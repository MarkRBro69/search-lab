"""Application layer for the Experiments module.

Orchestrates benchmark runs:
  1. Resolve Algorithm and QueryTemplate objects from the repository.
  2. For every (algorithm, template) pair, build SearchParams and call search_service.
  3. Compute TemplateResult with rich analytics.
  4. Aggregate per-algorithm summaries.
  5. Persist the BenchmarkRun.
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import TYPE_CHECKING

import structlog

from src.modules.experiments.domain.models import (
    Algorithm,
    AlgoSummary,
    BenchmarkRun,
    QueryTemplate,
    TemplateResult,
)
from src.modules.experiments.infrastructure import repository
from src.modules.search.api import (
    SearchParams,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    search,
)

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase
    from opensearchpy import OpenSearch

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# SearchParams builder
# ---------------------------------------------------------------------------


def _algo_to_params(algo: Algorithm, template: QueryTemplate, k: int) -> SearchParams:
    """Translate an Algorithm + QueryTemplate pair into a SearchParams dataclass."""
    f = algo.filters
    return SearchParams(
        q=template.query,
        mode=algo.mode,
        index_key=algo.index or template.index,
        size=k,
        bm25_weight=algo.bm25_weight,
        knn_weight=algo.knn_weight,
        num_candidates=algo.num_candidates,
        explain=False,
        min_rating=f.min_rating,
        max_cost_usd=f.max_cost_usd,
        category=f.category,
        body_area=f.body_area,
        is_surgical=f.is_surgical,
        specialty=f.specialty,
        min_experience=f.min_experience,
        worth_it=f.worth_it,
        verified=f.verified,
    )


# ---------------------------------------------------------------------------
# Analytics computation
# ---------------------------------------------------------------------------


def _compute_result(
    hits: list[dict],
    relevant_ids: list[str],
    latency_ms: int,
    k: int,
) -> TemplateResult:
    """Compute all analytics for one (algorithm, template) search result."""
    relevant = set(relevant_ids)
    ranked_ids = [h["id"] for h in hits]
    scores = [h["score"] for h in hits] if hits else [0.0]

    # Core IR metrics
    ndcg = ndcg_at_k(ranked_ids, relevant, k)
    mrr_val = mrr(ranked_ids, relevant)
    prec = precision_at_k(ranked_ids, relevant, k)
    rec = recall_at_k(ranked_ids, relevant, k)

    # Score distribution
    s_min = min(scores)
    s_max = max(scores)
    s_mean = sum(scores) / len(scores)
    s_std = (
        math.sqrt(sum((s - s_mean) ** 2 for s in scores) / len(scores)) if len(scores) > 1 else 0.0
    )

    # Separation: relevant vs non-relevant scores
    rel_scores = [h["score"] for h in hits if h["id"] in relevant]
    non_rel_scores = [h["score"] for h in hits if h["id"] not in relevant]
    rel_mean = sum(rel_scores) / len(rel_scores) if rel_scores else 0.0
    non_rel_mean = sum(non_rel_scores) / len(non_rel_scores) if non_rel_scores else 0.0

    # Positions (1-based)
    rel_positions = [i + 1 for i, h in enumerate(hits) if h["id"] in relevant]
    first_pos = rel_positions[0] if rel_positions else None

    return TemplateResult(
        ndcg_at_k=round(ndcg, 4),
        mrr=round(mrr_val, 4),
        precision_at_k=round(prec, 4),
        recall_at_k=round(rec, 4),
        latency_ms=latency_ms,
        score_min=round(s_min, 4),
        score_max=round(s_max, 4),
        score_mean=round(s_mean, 4),
        score_std=round(s_std, 4),
        relevant_score_mean=round(rel_mean, 4),
        non_relevant_score_mean=round(non_rel_mean, 4),
        score_separation=round(rel_mean - non_rel_mean, 4),
        first_relevant_position=first_pos,
        relevant_positions=rel_positions,
        total_hits=len(hits),
    )


def _summarise(template_results: dict[str, TemplateResult]) -> AlgoSummary:
    """Average per-template TemplateResults into a single AlgoSummary."""
    trs = list(template_results.values())
    n = len(trs) or 1

    def avg(attr: str) -> float:
        return round(sum(getattr(tr, attr) for tr in trs) / n, 4)

    return AlgoSummary(
        avg_ndcg_at_k=avg("ndcg_at_k"),
        avg_mrr=avg("mrr"),
        avg_precision_at_k=avg("precision_at_k"),
        avg_recall_at_k=avg("recall_at_k"),
        avg_latency_ms=avg("latency_ms"),
        avg_score_separation=avg("score_separation"),
        avg_score_mean=avg("score_mean"),
    )


# ---------------------------------------------------------------------------
# Core benchmark runner
# ---------------------------------------------------------------------------


async def run_benchmark(
    os_client: OpenSearch,
    algorithms: list[Algorithm],
    templates: list[QueryTemplate],
    k: int = 10,
    name: str = "",
) -> BenchmarkRun:
    """Execute all (algo × template) pairs concurrently, return a BenchmarkRun."""

    async def _eval_pair(
        algo: Algorithm, template: QueryTemplate
    ) -> tuple[str, str, TemplateResult]:
        params = _algo_to_params(algo, template, k)
        t0 = time.monotonic()
        result = await search(os_client, params)
        latency_ms = int((time.monotonic() - t0) * 1000)
        tr = _compute_result(result["hits"], template.relevant_ids, latency_ms, k)
        logger.info(
            "benchmark_pair_done",
            algo=algo.name,
            template=template.name,
            ndcg=tr.ndcg_at_k,
            sep=tr.score_separation,
            latency_ms=latency_ms,
        )
        return algo.id, template.id, tr

    tasks = [_eval_pair(algo, tmpl) for algo in algorithms for tmpl in templates]
    pairs = await asyncio.gather(*tasks)

    results: dict[str, dict[str, TemplateResult]] = {a.id: {} for a in algorithms}
    for algo_id, tmpl_id, tr in pairs:
        results[algo_id][tmpl_id] = tr

    summary = {algo_id: _summarise(trs) for algo_id, trs in results.items()}

    return BenchmarkRun(
        name=name,
        k=k,
        algorithm_ids=[a.id for a in algorithms],
        template_ids=[t.id for t in templates],
        results=results,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Public service functions (called by router)
# ---------------------------------------------------------------------------


async def create_algorithm(db: AsyncIOMotorDatabase, algo: Algorithm) -> Algorithm:  # type: ignore[type-arg]
    return await repository.create_algorithm(db, algo)


async def list_algorithms(db: AsyncIOMotorDatabase) -> list[Algorithm]:  # type: ignore[type-arg]
    return await repository.list_algorithms(db)


async def delete_algorithm(db: AsyncIOMotorDatabase, algo_id: str) -> bool:  # type: ignore[type-arg]
    return await repository.delete_algorithm(db, algo_id)


async def create_template(db: AsyncIOMotorDatabase, template: QueryTemplate) -> QueryTemplate:  # type: ignore[type-arg]
    return await repository.create_template(db, template)


async def list_templates(db: AsyncIOMotorDatabase) -> list[QueryTemplate]:  # type: ignore[type-arg]
    return await repository.list_templates(db)


async def update_template(db: AsyncIOMotorDatabase, template: QueryTemplate) -> QueryTemplate:  # type: ignore[type-arg]
    return await repository.update_template(db, template)


async def delete_template(db: AsyncIOMotorDatabase, template_id: str) -> bool:  # type: ignore[type-arg]
    return await repository.delete_template(db, template_id)


async def execute_benchmark(
    db: AsyncIOMotorDatabase,  # type: ignore[type-arg]
    os_client: OpenSearch,
    algorithm_ids: list[str],
    template_ids: list[str],
    k: int,
    name: str,
) -> BenchmarkRun:
    """Resolve IDs → objects, run benchmark, persist and return the run."""
    algo_tasks = [repository.get_algorithm(db, aid) for aid in algorithm_ids]
    tmpl_tasks = [repository.get_template(db, tid) for tid in template_ids]
    algos_raw, tmpls_raw = await asyncio.gather(
        asyncio.gather(*algo_tasks),
        asyncio.gather(*tmpl_tasks),
    )

    missing_algos = [aid for aid, a in zip(algorithm_ids, algos_raw, strict=True) if a is None]
    missing_tmpls = [tid for tid, t in zip(template_ids, tmpls_raw, strict=True) if t is None]
    if missing_algos or missing_tmpls:
        raise ValueError(f"Not found — algorithms: {missing_algos}, templates: {missing_tmpls}")

    algos: list[Algorithm] = list(algos_raw)  # type: ignore[arg-type]
    tmpls: list[QueryTemplate] = list(tmpls_raw)  # type: ignore[arg-type]

    run = await run_benchmark(os_client, algos, tmpls, k=k, name=name)
    return await repository.save_run(db, run)


async def list_runs(db: AsyncIOMotorDatabase) -> list[BenchmarkRun]:  # type: ignore[type-arg]
    return await repository.list_runs(db)


async def get_run(db: AsyncIOMotorDatabase, run_id: str) -> BenchmarkRun | None:  # type: ignore[type-arg]
    return await repository.get_run(db, run_id)


async def delete_run(db: AsyncIOMotorDatabase, run_id: str) -> bool:  # type: ignore[type-arg]
    return await repository.delete_run(db, run_id)
