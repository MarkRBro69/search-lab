"""OpenSearch search repository — BM25, semantic (KNN), hybrid, RRF queries."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from opensearchpy import OpenSearch

    from src.modules.search.application.search_params import SearchParams

logger = structlog.get_logger()

APP_ENV = os.getenv("APP_ENV", "development")

INDEX_PROCEDURES = f"{APP_ENV}_procedures_v1"
INDEX_DOCTORS = f"{APP_ENV}_doctors_v1"
INDEX_REVIEWS = f"{APP_ENV}_reviews_v1"
INDEX_ALL = f"{INDEX_PROCEDURES},{INDEX_DOCTORS},{INDEX_REVIEWS}"

INDEX_ALIAS: dict[str, str] = {
    "procedures": INDEX_PROCEDURES,
    "doctors": INDEX_DOCTORS,
    "reviews": INDEX_REVIEWS,
    "all": INDEX_ALL,
}

_BM25_FIELDS: dict[str, list[str]] = {
    "procedures": ["name^3", "description^2", "category", "body_area", "tags"],
    "doctors": ["name^3", "specialty^2", "bio^2", "city", "certifications", "procedures_performed"],
    "reviews": ["title^3", "content^2", "procedure_name", "doctor_name"],
    "all": [
        "name^3",
        "title^3",
        "description^2",
        "content^2",
        "specialty^2",
        "bio^2",
        "category",
        "body_area",
    ],
}


# ---------------------------------------------------------------------------
# Filter builder
# ---------------------------------------------------------------------------


def build_filters(params: SearchParams) -> list[dict[str, Any]]:
    """Build OpenSearch filter clauses from SearchParams."""
    clauses: list[dict] = []

    def range_(field: str, gte=None, lte=None) -> None:
        r: dict = {}
        if gte is not None:
            r["gte"] = gte
        if lte is not None:
            r["lte"] = lte
        clauses.append({"range": {field: r}})

    def term(field: str, value) -> None:
        clauses.append({"term": {field: value}})

    if params.min_rating is not None:
        # procedures/doctors use 'average_rating'; reviews use 'rating' — match either
        clauses.append(
            {
                "bool": {
                    "should": [
                        {"range": {"average_rating": {"gte": params.min_rating}}},
                        {"range": {"rating": {"gte": params.min_rating}}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    if params.max_cost_usd is not None:
        range_("average_cost_usd", lte=params.max_cost_usd)
    if params.category:
        term("category", params.category)
    if params.body_area:
        term("body_area", params.body_area)
    if params.is_surgical is not None:
        term("is_surgical", params.is_surgical)
    if params.specialty:
        term("specialty", params.specialty)
    if params.min_experience is not None:
        range_("years_experience", gte=params.min_experience)
    if params.worth_it:
        term("worth_it", params.worth_it)
    if params.verified is not None:
        term("verified", params.verified)

    return clauses


# ---------------------------------------------------------------------------
# Query body builders
# ---------------------------------------------------------------------------


def build_bm25_query(query: str, index_key: str) -> dict[str, dict]:
    """Return a bare multi_match query dict (for use in rank_eval requests)."""
    return {
        "multi_match": {
            "query": query,
            "fields": _BM25_FIELDS.get(index_key, _BM25_FIELDS["all"]),
            "type": "best_fields",
            "fuzziness": "AUTO",
        }
    }


def _bm25_body(params: SearchParams, size: int, include_explain: bool = False) -> dict:
    filters = build_filters(params)
    multi_match: dict = {
        "query": params.q,
        "fields": _BM25_FIELDS.get(params.index_key, _BM25_FIELDS["all"]),
        "type": "best_fields",
        "fuzziness": "AUTO",
    }
    if filters:
        body: dict = {
            "size": size,
            "query": {"bool": {"must": {"multi_match": multi_match}, "filter": filters}},
        }
    else:
        body = {"size": size, "query": {"multi_match": multi_match}}
    if include_explain:
        body["explain"] = True
    return body


def _knn_body(vector: list[float], params: SearchParams, size: int) -> dict:
    filters = build_filters(params)
    knn_clause: dict = {"vector": vector, "k": size}
    if filters:
        knn_clause["filter"] = {"bool": {"filter": filters}}
    return {"size": size, "query": {"knn": {"embedding": knn_clause}}}


# ---------------------------------------------------------------------------
# Raw hit extractor (used by hybrid / rrf)
# ---------------------------------------------------------------------------


def _extract_raw_hits(resp: dict) -> list[dict]:
    hits = []
    for h in resp["hits"]["hits"]:
        src = h["_source"].copy()
        src.pop("embedding", None)
        hits.append(
            {
                "id": h["_id"],
                "index": h["_index"],
                "score": h["_score"] or 0.0,
                "source": src,
            }
        )
    return hits


def _extract_total(resp: dict) -> int:
    val = resp["hits"]["total"]
    return val["value"] if isinstance(val, dict) else val


# ---------------------------------------------------------------------------
# Public search functions
# ---------------------------------------------------------------------------


def search_bm25(client: OpenSearch, params: SearchParams) -> dict:
    index = INDEX_ALIAS.get(params.index_key, INDEX_ALL)
    logger.debug("search_bm25", index=index, query=params.q)
    return client.search(
        index=index, body=_bm25_body(params, params.size, include_explain=params.explain)
    )


def search_knn(client: OpenSearch, vector: list[float], params: SearchParams) -> dict:
    index = INDEX_ALIAS.get(params.index_key, INDEX_ALL)
    logger.debug("search_knn", index=index)
    return client.search(index=index, body=_knn_body(vector, params, params.size))


# Wider fetches for Python-side combination (hybrid / rrf)
def search_bm25_wide(client: OpenSearch, params: SearchParams) -> list[dict]:
    index = INDEX_ALIAS.get(params.index_key, INDEX_ALL)
    resp = client.search(index=index, body=_bm25_body(params, params.candidate_size))
    return _extract_raw_hits(resp)


def search_knn_wide(client: OpenSearch, vector: list[float], params: SearchParams) -> list[dict]:
    index = INDEX_ALIAS.get(params.index_key, INDEX_ALL)
    resp = client.search(index=index, body=_knn_body(vector, params, params.candidate_size))
    return _extract_raw_hits(resp)


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def get_document(client: OpenSearch, index_key: str, doc_id: str) -> dict | None:
    index = INDEX_ALIAS.get(index_key)
    if not index:
        return None
    try:
        return client.get(index=index, id=doc_id)
    except Exception as exc:
        logger.warning(
            "opensearch_error",
            operation="get_document",
            index=index,
            doc_id=doc_id,
            exc_type=type(exc).__name__,
            detail=str(exc),
        )
        return None


def index_document(client: OpenSearch, index_key: str, doc_id: str, body: dict) -> dict:
    index = INDEX_ALIAS.get(index_key, INDEX_PROCEDURES)
    resp = client.index(index=index, id=doc_id, body=body, refresh="wait_for")
    logger.info("document_indexed", index=index, doc_id=doc_id, result=resp.get("result"))
    return resp


def delete_document(client: OpenSearch, index_key: str, doc_id: str) -> bool:
    index = INDEX_ALIAS.get(index_key)
    if not index:
        return False
    try:
        resp = client.delete(index=index, id=doc_id, refresh="wait_for")
        logger.info("document_deleted", index=index, doc_id=doc_id, result=resp.get("result"))
        return resp.get("result") == "deleted"
    except Exception as exc:
        logger.warning(
            "opensearch_error",
            operation="delete_document",
            index=index,
            doc_id=doc_id,
            exc_type=type(exc).__name__,
            detail=str(exc),
        )
        return False


# ---------------------------------------------------------------------------
# Native OpenSearch explain API
# ---------------------------------------------------------------------------


def explain_document(
    client: OpenSearch,
    index_key: str,
    doc_id: str,
    query: str,
) -> dict:
    """Call OpenSearch _explain for a single document against a BM25 query."""
    index = INDEX_ALIAS.get(index_key, INDEX_PROCEDURES)
    body = {"query": build_bm25_query(query, index_key)}
    logger.debug("explain_document", index=index, doc_id=doc_id)
    return client.explain(index=index, id=doc_id, body=body)


# ---------------------------------------------------------------------------
# Native OpenSearch _rank_eval API
# ---------------------------------------------------------------------------


def rank_eval_native(
    client: OpenSearch,
    index_key: str,
    requests: list[dict],
    metric: dict[str, dict[str, int]],
) -> dict:
    """Call OpenSearch _rank_eval with pre-built request objects."""
    index = INDEX_ALIAS.get(index_key, INDEX_ALL)
    body: dict = {"requests": requests, "metric": metric}
    logger.debug("rank_eval_native", index=index, num_requests=len(requests))
    return client.rank_eval(body=body, index=index)
