"""Unit tests for SearchParams."""

from __future__ import annotations

import pytest

from src.modules.search.application.search_params import SearchParams, _split_pair
from src.shared.search_mode import SearchMode

# ── _split_pair helper ────────────────────────────────────────────────────────


def test_split_pair_valid_returns_field_and_value() -> None:
    assert _split_pair("category:Electronics") == ("category", "Electronics")


def test_split_pair_value_with_colon_splits_on_first_only() -> None:
    assert _split_pair("url:https://example.com") == ("url", "https://example.com")


def test_split_pair_no_colon_returns_none() -> None:
    assert _split_pair("no-colon-here") is None


def test_split_pair_leading_colon_returns_none() -> None:
    assert _split_pair(":value") is None


def test_split_pair_trims_whitespace() -> None:
    assert _split_pair("  field : value  ") == ("field", "value")


# ── candidate_size ────────────────────────────────────────────────────────────


def test_candidate_size_returns_max_of_size_times_three_and_num_candidates() -> None:
    p = SearchParams(q="x", mode="bm25", index_key="all", size=10, num_candidates=50)
    assert p.candidate_size == max(30, 50) == 50


def test_candidate_size_when_size_large_exceeds_num_candidates() -> None:
    p = SearchParams(q="x", mode="bm25", index_key="all", size=40, num_candidates=50)
    assert p.candidate_size == max(120, 50) == 120


# ── has_filters ───────────────────────────────────────────────────────────────


def test_has_filters_false_when_empty() -> None:
    p = SearchParams(q="x", mode="bm25", index_key="all")
    assert p.has_filters() is False


def test_has_filters_true_with_filter_term() -> None:
    p = SearchParams(q="x", mode="bm25", index_key="all", filter_term=["category:A"])
    assert p.has_filters() is True


def test_has_filters_true_with_filter_gte() -> None:
    p = SearchParams(q="x", mode="bm25", index_key="all", filter_gte=["price:100"])
    assert p.has_filters() is True


# ── active_filters ────────────────────────────────────────────────────────────


def test_active_filters_empty_when_no_filters() -> None:
    p = SearchParams(q="x", mode="bm25", index_key="all")
    assert p.active_filters() == {}


def test_active_filters_term_filter_echoed_with_equals_prefix() -> None:
    p = SearchParams(q="x", mode="bm25", index_key="all", filter_term=["category:Electronics"])
    assert p.active_filters() == {"=category": "Electronics"}


def test_active_filters_gte_uses_gte_prefix() -> None:
    p = SearchParams(q="x", mode="bm25", index_key="all", filter_gte=["price:100"])
    assert p.active_filters() == {">=price": "100"}


def test_active_filters_lte_uses_lte_prefix() -> None:
    p = SearchParams(q="x", mode="bm25", index_key="all", filter_lte=["price:500"])
    assert p.active_filters() == {"<=price": "500"}


def test_active_filters_multiple_types_combined() -> None:
    p = SearchParams(
        q="x",
        mode="hybrid",
        index_key="idx",
        filter_term=["category:Books", "in_stock:true"],
        filter_gte=["rating:4.0"],
        filter_lte=["price:50"],
    )
    result = p.active_filters()
    assert result == {
        "=category": "Books",
        "=in_stock": "true",
        ">=rating": "4.0",
        "<=price": "50",
    }


def test_active_filters_skips_malformed_entries() -> None:
    p = SearchParams(q="x", mode="bm25", index_key="all", filter_term=["no-colon", "ok:val"])
    assert p.active_filters() == {"=ok": "val"}


def test_search_params_hybrid_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="must equal 1.0"):
        SearchParams(
            q="x",
            mode=SearchMode.HYBRID,
            index_key="all",
            bm25_weight=0.6,
            knn_weight=0.6,
        )
