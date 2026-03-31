"""Unit tests for IR metrics in eval_service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.search.application.eval_service import (
    evaluate,
    mrr,
    ndcg_at_k,
    precision_at_k,
    rank_eval,
    recall_at_k,
)
from src.modules.search.application.search_params import SearchParams
from src.shared.exceptions import (
    EVAL_METRIC_INCOMPLETE,
    INVALID_INDEX_KEY,
    InvalidInputError,
    UnprocessableEntityError,
)
from src.shared.search_mode import SearchMode


def test_ndcg_at_k_perfect_ranking_returns_one() -> None:
    relevant = {"only"}
    ranked = ["only", "noise1", "noise2"]
    assert ndcg_at_k(ranked, relevant, k=5) == 1.0


def test_ndcg_at_k_empty_relevant_returns_zero() -> None:
    assert ndcg_at_k(["a", "b"], set(), k=5) == 0.0


def test_mrr_first_position_returns_one() -> None:
    assert mrr(["rel", "other"], {"rel"}) == 1.0


def test_mrr_no_relevant_returns_zero() -> None:
    assert mrr(["a", "b"], {"x"}) == 0.0


def test_precision_at_k_counts_hits_in_top_k() -> None:
    ranked = ["a", "b", "c", "d"]
    relevant = {"a", "c"}
    assert precision_at_k(ranked, relevant, k=3) == 2.0 / 3.0


def test_precision_at_k_zero_k_returns_zero() -> None:
    """k=0: avoid division by zero; metric is defined as 0.0."""
    assert precision_at_k(["a", "b"], {"a"}, k=0) == 0.0


def test_precision_at_k_duplicate_ids_counted_per_position() -> None:
    """Each rank slot is evaluated independently; duplicate IDs can add multiple hits."""
    ranked = ["a", "a", "b"]
    relevant = {"a"}
    assert precision_at_k(ranked, relevant, k=3) == 2.0 / 3.0


def test_ndcg_when_more_relevant_than_k_still_bounded_by_one() -> None:
    """Ideal DCG uses at most k discounted slots; surplus relevant docs do not expand ideal past k."""
    relevant = {"a", "b", "c", "d", "e"}
    ranked = ["a", "b", "c", "x", "y"]
    n = ndcg_at_k(ranked, relevant, k=3)
    assert 0.0 <= n <= 1.0


def test_mrr_uses_full_ranked_list_not_only_first_k_slots() -> None:
    """mrr() scans the entire ranked_ids list (no k argument). Relevant only after index k-1 still counts."""
    ranked = ["noise1", "noise2", "noise3", "rel"]
    relevant = {"rel"}
    assert mrr(ranked, relevant) == 0.25


def test_recall_at_k_divides_by_relevant_size() -> None:
    ranked = ["a", "b", "c"]
    relevant = {"a", "x", "y"}
    assert recall_at_k(ranked, relevant, k=3) == 1.0 / 3.0


def test_recall_at_k_empty_relevant_returns_zero() -> None:
    assert recall_at_k(["a"], set(), k=5) == 0.0


async def test_evaluate_mocked_search_metrics_computed(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
    mock_embed: AsyncMock,
) -> None:
    params = SearchParams(q="query", mode=SearchMode.BM25, index_key="all", size=5)
    fake: dict[str, object] = {
        "hits": [
            {"id": "doc1", "score": 1.0},
            {"id": "doc2", "score": 0.5},
        ],
    }
    with patch(
        "src.modules.search.application.eval_service.search",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        out = await evaluate(
            mock_os_client,
            params,
            ["doc1"],
            index_alias,
            bm25_fields_by_key,
            mock_embed,
        )
    metrics = out["metrics"]
    assert metrics["ndcg_at_k"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["precision_at_k"] == 0.2
    assert metrics["recall_at_k"] == 1.0


async def test_evaluate_relevant_positions_match_hit_order(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
    mock_embed: AsyncMock,
) -> None:
    params = SearchParams(q="q", mode=SearchMode.BM25, index_key="all", size=5)
    fake: dict[str, object] = {
        "hits": [
            {"id": "a", "score": 1.0},
            {"id": "b", "score": 0.5},
            {"id": "c", "score": 0.3},
        ],
    }
    with patch(
        "src.modules.search.application.eval_service.search",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        out = await evaluate(
            mock_os_client,
            params,
            ["b", "c"],
            index_alias,
            bm25_fields_by_key,
            mock_embed,
        )
    assert out["relevant_positions"] == [2, 3]


async def test_evaluate_empty_hits_non_list_treated_as_empty_list(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
    mock_embed: AsyncMock,
) -> None:
    params = SearchParams(q="q", mode=SearchMode.BM25, index_key="all", size=5)
    fake: dict[str, object] = {"hits": "not_a_list"}
    with patch(
        "src.modules.search.application.eval_service.search",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        out = await evaluate(
            mock_os_client,
            params,
            ["x"],
            index_alias,
            bm25_fields_by_key,
            mock_embed,
        )
    assert out["hits"] == []
    assert out["relevant_positions"] == []


async def test_rank_eval_success_numeric_metric_non_empty_details_and_failures_str(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> None:
    raw_response: dict[str, object] = {
        "metric_score": 0.75,
        "details": {
            "q1": {
                "metric_score": 0.9,
                "unrated_docs": [{"_id": "u1"}],
            }
        },
        "failures": {"shard": "boom"},
    }
    query_inputs = [
        {
            "id": "q1",
            "query": "text",
            "ratings": [{"doc_id": "d1", "rating": 2}],
        }
    ]
    with patch(
        "src.modules.search.application.eval_service.rank_eval_native",
        return_value=raw_response,
    ):
        result = await rank_eval(
            mock_os_client,
            "all",
            query_inputs,
            5,
            "precision",
            index_alias,
            bm25_fields_by_key,
        )
    assert result["metric_score"] == 0.75
    assert result["details"]["q1"]["metric_score"] == 0.9
    assert result["details"]["q1"]["unrated_docs"] == ["u1"]
    assert result["failures"]["shard"] == "boom"


async def test_rank_eval_missing_metric_score_raises_unprocessable_entity(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> None:
    with (
        patch(
            "src.modules.search.application.eval_service.rank_eval_native",
            return_value={"details": {}, "failures": {}},
        ),
        pytest.raises(UnprocessableEntityError) as exc_info,
    ):
        await rank_eval(
            mock_os_client,
            "all",
            [{"id": "q", "query": "x", "ratings": []}],
            3,
            "precision",
            index_alias,
            bm25_fields_by_key,
        )
    assert exc_info.value.code == EVAL_METRIC_INCOMPLETE


async def test_rank_eval_non_numeric_metric_score_raises_unprocessable_entity(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    bm25_fields_by_key: dict[str, list[str]],
) -> None:
    with (
        patch(
            "src.modules.search.application.eval_service.rank_eval_native",
            return_value={"metric_score": "not_a_number", "details": {}, "failures": {}},
        ),
        pytest.raises(UnprocessableEntityError) as exc_info,
    ):
        await rank_eval(
            mock_os_client,
            "all",
            [{"id": "q", "query": "x", "ratings": []}],
            3,
            "precision",
            index_alias,
            bm25_fields_by_key,
        )
    assert exc_info.value.code == EVAL_METRIC_INCOMPLETE


async def test_rank_eval_unknown_index_key_raises_invalid_input_not_key_error(
    mock_os_client: MagicMock,
    bm25_fields_by_key: dict[str, list[str]],
) -> None:
    alias = {"all": "idx"}
    with pytest.raises(InvalidInputError) as exc_info:
        await rank_eval(
            mock_os_client,
            "unknown",
            [{"id": "q", "query": "x", "ratings": []}],
            3,
            "precision",
            alias,
            bm25_fields_by_key,
        )
    assert exc_info.value.code == INVALID_INDEX_KEY
    assert isinstance(exc_info.value, InvalidInputError)


# ---------------------------------------------------------------------------
# RankEvalRequest schema — regression: unsupported OpenSearch metrics rejected
# ---------------------------------------------------------------------------


def test_rank_eval_request_ndcg_metric_rejected() -> None:
    """Regression: ndcg is Elasticsearch-only, not supported by OpenSearch _rank_eval."""
    from pydantic import ValidationError

    from src.modules.search.presentation.schemas import (
        RankEvalQuery,
        RankEvalRating,
        RankEvalRequest,
    )

    with pytest.raises(ValidationError):
        RankEvalRequest(
            queries=[
                RankEvalQuery(id="q1", query="x", ratings=[RankEvalRating(doc_id="d1", rating=1)])
            ],
            index="my-index",
            metric="ndcg",
        )


def test_rank_eval_request_expected_reciprocal_rank_rejected() -> None:
    """Regression: expected_reciprocal_rank is not supported by OpenSearch _rank_eval."""
    from pydantic import ValidationError

    from src.modules.search.presentation.schemas import (
        RankEvalQuery,
        RankEvalRating,
        RankEvalRequest,
    )

    with pytest.raises(ValidationError):
        RankEvalRequest(
            queries=[
                RankEvalQuery(id="q1", query="x", ratings=[RankEvalRating(doc_id="d1", rating=1)])
            ],
            index="my-index",
            metric="expected_reciprocal_rank",
        )


def test_rank_eval_request_supported_metrics_accepted() -> None:
    """All four OpenSearch-supported metrics must pass schema validation."""
    from src.modules.search.presentation.schemas import (
        RankEvalQuery,
        RankEvalRating,
        RankEvalRequest,
    )

    ratings = [RankEvalRating(doc_id="d1", rating=1)]
    query = RankEvalQuery(id="q1", query="x", ratings=ratings)
    for metric in ("dcg", "precision", "recall", "mean_reciprocal_rank"):
        req = RankEvalRequest(queries=[query], index="idx", metric=metric)
        assert req.metric == metric


def test_rank_eval_request_index_all_rejected() -> None:
    """Regression: 'all' index is forbidden in rank_eval (ratings target one physical index)."""
    from pydantic import ValidationError

    from src.modules.search.presentation.schemas import (
        RankEvalQuery,
        RankEvalRating,
        RankEvalRequest,
    )

    with pytest.raises(ValidationError):
        RankEvalRequest(
            queries=[
                RankEvalQuery(id="q1", query="x", ratings=[RankEvalRating(doc_id="d1", rating=1)])
            ],
            index="all",
            metric="dcg",
        )
