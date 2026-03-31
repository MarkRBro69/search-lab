"""Unit tests for experiments domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.modules.experiments.domain.models import Algorithm, AlgorithmFilters, QueryTemplate


def test_algorithm_bm25_weight_out_of_range_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        Algorithm(name="n", bm25_weight=1.5)


def test_algorithm_num_candidates_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        Algorithm(name="n", num_candidates=5)
    with pytest.raises(ValidationError):
        Algorithm(name="n", num_candidates=501)


def test_algorithm_bm25_knn_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError):
        Algorithm(name="n", bm25_weight=0.6, knn_weight=0.6)


def test_query_template_accepts_empty_relevant_ids() -> None:
    t = QueryTemplate(name="n", query="q", relevant_ids=[])
    assert t.relevant_ids == []


# ---------------------------------------------------------------------------
# AlgorithmFilters — regression: domain-agnostic generic format
# ---------------------------------------------------------------------------


def test_algorithm_filters_defaults_are_empty_lists() -> None:
    """Regression: AlgorithmFilters uses generic filter_term/gte/lte, not domain fields."""
    f = AlgorithmFilters()
    assert f.filter_term == []
    assert f.filter_gte == []
    assert f.filter_lte == []


def test_algorithm_filters_accepts_generic_filter_format() -> None:
    f = AlgorithmFilters(
        filter_term=["category:Books", "in_stock:true"],
        filter_gte=["price:10"],
        filter_lte=["price:500"],
    )
    assert f.filter_term == ["category:Books", "in_stock:true"]
    assert f.filter_gte == ["price:10"]
    assert f.filter_lte == ["price:500"]


def test_algorithm_filters_old_domain_fields_are_silently_ignored() -> None:
    """Regression: old MongoDB docs with domain-specific fields must load without error."""
    f = AlgorithmFilters.model_validate(
        {"min_rating": 4.0, "is_surgical": True, "category": "cosmetic"}
    )
    assert f.filter_term == []
    assert f.filter_gte == []
    assert f.filter_lte == []
