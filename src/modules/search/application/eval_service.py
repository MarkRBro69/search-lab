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
    INDEX_ALIAS,
    INDEX_PROCEDURES,
    build_bm25_query,
    rank_eval_native,
)

if TYPE_CHECKING:
    from opensearchpy import OpenSearch

logger = structlog.get_logger()


class _RatingData(TypedDict):
    doc_id: str
    rating: int


class _QueryData(TypedDict):
    id: str
    query: str
    ratings: list[_RatingData]


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
) -> dict:
    relevant = set(relevant_ids)
    result = await search(client, params)
    hits = result["hits"]

    ranked_ids = [h["id"] for h in hits]
    k = params.size

    n = ndcg_at_k(ranked_ids, relevant, k)
    m = mrr(ranked_ids, relevant)
    p = precision_at_k(ranked_ids, relevant, k)
    r = recall_at_k(ranked_ids, relevant, k)

    relevant_positions = [i + 1 for i, doc_id in enumerate(ranked_ids) if doc_id in relevant]

    logger.info(
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
) -> dict[str, object]:
    """Evaluate ranking quality using the native OpenSearch _rank_eval API (BM25 only)."""
    log = logger.bind(module="search", operation="rank_eval")

    resolved_index = INDEX_ALIAS.get(index_key, INDEX_PROCEDURES)

    os_requests: list[dict] = [
        {
            "id": q["id"],
            "request": {"query": build_bm25_query(q["query"], index_key)},
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
    raw: dict = await loop.run_in_executor(
        None,
        partial(rank_eval_native, client, index_key, os_requests, metric),
    )

    details: dict[str, dict[str, object]] = {
        qid: {
            "metric_score": res["metric_score"],
            "unrated_docs": [entry["_id"] for entry in res.get("unrated_docs", [])],
        }
        for qid, res in raw.get("details", {}).items()
    }

    log.info("rank_eval_done", overall_score=raw.get("metric_score"), num_queries=len(details))

    return {
        "metric_score": raw["metric_score"],
        "details": details,
        "failures": raw.get("failures", {}),
    }
