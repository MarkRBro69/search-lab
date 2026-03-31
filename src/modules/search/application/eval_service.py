"""Offline relevance evaluation — NDCG, MRR, Precision@K, native rank_eval."""

from __future__ import annotations

import asyncio
import math
from functools import partial
from typing import TYPE_CHECKING, TypedDict

import structlog

from src.modules.search.application.search_params import SearchParams  # noqa: TC001
from src.modules.search.application.search_service import search
from src.modules.search.infrastructure.repository import (
    build_bm25_query,
    rank_eval_native,
)
from src.shared.exceptions import (
    EVAL_METRIC_INCOMPLETE,
    INVALID_INDEX_KEY,
    InvalidInputError,
    UnprocessableEntityError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from opensearchpy import OpenSearch

logger = structlog.get_logger()


class _RatingData(TypedDict):
    doc_id: str
    rating: int


class _QueryData(TypedDict):
    id: str
    query: str
    ratings: list[_RatingData]


class RankEvalQueryDetail(TypedDict):
    """Per-query slice of the OpenSearch _rank_eval response."""

    metric_score: float
    unrated_docs: list[str]


class RankEvalResult(TypedDict):
    """Typed aggregate result from native OpenSearch _rank_eval."""

    metric_score: float
    details: dict[str, RankEvalQueryDetail]
    failures: dict[str, str]


# ---------------------------------------------------------------------------
# Metric implementations
# ---------------------------------------------------------------------------


def _dcg(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    return sum(
        1.0 / math.log2(i + 2) for i, doc_id in enumerate(ranked_ids[:k]) if doc_id in relevant
    )


def ndcg_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    """Normalised Discounted Cumulative Gain @K."""
    ideal = _dcg(list(relevant)[:k], relevant, k)
    return _dcg(ranked_ids, relevant, k) / ideal if ideal > 0 else 0.0


def mrr(ranked_ids: list[str], relevant: set[str]) -> float:
    """Mean Reciprocal Rank — reciprocal of the first relevant result position."""
    for i, doc_id in enumerate(ranked_ids):
        if doc_id in relevant:
            return 1.0 / (i + 1)
    return 0.0


def precision_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    """Fraction of top-K results that are relevant."""
    return sum(1 for doc_id in ranked_ids[:k] if doc_id in relevant) / k if k > 0 else 0.0


def recall_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    """Fraction of all relevant documents found in top-K."""
    if not relevant:
        return 0.0
    return sum(1 for doc_id in ranked_ids[:k] if doc_id in relevant) / len(relevant)


# ---------------------------------------------------------------------------
# Public eval function
# ---------------------------------------------------------------------------


async def evaluate(
    client: OpenSearch,
    params: SearchParams,
    relevant_ids: list[str],
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
    embed: Callable[[str], Awaitable[list[float]]],
) -> dict[str, object]:
    relevant = set(relevant_ids)
    result = await search(client, params, index_alias, bm25_fields_by_key, embed)
    hits_raw = result["hits"]
    hits: list[dict[str, object]] = hits_raw if isinstance(hits_raw, list) else []

    ranked_ids = [h["id"] for h in hits]
    k = params.size

    n = ndcg_at_k(ranked_ids, relevant, k)
    m = mrr(ranked_ids, relevant)
    p = precision_at_k(ranked_ids, relevant, k)
    r = recall_at_k(ranked_ids, relevant, k)

    relevant_positions = [i + 1 for i, doc_id in enumerate(ranked_ids) if doc_id in relevant]

    log = logger.bind(module="search", operation="evaluate")
    log.info(
        "eval_done",
        query=params.q,
        mode=params.mode,
        ndcg=round(n, 4),
        mrr=round(m, 4),
        precision=round(p, 4),
        recall=round(r, 4),
        relevant_provided=len(relevant),
        relevant_found=len(relevant_positions),
    )

    return {
        "query": params.q,
        "mode": params.mode,
        "index": params.index_key,
        "k": k,
        "metrics": {
            "ndcg_at_k": round(n, 4),
            "mrr": round(m, 4),
            "precision_at_k": round(p, 4),
            "recall_at_k": round(r, 4),
        },
        "relevant_provided": len(relevant),
        "relevant_found": len(relevant_positions),
        "relevant_positions": relevant_positions,
        "hits": hits,
    }


# ---------------------------------------------------------------------------
# Native OpenSearch _rank_eval
# ---------------------------------------------------------------------------


async def rank_eval(
    client: OpenSearch,
    index_key: str,
    query_inputs: list[_QueryData],
    k: int,
    metric_name: str,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> RankEvalResult:
    """Evaluate ranking quality using the native OpenSearch _rank_eval API (BM25 only)."""
    log = logger.bind(module="search", operation="rank_eval")

    if index_key not in index_alias:
        raise InvalidInputError(
            code=INVALID_INDEX_KEY,
            detail=f"Unknown index key for rank_eval: {index_key!r}",
        )
    resolved_index = index_alias[index_key]

    os_requests: list[dict[str, object]] = [
        {
            "id": q["id"],
            "request": {
                "query": build_bm25_query(q["query"], index_key, bm25_fields_by_key),
            },
            "ratings": [
                {"_index": resolved_index, "_id": r["doc_id"], "rating": r["rating"]}
                for r in q["ratings"]
            ],
        }
        for q in query_inputs
    ]
    metric: dict[str, dict[str, int]] = {metric_name: {"k": k}}

    log.info(
        "rank_eval_started",
        index=resolved_index,
        num_queries=len(os_requests),
        metric=metric_name,
        k=k,
    )
    loop = asyncio.get_running_loop()
    raw: dict[str, object] = await loop.run_in_executor(
        None,
        partial(rank_eval_native, client, index_key, os_requests, metric, index_alias),
    )

    details_raw = raw.get("details", {})
    details: dict[str, dict[str, object]] = {}
    if isinstance(details_raw, dict):
        for qid, res in details_raw.items():
            if not isinstance(res, dict):
                continue
            unrated = res.get("unrated_docs", [])
            unrated_ids: list[str] = []
            if isinstance(unrated, list):
                for entry in unrated:
                    if isinstance(entry, dict) and "_id" in entry:
                        unrated_ids.append(str(entry["_id"]))
            ms_raw = res.get("metric_score")
            metric_score_detail = float(ms_raw) if isinstance(ms_raw, (int, float)) else 0.0
            details[str(qid)] = {
                "metric_score": metric_score_detail,
                "unrated_docs": unrated_ids,
            }

    log.info("rank_eval_done", overall_score=raw.get("metric_score"), num_queries=len(details))

    failures_raw = raw.get("failures", {})
    failures: dict[str, str] = {}
    if isinstance(failures_raw, dict):
        for fk, fv in failures_raw.items():
            failures[str(fk)] = str(fv)

    metric_score = raw.get("metric_score")
    if metric_score is None:
        raise UnprocessableEntityError(
            code=EVAL_METRIC_INCOMPLETE,
            detail="Rank eval response missing metric_score",
        )

    try:
        overall_score = float(metric_score)
    except TypeError, ValueError:
        raise UnprocessableEntityError(
            code=EVAL_METRIC_INCOMPLETE,
            detail="Rank eval response metric_score is not a valid number",
        ) from None

    out: RankEvalResult = {
        "metric_score": overall_score,
        "details": details,
        "failures": failures,
    }
    return out
