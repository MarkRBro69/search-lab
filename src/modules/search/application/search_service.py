"""Search use case — BM25, semantic, hybrid (weighted), RRF."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING

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
from src.shared.exceptions import SEARCH_INVALID_MODE, InvalidInputError
from src.shared.search_mode import SearchMode

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from opensearchpy import OpenSearch

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Score normalization helpers
# ---------------------------------------------------------------------------


def _minmax(hits: list[dict[str, object]], score_key: str = "score") -> None:
    """Min-max normalize scores in-place."""
    if not hits:
        return
    scores = [float(h[score_key]) for h in hits if isinstance(h.get(score_key), (int, float))]
    if not scores:
        return
    lo = min(scores)
    hi = max(scores)
    for h in hits:
        raw = h.get(score_key)
        if not isinstance(raw, (int, float)):
            continue
        h[score_key] = round((float(raw) - lo) / (hi - lo), 6) if hi > lo else 1.0


# ---------------------------------------------------------------------------
# Simple modes: BM25-only, KNN-only
# ---------------------------------------------------------------------------


def _parse_hits(raw: dict[str, object]) -> tuple[int, list[dict[str, object]]]:
    total = _extract_total(raw)
    hits_obj = raw["hits"]
    if not isinstance(hits_obj, dict):
        return total, []
    raw_hits = hits_obj.get("hits", [])
    if not isinstance(raw_hits, list):
        return total, []
    hits: list[dict[str, object]] = []
    for h in raw_hits:
        if not isinstance(h, dict):
            continue
        src_raw = h.get("_source")
        src: dict[str, object] = dict(src_raw) if isinstance(src_raw, dict) else {}
        src.pop("embedding", None)
        score_raw = h.get("_score")
        score = float(score_raw) if isinstance(score_raw, (int, float)) else 0.0
        hit: dict[str, object] = {
            "id": str(h["_id"]),
            "index": h["_index"],
            "score": score,
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
    bm25_hits: list[dict[str, object]],
    knn_hits: list[dict[str, object]],
    params: SearchParams,
) -> list[dict[str, object]]:
    bm25_map: dict[str, dict[str, object]] = {str(h["id"]): h for h in bm25_hits}
    knn_map: dict[str, dict[str, object]] = {str(h["id"]): h for h in knn_hits}

    bm25_rank: dict[str, int] = {str(h["id"]): i + 1 for i, h in enumerate(bm25_hits)}
    knn_rank: dict[str, int] = {str(h["id"]): i + 1 for i, h in enumerate(knn_hits)}
    bm25_miss = len(bm25_hits) + 1
    knn_miss = len(knn_hits) + 1
    n_bm25 = len(bm25_hits) if bm25_hits else 1
    n_knn = len(knn_hits) if knn_hits else 1

    all_ids = set(bm25_map) | set(knn_map)
    docs: list[dict[str, object]] = []

    for doc_id in all_ids:
        r_b = bm25_rank.get(doc_id, bm25_miss)
        r_k = knn_rank.get(doc_id, knn_miss)
        b_rs = (n_bm25 - r_b + 1) / n_bm25
        k_rs = (n_knn - r_k + 1) / n_knn
        combined = params.bm25_weight * b_rs + params.knn_weight * k_rs

        source_hit = bm25_map.get(doc_id) or knn_map.get(doc_id)
        assert source_hit is not None
        doc: dict[str, object] = {
            "id": doc_id,
            "index": source_hit["index"],
            "score": round(combined, 6),
            "source": source_hit["source"],
        }
        if params.explain:
            doc["score_breakdown"] = {
                "bm25_rank": r_b,
                "knn_rank": r_k,
                "bm25_rank_score": round(b_rs, 4),
                "knn_rank_score": round(k_rs, 4),
                "bm25_contribution": round(params.bm25_weight * b_rs, 4),
                "knn_contribution": round(params.knn_weight * k_rs, 4),
            }
        docs.append(doc)

    docs.sort(key=lambda d: float(d["score"]), reverse=True)
    return docs[: params.size]


# ---------------------------------------------------------------------------
# RRF: Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

_RRF_K = 60  # standard constant from the original RRF paper


def _rrf_combine(
    bm25_hits: list[dict[str, object]],
    knn_hits: list[dict[str, object]],
    params: SearchParams,
) -> list[dict[str, object]]:
    bm25_map: dict[str, dict[str, object]] = {str(h["id"]): h for h in bm25_hits}
    knn_map: dict[str, dict[str, object]] = {str(h["id"]): h for h in knn_hits}
    bm25_rank: dict[str, int] = {str(h["id"]): i + 1 for i, h in enumerate(bm25_hits)}
    knn_rank: dict[str, int] = {str(h["id"]): i + 1 for i, h in enumerate(knn_hits)}

    bm25_miss = len(bm25_hits) + 1
    knn_miss = len(knn_hits) + 1

    all_ids = set(bm25_map) | set(knn_map)
    docs: list[dict[str, object]] = []

    for doc_id in all_ids:
        r_b = bm25_rank.get(doc_id, bm25_miss)
        r_k = knn_rank.get(doc_id, knn_miss)
        rrf_b = 1.0 / (_RRF_K + r_b)
        rrf_k = 1.0 / (_RRF_K + r_k)
        combined = rrf_b + rrf_k

        source_hit = bm25_map.get(doc_id) or knn_map.get(doc_id)
        assert source_hit is not None
        doc: dict[str, object] = {
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

    docs.sort(key=lambda d: float(d["score"]), reverse=True)
    return docs[: params.size]


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


async def search(
    client: OpenSearch,
    params: SearchParams,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
    embed: Callable[[str], Awaitable[list[float]]],
) -> dict[str, object]:
    log = logger.bind(module="search", operation="search")
    log.info(
        "search_request",
        query=params.q,
        mode=params.mode,
        index=params.index_key,
        size=params.size,
        explain=params.explain,
        filters=params.active_filters(),
    )

    loop = asyncio.get_running_loop()

    if params.mode == SearchMode.BM25:
        raw = await loop.run_in_executor(
            None,
            partial(search_bm25, client, params, index_alias, bm25_fields_by_key),
        )
        total, hits = _parse_hits(raw)
        _minmax(hits)

    elif params.mode == SearchMode.SEMANTIC:
        vector = await embed(params.q)
        raw = await loop.run_in_executor(
            None, partial(search_knn, client, vector, params, index_alias)
        )
        total, hits = _parse_hits(raw)
        _minmax(hits)

    elif params.mode == SearchMode.HYBRID:
        vector = await embed(params.q)
        bm25_hits, knn_hits = await asyncio.gather(
            loop.run_in_executor(
                None,
                partial(search_bm25_wide, client, params, index_alias, bm25_fields_by_key),
            ),
            loop.run_in_executor(
                None, partial(search_knn_wide, client, vector, params, index_alias)
            ),
        )
        hits = _hybrid_combine(bm25_hits, knn_hits, params)
        _minmax(hits)
        total = len(set(h["id"] for h in bm25_hits) | set(h["id"] for h in knn_hits))

    elif params.mode == SearchMode.RRF:
        vector = await embed(params.q)
        bm25_hits, knn_hits = await asyncio.gather(
            loop.run_in_executor(
                None,
                partial(search_bm25_wide, client, params, index_alias, bm25_fields_by_key),
            ),
            loop.run_in_executor(
                None, partial(search_knn_wide, client, vector, params, index_alias)
            ),
        )
        hits = _rrf_combine(bm25_hits, knn_hits, params)
        _minmax(hits)
        total = len(set(h["id"] for h in bm25_hits) | set(h["id"] for h in knn_hits))

    else:
        raise InvalidInputError(
            code=SEARCH_INVALID_MODE,
            detail=f"Unknown search mode: {params.mode!r}",
        )

    log.info("search_done", query=params.q, mode=params.mode, total=total, returned=len(hits))

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
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> dict[str, object]:
    """Return OpenSearch native _explain response for a single document."""
    log = logger.bind(module="search", operation="explain_document_async")
    log.info("explain_requested", index_key=index_key, doc_id=doc_id)
    loop = asyncio.get_running_loop()
    result: dict[str, object] = await loop.run_in_executor(
        None,
        partial(
            explain_document,
            client,
            index_key,
            doc_id,
            query,
            index_alias,
            bm25_fields_by_key,
        ),
    )
    log.info("explain_done", matched=result.get("matched"))
    return result
