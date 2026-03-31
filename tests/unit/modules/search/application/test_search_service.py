"""Unit tests for search_service.search() — each mode tested with mocked executor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.experiments.application.experiments_service import _compute_result
from src.modules.search.application.eval_service import evaluate
from src.modules.search.application.search_params import SearchParams
from src.modules.search.application.search_service import (
    _parse_hits,
    explain_document_async,
    search,
)
from src.shared.exceptions import SEARCH_INVALID_MODE, InvalidInputError
from src.shared.search_mode import SearchMode


def _make_raw_response(hits: list[dict] | None = None) -> dict:
    """Build a minimal OpenSearch response dict."""
    hits = hits or []
    return {
        "hits": {
            "total": {"value": len(hits)},
            "hits": hits,
        }
    }


def _raw_hit(doc_id: str, score: float = 1.0) -> dict:
    return {"_id": doc_id, "_index": "test-idx", "_score": score, "_source": {"title": doc_id}}


def _extracted_wide_hit(doc_id: str, score: float = 1.0) -> dict[str, object]:
    """Shape returned by search_bm25_wide / search_knn_wide (_extract_raw_hits)."""
    return {
        "id": doc_id,
        "index": "test-idx",
        "score": score,
        "source": {"title": doc_id},
    }


@pytest.fixture
def os_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def embed() -> AsyncMock:
    return AsyncMock(return_value=[0.1] * 384)


@pytest.fixture
def index_alias() -> dict[str, str]:
    return {"all": "test-idx"}


@pytest.fixture
def bm25_fields() -> dict[str, list[str]]:
    return {"all": ["title", "body"]}


@pytest.fixture
def bm25_params(index_alias: dict, bm25_fields: dict) -> tuple:
    params = SearchParams(q="hello", mode=SearchMode.BM25, index_key="all", size=5)
    return params, index_alias, bm25_fields


def test_parse_hits_normalizes_numeric_id_to_str() -> None:
    raw = _make_raw_response(
        [
            {
                "_id": 42,
                "_index": "test-idx",
                "_score": 1.0,
                "_source": {"title": "x"},
            }
        ]
    )
    _total, hits = _parse_hits(raw)
    assert len(hits) == 1
    assert hits[0]["id"] == "42"
    assert isinstance(hits[0]["id"], str)


async def test_eval_and_experiments_metrics_match_for_same_hits() -> None:
    """Same hit list and k → identical IR metrics from eval_service.evaluate vs experiments _compute_result."""
    params = SearchParams(q="q", mode=SearchMode.BM25, index_key="all", size=3)
    hits: list[dict[str, object]] = [
        {"id": "1", "score": 1.0, "index": "ix", "source": {}},
        {"id": "2", "score": 0.5, "index": "ix", "source": {}},
    ]
    fake: dict[str, object] = {"hits": hits}
    relevant = ["1"]

    with patch(
        "src.modules.search.application.eval_service.search",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        ev = await evaluate(
            MagicMock(),
            params,
            relevant,
            {"all": "ix"},
            {"all": ["title"]},
            AsyncMock(return_value=[0.0]),
        )
    tr = _compute_result(hits, relevant, latency_ms=0, k=3)
    assert ev["metrics"]["ndcg_at_k"] == tr.ndcg_at_k
    assert ev["metrics"]["mrr"] == tr.mrr
    assert ev["metrics"]["precision_at_k"] == tr.precision_at_k
    assert ev["metrics"]["recall_at_k"] == tr.recall_at_k


async def test_search_bm25_calls_search_bm25_and_returns_response(
    os_client: MagicMock,
    embed: AsyncMock,
    index_alias: dict,
    bm25_fields: dict,
) -> None:
    params = SearchParams(q="hello", mode=SearchMode.BM25, index_key="all", size=2)
    raw = _make_raw_response([_raw_hit("a", 2.0), _raw_hit("b", 1.0)])

    with patch(
        "src.modules.search.application.search_service.search_bm25", return_value=raw
    ) as mock_bm25:
        result = await search(os_client, params, index_alias, bm25_fields, embed)

    mock_bm25.assert_called_once()
    embed.assert_not_called()
    assert result["mode"] == SearchMode.BM25
    assert result["total"] == 2
    assert len(result["hits"]) == 2


async def test_search_semantic_calls_embed_and_search_knn(
    os_client: MagicMock,
    embed: AsyncMock,
    index_alias: dict,
    bm25_fields: dict,
) -> None:
    params = SearchParams(q="query", mode=SearchMode.SEMANTIC, index_key="all", size=3)
    raw = _make_raw_response([_raw_hit("x", 0.9)])

    with patch("src.modules.search.application.search_service.search_knn", return_value=raw):
        result = await search(os_client, params, index_alias, bm25_fields, embed)

    embed.assert_awaited_once_with("query")
    assert result["mode"] == SearchMode.SEMANTIC
    assert result["total"] == 1


async def test_search_hybrid_calls_bm25_wide_and_knn_wide(
    os_client: MagicMock,
    embed: AsyncMock,
    index_alias: dict,
    bm25_fields: dict,
) -> None:
    params = SearchParams(q="q", mode=SearchMode.HYBRID, index_key="all", size=2)
    bm25_wide = [
        _extracted_wide_hit("a", 1.5),
        _extracted_wide_hit("b", 0.5),
    ]
    knn_wide = [
        _extracted_wide_hit("b", 0.9),
        _extracted_wide_hit("c", 0.7),
    ]

    with (
        patch(
            "src.modules.search.application.search_service.search_bm25_wide",
            return_value=bm25_wide,
        ),
        patch(
            "src.modules.search.application.search_service.search_knn_wide",
            return_value=knn_wide,
        ),
    ):
        result = await search(os_client, params, index_alias, bm25_fields, embed)

    embed.assert_awaited_once()
    assert result["mode"] == SearchMode.HYBRID
    assert len(result["hits"]) <= 2


async def test_search_rrf_calls_bm25_wide_and_knn_wide(
    os_client: MagicMock,
    embed: AsyncMock,
    index_alias: dict,
    bm25_fields: dict,
) -> None:
    params = SearchParams(q="q", mode=SearchMode.RRF, index_key="all", size=2)
    bm25_wide = [
        _extracted_wide_hit("a", 2.0),
        _extracted_wide_hit("b", 1.0),
    ]
    knn_wide = [
        _extracted_wide_hit("b", 0.8),
        _extracted_wide_hit("c", 0.6),
    ]

    with (
        patch(
            "src.modules.search.application.search_service.search_bm25_wide",
            return_value=bm25_wide,
        ),
        patch(
            "src.modules.search.application.search_service.search_knn_wide",
            return_value=knn_wide,
        ),
    ):
        result = await search(os_client, params, index_alias, bm25_fields, embed)

    embed.assert_awaited_once()
    assert result["mode"] == SearchMode.RRF
    assert len(result["hits"]) <= 2


async def test_search_unknown_mode_raises_invalid_input_error(
    os_client: MagicMock,
    embed: AsyncMock,
    index_alias: dict,
    bm25_fields: dict,
) -> None:
    params = SearchParams(q="q", mode="bm25", index_key="all")
    object.__setattr__(params, "mode", "bad_mode")  # bypass dataclass to inject invalid mode

    with pytest.raises(InvalidInputError) as exc_info:
        await search(os_client, params, index_alias, bm25_fields, embed)

    assert exc_info.value.code == SEARCH_INVALID_MODE


async def test_explain_document_async_run_in_executor_returns_explain_dict(
    os_client: MagicMock,
    index_alias: dict,
    bm25_fields: dict,
) -> None:
    expected: dict[str, object] = {"matched": True, "explanation": {"value": 1}}
    with patch(
        "src.modules.search.application.search_service.explain_document",
        return_value=expected,
    ) as mock_explain:
        result = await explain_document_async(
            os_client,
            "all",
            "doc-1",
            "why",
            index_alias,
            bm25_fields,
        )
    mock_explain.assert_called_once()
    assert result == expected
