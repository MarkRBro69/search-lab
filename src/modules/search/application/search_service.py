"""Search use case — BM25, semantic, hybrid (weighted), RRF."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Any

import structlog

from src.modules.search.application.search_params import SearchParams  # noqa: TC001
from src.modules.search.infrastructure.repository import (
    _extract_total,
    explain_document,
    search_bm25,
    search_bm25_wide,
    search_knn,
    search_knn_wide,
)
from src.shared.infrastructure.embedding import embed_async

if TYPE_CHECKING:
    from opensearchpy import OpenSearch

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Score normalization helpers
# ---------------------------------------------------------------------------


def _minmax(hits: list[dict], score_key: str = "score") -> None:
    """Min-max normalize scores in-place."""
    if not hits:
        return
    lo = min(h[score_key] for h in hits)
    hi = max(h[score_key] for h in hits)
    for h in hits:
        h[score_key] = round((h[score_key] - lo) / (hi - lo), 6) if hi > lo else 1.0


# ---------------------------------------------------------------------------
# Simple modes: BM25-only, KNN-only
# ---------------------------------------------------------------------------


def _parse_hits(raw: dict) -> tuple[int, list[dict]]:
    total = _extract_total(raw)
    hits = []
    for h in raw["hits"]["hits"]:
        src = h["_source"].copy()
        src.pop("embedding", None)
        hit: dict[str, Any] = {
            "id": h["_id"],
            "index": h["_index"],
            "score": h["_score"] or 0.0,
            "source": src,
        }
        if "_explanation" in h:
            hit["os_explanation"] = h["_explanation"]
        hits.append(hit)
    return total, hits


# ---------------------------------------------------------------------------
# Hybrid: weighted combination (Python-side, runs queries in parallel)
# ---------------------------------------------------------------------------


def _hybrid_combine(
    bm25_hits: list[dict],
    knn_hits: list[dict],
    params: SearchParams,
) -> list[dict]:
    # Build lookup maps
    bm25_map: dict[str, dict] = {h["id"]: h for h in bm25_hits}
    knn_map: dict[str, dict] = {h["id"]: h for h in knn_hits}

    # Normalize scores within each list
    bm25_scores = {h["id"]: h["score"] for h in bm25_hits}
    knn_scores = {h["id"]: h["score"] for h in knn_hits}

    def _norm(scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return {}
        lo, hi = min(scores.values()), max(scores.values())
        if hi == lo:
            return {k: 1.0 for k in scores}
        return {k: (v - lo) / (hi - lo) for k, v in scores.items()}

    bm25_norm = _norm(bm25_scores)
    knn_norm = _norm(knn_scores)

    all_ids = set(bm25_map) | set(knn_map)
    docs: list[dict[str, Any]] = []

    for doc_id in all_ids:
        b_n = bm25_norm.get(doc_id, 0.0)
        k_n = knn_norm.get(doc_id, 0.0)
        combined = params.bm25_weight * b_n + params.knn_weight * k_n

        source_hit = bm25_map.get(doc_id) or knn_map.get(doc_id)
        assert source_hit is not None
        doc: dict[str, Any] = {
            "id": doc_id,
            "index": source_hit["index"],
            "score": round(combined, 6),
            "source": source_hit["source"],
        }
        if params.explain:
            doc["score_breakdown"] = {
                "bm25_raw": round(bm25_scores.get(doc_id, 0.0), 4),
                "bm25_normalized": round(b_n, 4),
                "knn_cosine": round(knn_scores.get(doc_id, 0.0), 4),
                "knn_normalized": round(k_n, 4),
                "bm25_contribution": round(params.bm25_weight * b_n, 4),
                "knn_contribution": round(params.knn_weight * k_n, 4),
            }
        docs.append(doc)

    docs.sort(key=lambda d: d["score"], reverse=True)
    return docs[: params.size]


# ---------------------------------------------------------------------------
# RRF: Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

_RRF_K = 60  # standard constant from the original RRF paper


def _rrf_combine(
    bm25_hits: list[dict],
    knn_hits: list[dict],
    params: SearchParams,
) -> list[dict]:
    bm25_map: dict[str, dict] = {h["id"]: h for h in bm25_hits}
    knn_map: dict[str, dict] = {h["id"]: h for h in knn_hits}
    bm25_rank: dict[str, int] = {h["id"]: i + 1 for i, h in enumerate(bm25_hits)}
    knn_rank: dict[str, int] = {h["id"]: i + 1 for i, h in enumerate(knn_hits)}

    # Penalty rank for a doc missing from one list
    bm25_miss = len(bm25_hits) + 1
    knn_miss = len(knn_hits) + 1

    all_ids = set(bm25_map) | set(knn_map)
    docs: list[dict[str, Any]] = []

    for doc_id in all_ids:
        r_b = bm25_rank.get(doc_id, bm25_miss)
        r_k = knn_rank.get(doc_id, knn_miss)
        rrf_b = 1.0 / (_RRF_K + r_b)
        rrf_k = 1.0 / (_RRF_K + r_k)
        combined = rrf_b + rrf_k

        source_hit = bm25_map.get(doc_id) or knn_map.get(doc_id)
        assert source_hit is not None
        doc: dict[str, Any] = {
            "id": doc_id,
            "index": source_hit["index"],
            "score": round(combined, 6),
            "source": source_hit["source"],
        }
        if params.explain:
            doc["score_breakdown"] = {
                "bm25_rank": r_b,
                "knn_rank": r_k,
                "rrf_bm25": round(rrf_b, 6),
                "rrf_knn": round(rrf_k, 6),
                "rrf_k": _RRF_K,
            }
        docs.append(doc)

    docs.sort(key=lambda d: d["score"], reverse=True)
    return docs[: params.size]


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


async def search(client: OpenSearch, params: SearchParams) -> dict:
    logger.info(
        "search_request",
        query=params.q,
        mode=params.mode,
        index=params.index_key,
        size=params.size,
        explain=params.explain,
        filters=params.active_filters(),
    )

    loop = asyncio.get_running_loop()
    vector: list[float] | None = None

    # ── BM25-only ─────────────────────────────────────────────────────────
    if params.mode == "bm25":
        raw = await loop.run_in_executor(None, partial(search_bm25, client, params))
        total, hits = _parse_hits(raw)
        _minmax(hits)

    # ── Semantic-only ──────────────────────────────────────────────────────
    elif params.mode == "semantic":
        vector = await embed_async(params.q)
        raw = await loop.run_in_executor(None, partial(search_knn, client, vector, params))
        total, hits = _parse_hits(raw)

    # ── Hybrid (weighted, Python-side) ─────────────────────────────────────
    elif params.mode == "hybrid":
        vector = await embed_async(params.q)
        bm25_hits, knn_hits = await asyncio.gather(
            loop.run_in_executor(None, partial(search_bm25_wide, client, params)),
            loop.run_in_executor(None, partial(search_knn_wide, client, vector, params)),
        )
        hits = _hybrid_combine(bm25_hits, knn_hits, params)
        total = len(set(h["id"] for h in bm25_hits) | set(h["id"] for h in knn_hits))

    # ── RRF ───────────────────────────────────────────────────────────────
    elif params.mode == "rrf":
        vector = await embed_async(params.q)
        bm25_hits, knn_hits = await asyncio.gather(
            loop.run_in_executor(None, partial(search_bm25_wide, client, params)),
            loop.run_in_executor(None, partial(search_knn_wide, client, vector, params)),
        )
        hits = _rrf_combine(bm25_hits, knn_hits, params)
        total = len(set(h["id"] for h in bm25_hits) | set(h["id"] for h in knn_hits))

    else:
        raise ValueError(f"Unknown search mode: {params.mode!r}")

    logger.info("search_done", query=params.q, mode=params.mode, total=total, returned=len(hits))

    return {
        "query": params.q,
        "mode": params.mode,
        "index": params.index_key,
        "total": total,
        "hits": hits,
        "filters": params.active_filters(),
        "params": {
            "bm25_weight": params.bm25_weight,
            "knn_weight": params.knn_weight,
            "num_candidates": params.num_candidates,
            "explain": params.explain,
        },
    }


async def explain_document_async(
    client: OpenSearch,
    index_key: str,
    doc_id: str,
    query: str,
) -> dict:
    """Return OpenSearch native _explain response for a single document."""
    log = logger.bind(module="search", operation="explain_document_async")
    log.info("explain_requested", index_key=index_key, doc_id=doc_id)
    loop = asyncio.get_running_loop()
    result: dict = await loop.run_in_executor(
        None,
        partial(explain_document, client, index_key, doc_id, query),
    )
    log.info("explain_done", matched=result.get("matched"))
    return result
