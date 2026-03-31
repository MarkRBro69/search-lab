"""Unit tests for OpenSearch repository helpers and CRUD."""

from __future__ import annotations

from unittest.mock import MagicMock  # noqa: TC003

import pytest
from opensearchpy.exceptions import NotFoundError, TransportError

from src.modules.search.application.search_params import SearchParams
from src.modules.search.infrastructure.repository import (
    _bm25_body,
    _bm25_field_list,
    _extract_raw_hits,
    _extract_total,
    _knn_body,
    _resolve_index,
    build_bm25_query,
    build_filters,
    delete_document,
    explain_document,
    get_document,
    index_document,
    rank_eval_native,
    search_bm25,
    search_bm25_wide,
    search_knn,
    search_knn_wide,
)
from src.shared.exceptions import SEARCH_UNAVAILABLE, ServiceUnavailableError
from src.shared.search_mode import SearchMode


def test_resolve_index_known_key_returns_alias_value(
    index_alias: dict[str, str],
) -> None:
    assert _resolve_index("all", index_alias) == "physical-all"


def test_resolve_index_unknown_single_key_pass_through(
    index_alias: dict[str, str],
) -> None:
    assert _resolve_index("physical-name-direct", index_alias) == "physical-name-direct"


def test_resolve_index_comma_joined_logical_keys_expands_to_physical() -> None:
    """Regression: template multiselect stores comma-joined logical keys; must expand."""
    alias = {"doctors": "phys-doctors", "reviews": "phys-reviews"}
    assert _resolve_index("doctors,reviews", alias) == "phys-doctors,phys-reviews"


def test_resolve_index_comma_joined_mixed_known_unknown_passthrough_unknown() -> None:
    alias = {"doctors": "phys-doctors"}
    result = _resolve_index("doctors,unknown", alias)
    assert result == "phys-doctors,unknown"


def test_bm25_field_list_index_key_returns_fields(
    bm25_fields_by_key: dict[str, list[str]],
) -> None:
    assert _bm25_field_list("reviews", bm25_fields_by_key) == ["text"]


def test_bm25_field_list_fallback_to_all(
    bm25_fields_by_key: dict[str, list[str]],
) -> None:
    assert _bm25_field_list("unknown", bm25_fields_by_key) == ["title^2", "body"]


def test_bm25_field_list_empty_fallback_when_all_missing() -> None:
    assert _bm25_field_list("x", {"other": ["a"]}) == []


def test_bm25_field_list_comma_joined_key_returns_all_superset() -> None:
    """Regression: comma-joined logical keys (multiselect template index) use 'all' fields."""
    fields = {"all": ["title^2", "body"], "reviews": ["text"]}
    assert _bm25_field_list("reviews,doctors", fields) == ["title^2", "body"]


def test_build_filters_no_filters_returns_empty() -> None:
    p = SearchParams(q="q", mode=SearchMode.BM25, index_key="all")
    assert build_filters(p) == []


def test_build_filters_term_string_produces_term_clause() -> None:
    p = SearchParams(
        q="q", mode=SearchMode.BM25, index_key="all", filter_term=["category:Electronics"]
    )
    clauses = build_filters(p)
    assert clauses == [{"term": {"category": "Electronics"}}]


def test_build_filters_term_boolean_true_cast() -> None:
    p = SearchParams(q="q", mode=SearchMode.BM25, index_key="all", filter_term=["in_stock:true"])
    assert build_filters(p) == [{"term": {"in_stock": True}}]


def test_build_filters_term_boolean_false_cast() -> None:
    p = SearchParams(q="q", mode=SearchMode.BM25, index_key="all", filter_term=["verified:false"])
    assert build_filters(p) == [{"term": {"verified": False}}]


def test_build_filters_gte_and_lte_merged_into_single_range() -> None:
    p = SearchParams(
        q="q",
        mode=SearchMode.BM25,
        index_key="all",
        filter_gte=["price:100"],
        filter_lte=["price:500"],
    )
    clauses = build_filters(p)
    assert clauses == [{"range": {"price": {"gte": 100.0, "lte": 500.0}}}]


def test_build_filters_gte_only_range() -> None:
    p = SearchParams(q="q", mode=SearchMode.BM25, index_key="all", filter_gte=["rating:4.0"])
    assert build_filters(p) == [{"range": {"rating": {"gte": 4.0}}}]


def test_build_filters_multiple_fields_combined() -> None:
    p = SearchParams(
        q="q",
        mode=SearchMode.BM25,
        index_key="all",
        filter_term=["category:Books", "in_stock:true"],
        filter_gte=["price:10"],
    )
    clauses = build_filters(p)
    assert len(clauses) == 3


def test_build_filters_malformed_entry_skipped() -> None:
    p = SearchParams(q="q", mode=SearchMode.BM25, index_key="all", filter_term=["no-colon"])
    assert build_filters(p) == []


def test_build_bm25_query_multi_match_and_fields(
    bm25_fields_by_key: dict[str, list[str]],
) -> None:
    q = build_bm25_query("hello", "all", bm25_fields_by_key)
    mm = q["multi_match"]
    assert mm["query"] == "hello"
    assert mm["fields"] == ["title^2", "body"]
    assert mm["type"] == "best_fields"


def test_bm25_body_with_filters_bool_must_and_filter() -> None:
    p = SearchParams(
        q="q",
        mode=SearchMode.BM25,
        index_key="all",
        size=10,
        filter_term=["category:Electronics"],
    )
    body = _bm25_body(p, 7, {"all": ["t"]})
    assert body["size"] == 7
    bool_q = body["query"]["bool"]
    assert "must" in bool_q and "filter" in bool_q


def test_bm25_body_without_filters_flat_multi_match() -> None:
    p = SearchParams(q="q", mode=SearchMode.BM25, index_key="all", size=3)
    body = _bm25_body(p, 5, {"all": ["f1"]})
    assert body["size"] == 5
    assert "multi_match" in body["query"]


def test_bm25_body_explain_and_size_from_arg() -> None:
    p = SearchParams(q="q", mode=SearchMode.BM25, index_key="all", size=2, explain=True)
    body = _bm25_body(p, 9, {"all": ["f"]}, include_explain=True)
    assert body["explain"] is True
    assert body["size"] == 9


def test_knn_body_vector_k_and_filter_when_build_filters() -> None:
    p = SearchParams(
        q="q",
        mode=SearchMode.SEMANTIC,
        index_key="all",
        size=4,
        filter_term=["category:Books"],
    )
    vec = [0.1, 0.2]
    body = _knn_body(vec, p, p.size)
    knn = body["query"]["knn"]["embedding"]
    assert knn["vector"] == vec
    assert knn["k"] == 4
    assert "filter" in knn


def test_extract_raw_hits_typical_response() -> None:
    resp: dict[str, object] = {
        "hits": {
            "hits": [
                {
                    "_id": "1",
                    "_index": "i",
                    "_score": 1.5,
                    "_source": {"a": 1},
                }
            ]
        }
    }
    hits = _extract_raw_hits(resp)
    assert len(hits) == 1
    assert hits[0]["id"] == "1"
    assert hits[0]["score"] == 1.5


def test_extract_raw_hits_missing_or_wrong_nested_hits_returns_empty() -> None:
    assert _extract_raw_hits({"hits": "bad"}) == []
    assert _extract_raw_hits({"hits": {"hits": "not_list"}}) == []


def test_extract_total_dict_value_int() -> None:
    assert _extract_total({"hits": {"total": {"value": 42}}}) == 42


def test_extract_total_int() -> None:
    assert _extract_total({"hits": {"total": 7}}) == 7


def test_extract_total_float_value_returns_zero_documented() -> None:
    """OpenSearch may return float total.value; implementation maps non-int to 0."""
    assert _extract_total({"hits": {"total": {"value": 3.14}}}) == 0


def test_search_bm25_calls_client_with_expected_index_and_body(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> None:
    mock_os_client.search.return_value = {}
    p = SearchParams(q="qq", mode=SearchMode.BM25, index_key="all", size=2)
    search_bm25(mock_os_client, p, index_alias, bm25_fields_by_key)
    mock_os_client.search.assert_called_once()
    call_kw = mock_os_client.search.call_args.kwargs
    assert call_kw["index"] == "physical-all"
    assert "body" in call_kw


def test_search_knn_calls_client_with_expected_index_and_body(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    mock_os_client.search.return_value = {}
    p = SearchParams(q="q", mode=SearchMode.SEMANTIC, index_key="reviews", size=3)
    search_knn(mock_os_client, [0.1], p, index_alias)
    mock_os_client.search.assert_called_once()
    assert mock_os_client.search.call_args.kwargs["index"] == "physical-reviews"


def test_search_bm25_wide_calls_search_with_candidate_size(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> None:
    mock_os_client.search.return_value = {"hits": {"hits": []}}
    p = SearchParams(q="q", mode=SearchMode.BM25, index_key="all", size=2, num_candidates=10)
    search_bm25_wide(mock_os_client, p, index_alias, bm25_fields_by_key)
    body = mock_os_client.search.call_args.kwargs["body"]
    assert body["size"] == p.candidate_size


def test_search_knn_wide_calls_search(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    mock_os_client.search.return_value = {"hits": {"hits": []}}
    p = SearchParams(q="q", mode=SearchMode.SEMANTIC, index_key="all", size=2)
    search_knn_wide(mock_os_client, [0.0, 1.0], p, index_alias)
    mock_os_client.search.assert_called_once()


def test_search_bm25_transport_error_raises_service_unavailable(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> None:
    mock_os_client.search.side_effect = TransportError("t", {})
    p = SearchParams(q="q", mode=SearchMode.BM25, index_key="all", size=2)
    with pytest.raises(ServiceUnavailableError) as exc_info:
        search_bm25(mock_os_client, p, index_alias, bm25_fields_by_key)
    assert exc_info.value.code == SEARCH_UNAVAILABLE


def test_search_knn_transport_error_raises_service_unavailable(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    mock_os_client.search.side_effect = TransportError("t", {})
    p = SearchParams(q="q", mode=SearchMode.SEMANTIC, index_key="all", size=2)
    with pytest.raises(ServiceUnavailableError):
        search_knn(mock_os_client, [0.1], p, index_alias)


def test_search_bm25_wide_transport_error_raises_service_unavailable(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> None:
    mock_os_client.search.side_effect = TransportError("t", {})
    p = SearchParams(q="q", mode=SearchMode.BM25, index_key="all", size=2)
    with pytest.raises(ServiceUnavailableError):
        search_bm25_wide(mock_os_client, p, index_alias, bm25_fields_by_key)


def test_search_knn_wide_transport_error_raises_service_unavailable(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    mock_os_client.search.side_effect = TransportError("t", {})
    p = SearchParams(q="q", mode=SearchMode.SEMANTIC, index_key="all", size=2)
    with pytest.raises(ServiceUnavailableError):
        search_knn_wide(mock_os_client, [0.1], p, index_alias)


def test_get_document_not_found_returns_none(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    mock_os_client.get.side_effect = NotFoundError("n", {})
    assert get_document(mock_os_client, "all", "id1", index_alias) is None


def test_get_document_transport_error_raises_service_unavailable(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    mock_os_client.get.side_effect = TransportError("t", {})
    with pytest.raises(ServiceUnavailableError) as exc_info:
        get_document(mock_os_client, "all", "id1", index_alias)
    assert exc_info.value.code == SEARCH_UNAVAILABLE


def test_get_document_missing_key_in_alias_returns_none(
    mock_os_client: MagicMock,
) -> None:
    assert get_document(mock_os_client, "missing", "id", {"other": "x"}) is None


def test_index_document_unknown_index_key_raises_value_error(
    mock_os_client: MagicMock,
) -> None:
    with pytest.raises(ValueError, match="Unknown index key"):
        index_document(mock_os_client, "nope", "id", {}, {})


def test_delete_document_success_returns_true(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    mock_os_client.delete.return_value = {"result": "deleted"}
    assert delete_document(mock_os_client, "all", "d1", index_alias) is True


def test_delete_document_not_found_returns_false(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    mock_os_client.delete.side_effect = NotFoundError("n", {})
    assert delete_document(mock_os_client, "all", "d1", index_alias) is False


def test_delete_document_transport_error_raises(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    mock_os_client.delete.side_effect = TransportError("t", {})
    with pytest.raises(ServiceUnavailableError):
        delete_document(mock_os_client, "all", "d1", index_alias)


def test_explain_document_unknown_key_raises_value_error(
    mock_os_client: MagicMock,
) -> None:
    with pytest.raises(ValueError, match="Unknown index key"):
        explain_document(mock_os_client, "x", "id", "q", {}, {"all": ["t"]})


def test_explain_document_success_returns_client_explain(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> None:
    expected: dict[str, object] = {"matched": True}
    mock_os_client.explain.return_value = expected
    out = explain_document(mock_os_client, "all", "id1", "query", index_alias, bm25_fields_by_key)
    assert out == expected
    mock_os_client.explain.assert_called_once()


def test_rank_eval_native_calls_client_rank_eval(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    mock_os_client.rank_eval.return_value = {"ok": True}
    requests: list[dict[str, object]] = [{"id": "q1"}]
    metric: dict[str, dict[str, int]] = {"precision": {"k": 5}}
    rank_eval_native(mock_os_client, "all", requests, metric, index_alias)
    mock_os_client.rank_eval.assert_called_once()
    kw = mock_os_client.rank_eval.call_args.kwargs
    assert kw["index"] == "physical-all"
    body = kw["body"]
    assert body["requests"] == requests
    assert body["metric"] == metric
