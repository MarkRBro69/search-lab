"""OpenSearch search repository — BM25, semantic (KNN), hybrid, RRF queries."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import structlog
from opensearchpy.exceptions import NotFoundError, TransportError

from src.shared.exceptions import SEARCH_UNAVAILABLE, ServiceUnavailableError

if TYPE_CHECKING:
    from opensearchpy import OpenSearch

    from src.modules.search.application.search_params import SearchParams

logger = structlog.get_logger(module="search")


def _resolve_index(index_key: str, index_alias: dict[str, str], *, default_key: str = "all") -> str:
    # Single known logical key → resolved physical name.
    if index_key in index_alias:
        return index_alias[index_key]
    # Comma-joined logical keys (e.g. "doctors,procedures") → expand each to physical name.
    parts = [p.strip() for p in index_key.split(",") if p.strip()]
    if len(parts) > 1:
        return ",".join(index_alias.get(p, p) for p in parts)
    # Unknown single key (already a physical name) → pass through.
    return index_key


def _bm25_field_list(index_key: str, bm25_fields_by_key: dict[str, list[str]]) -> list[str]:
    # For comma-joined keys, use the 'all' field list as the combined superset.
    if "," in index_key:
        return list(bm25_fields_by_key.get("all", []))
    return list(bm25_fields_by_key.get(index_key, bm25_fields_by_key.get("all", [])))


def _split_pair(s: str) -> tuple[str, str] | None:
    """Split 'field:value' into (field, value). Returns None if the format is invalid."""
    idx = s.find(":")
    if idx <= 0:
        return None
    return s[:idx].strip(), s[idx + 1 :].strip()


# ---------------------------------------------------------------------------
# Filter builder
# ---------------------------------------------------------------------------


def build_filters(params: SearchParams) -> list[dict[str, object]]:
    """Build generic OpenSearch filter clauses from key-value filter params.

    Supports any document schema — field names are passed through as-is.
    """
    clauses: list[dict[str, object]] = []

    for s in params.filter_term:
        pair = _split_pair(s)
        if not pair:
            continue
        f, v = pair
        # Auto-cast "true"/"false" strings to booleans; pass everything else as string
        if v.lower() == "true":
            clauses.append({"term": {f: True}})
        elif v.lower() == "false":
            clauses.append({"term": {f: False}})
        else:
            clauses.append({"term": {f: v}})

    # Merge gte/lte filters on the same field into a single range clause
    ranges: dict[str, dict[str, float]] = {}
    for s in params.filter_gte:
        pair = _split_pair(s)
        if not pair:
            continue
        f, v = pair
        with contextlib.suppress(ValueError):
            ranges.setdefault(f, {})["gte"] = float(v)
    for s in params.filter_lte:
        pair = _split_pair(s)
        if not pair:
            continue
        f, v = pair
        with contextlib.suppress(ValueError):
            ranges.setdefault(f, {})["lte"] = float(v)
    for f, bounds in ranges.items():
        clauses.append({"range": {f: bounds}})

    return clauses


# ---------------------------------------------------------------------------
# Query body builders
# ---------------------------------------------------------------------------


def build_bm25_query(
    query: str,
    index_key: str,
    bm25_fields_by_key: dict[str, list[str]],
) -> dict[str, dict[str, object]]:
    """Return a bare multi_match query dict (for use in rank_eval requests)."""
    fields = _bm25_field_list(index_key, bm25_fields_by_key)
    return {
        "multi_match": {
            "query": query,
            "fields": fields,
            "type": "best_fields",
            "fuzziness": "AUTO",
        }
    }


def _bm25_body(
    params: SearchParams,
    size: int,
    bm25_fields_by_key: dict[str, list[str]],
    include_explain: bool = False,
) -> dict[str, object]:
    filters = build_filters(params)
    fields = _bm25_field_list(params.index_key, bm25_fields_by_key)
    multi_match: dict[str, object] = {
        "query": params.q,
        "fields": fields,
        "type": "best_fields",
        "fuzziness": "AUTO",
    }
    body: dict[str, object]
    if filters:
        body = {
            "size": size,
            "query": {"bool": {"must": {"multi_match": multi_match}, "filter": filters}},
        }
    else:
        body = {"size": size, "query": {"multi_match": multi_match}}
    if include_explain:
        body["explain"] = True
    return body


def _knn_body(vector: list[float], params: SearchParams, size: int) -> dict[str, object]:
    filters = build_filters(params)
    knn_clause: dict[str, object] = {"vector": vector, "k": size}
    if filters:
        knn_clause["filter"] = {"bool": {"filter": filters}}
    return {"size": size, "query": {"knn": {"embedding": knn_clause}}}


# ---------------------------------------------------------------------------
# Raw hit extractor (used by hybrid / rrf)
# ---------------------------------------------------------------------------


def _extract_raw_hits(resp: dict[str, object]) -> list[dict[str, object]]:
    hits_obj = resp["hits"]
    if not isinstance(hits_obj, dict):
        return []
    raw_hits = hits_obj.get("hits", [])
    if not isinstance(raw_hits, list):
        return []
    hits: list[dict[str, object]] = []
    for h in raw_hits:
        if not isinstance(h, dict):
            continue
        src_raw = h.get("_source")
        src: dict[str, object] = dict(src_raw) if isinstance(src_raw, dict) else {}
        src.pop("embedding", None)
        score_raw = h.get("_score")
        score = float(score_raw) if isinstance(score_raw, (int, float)) else 0.0
        hits.append(
            {
                "id": h["_id"],
                "index": h["_index"],
                "score": score,
                "source": src,
            }
        )
    return hits


def _extract_total(resp: dict[str, object]) -> int:
    hits_obj = resp["hits"]
    if not isinstance(hits_obj, dict):
        return 0
    val = hits_obj["total"]
    if isinstance(val, dict):
        v = val.get("value")
        return int(v) if isinstance(v, int) else 0
    if isinstance(val, int):
        return val
    return 0


# ---------------------------------------------------------------------------
# Public search functions
# ---------------------------------------------------------------------------


def _transport_error_info_snippet(err: TransportError) -> str:
    """Safe `err.info` — the property can raise if the exception tuple is incomplete."""
    try:
        return str(err.info)[:500]
    except IndexError, TypeError, AttributeError:
        return ""


def _log_transport_error(operation: str, err: TransportError, **ctx: object) -> None:
    """Log TransportError details before converting to ServiceUnavailableError."""
    log = logger.bind(operation=operation)
    log.error(
        "opensearch_transport_error",
        status_code=getattr(err, "status_code", None),
        error=str(getattr(err, "error", err))[:500],
        info=_transport_error_info_snippet(err),
        **ctx,
    )


def search_bm25(
    client: OpenSearch,
    params: SearchParams,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> dict[str, object]:
    try:
        index = _resolve_index(params.index_key, index_alias)
        log = logger.bind(operation="search_bm25")
        log.debug("search_bm25", index=index, query=params.q)
        body = _bm25_body(params, params.size, bm25_fields_by_key, include_explain=params.explain)
        return client.search(index=index, body=body)
    except TransportError as err:
        _log_transport_error("search_bm25", err, index=params.index_key, query=params.q)
        raise ServiceUnavailableError(
            code=SEARCH_UNAVAILABLE,
            detail="Search service temporarily unavailable",
        ) from err


def search_knn(
    client: OpenSearch,
    vector: list[float],
    params: SearchParams,
    index_alias: dict[str, str],
) -> dict[str, object]:
    try:
        index = _resolve_index(params.index_key, index_alias)
        log = logger.bind(operation="search_knn")
        log.debug("search_knn", index=index)
        return client.search(index=index, body=_knn_body(vector, params, params.size))
    except TransportError as err:
        _log_transport_error("search_knn", err, index=params.index_key)
        raise ServiceUnavailableError(
            code=SEARCH_UNAVAILABLE,
            detail="Search service temporarily unavailable",
        ) from err


def search_bm25_wide(
    client: OpenSearch,
    params: SearchParams,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> list[dict[str, object]]:
    try:
        index = _resolve_index(params.index_key, index_alias)
        resp = client.search(
            index=index, body=_bm25_body(params, params.candidate_size, bm25_fields_by_key)
        )
        return _extract_raw_hits(resp)
    except TransportError as err:
        _log_transport_error("search_bm25_wide", err, index=params.index_key, query=params.q)
        raise ServiceUnavailableError(
            code=SEARCH_UNAVAILABLE,
            detail="Search service temporarily unavailable",
        ) from err


def search_knn_wide(
    client: OpenSearch,
    vector: list[float],
    params: SearchParams,
    index_alias: dict[str, str],
) -> list[dict[str, object]]:
    try:
        index = _resolve_index(params.index_key, index_alias)
        resp = client.search(index=index, body=_knn_body(vector, params, params.candidate_size))
        return _extract_raw_hits(resp)
    except TransportError as err:
        _log_transport_error("search_knn_wide", err, index=params.index_key)
        raise ServiceUnavailableError(
            code=SEARCH_UNAVAILABLE,
            detail="Search service temporarily unavailable",
        ) from err


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def get_document(
    client: OpenSearch, index_key: str, doc_id: str, index_alias: dict[str, str]
) -> dict[str, object] | None:
    index = index_alias.get(index_key)
    if not index:
        return None
    try:
        return client.get(index=index, id=doc_id)
    except NotFoundError:
        return None
    except TransportError as err:
        raise ServiceUnavailableError(
            code=SEARCH_UNAVAILABLE,
            detail="Search service temporarily unavailable",
        ) from err


def index_document(
    client: OpenSearch,
    index_key: str,
    doc_id: str,
    body: dict[str, object],
    index_alias: dict[str, str],
) -> dict[str, object]:
    index = index_alias.get(index_key)
    if index is None:
        msg = f"Unknown index key for index_document: {index_key!r}"
        raise ValueError(msg)
    resp = client.index(index=index, id=doc_id, body=body, refresh="wait_for")
    log = logger.bind(operation="index_document")
    log.info("document_indexed", index=index, doc_id=doc_id, result=resp.get("result"))
    return resp


def delete_document(
    client: OpenSearch, index_key: str, doc_id: str, index_alias: dict[str, str]
) -> bool:
    index = index_alias.get(index_key)
    if not index:
        return False
    try:
        resp = client.delete(index=index, id=doc_id, refresh="wait_for")
        log = logger.bind(operation="delete_document")
        log.info("document_deleted", index=index, doc_id=doc_id, result=resp.get("result"))
        return resp.get("result") == "deleted"
    except NotFoundError:
        return False
    except TransportError as err:
        raise ServiceUnavailableError(
            code=SEARCH_UNAVAILABLE,
            detail="Search service temporarily unavailable",
        ) from err


# ---------------------------------------------------------------------------
# Native OpenSearch explain API
# ---------------------------------------------------------------------------


def explain_document(
    client: OpenSearch,
    index_key: str,
    doc_id: str,
    query: str,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> dict[str, object]:
    """Call OpenSearch _explain for a single document against a BM25 query."""
    index = index_alias.get(index_key)
    if index is None:
        msg = f"Unknown index key for explain: {index_key!r}"
        raise ValueError(msg)
    body: dict[str, object] = {
        "query": build_bm25_query(query, index_key, bm25_fields_by_key),
    }
    log = logger.bind(operation="explain_document")
    log.debug("explain_document", index=index, doc_id=doc_id)
    return client.explain(index=index, id=doc_id, body=body)


# ---------------------------------------------------------------------------
# Native OpenSearch _rank_eval API
# ---------------------------------------------------------------------------


def rank_eval_native(
    client: OpenSearch,
    index_key: str,
    requests: list[dict[str, object]],
    metric: dict[str, dict[str, int]],
    index_alias: dict[str, str],
) -> dict[str, object]:
    """Call OpenSearch _rank_eval with pre-built request objects."""
    index = _resolve_index(index_key, index_alias)
    body: dict[str, object] = {"requests": requests, "metric": metric}
    log = logger.bind(operation="rank_eval_native")
    log.debug("rank_eval_native", index=index, num_requests=len(requests))
    return client.rank_eval(body=body, index=index)
