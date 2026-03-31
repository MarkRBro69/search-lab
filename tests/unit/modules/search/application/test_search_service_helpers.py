"""Unit tests for search_service private helpers."""

from __future__ import annotations

from src.modules.search.application.search_params import SearchParams
from src.modules.search.application.search_service import (
    _hybrid_combine,
    _minmax,
    _parse_hits,
    _rrf_combine,
)
from src.shared.search_mode import SearchMode


def test_parse_hits_extracts_id_index_score_source_strips_embedding() -> None:
    raw: dict[str, object] = {
        "hits": {
            "total": {"value": 2},
            "hits": [
                {
                    "_id": "doc1",
                    "_index": "my-index",
                    "_score": 2.5,
                    "_source": {"title": "x", "embedding": [0.1, 0.2]},
                },
            ],
        },
    }
    total, hits = _parse_hits(raw)
    assert total == 2
    assert len(hits) == 1
    h = hits[0]
    assert h["id"] == "doc1"
    assert h["index"] == "my-index"
    assert h["score"] == 2.5
    src = h["source"]
    assert isinstance(src, dict)
    assert src.get("title") == "x"
    assert "embedding" not in src


def test_parse_hits_returns_empty_list_when_hits_missing() -> None:
    """Inner hits list absent — treat as no hits (not a KeyError on outer 'hits')."""
    raw: dict[str, object] = {
        "hits": {
            "total": 0,
        },
    }
    total, hits = _parse_hits(raw)
    assert total == 0
    assert hits == []


def test_minmax_normalizes_scores_in_place() -> None:
    hits: list[dict[str, object]] = [
        {"id": "a", "score": 10.0},
        {"id": "b", "score": 20.0},
    ]
    _minmax(hits)
    assert hits[0]["score"] == 0.0
    assert hits[1]["score"] == 1.0


def test_minmax_noop_on_empty_hits() -> None:
    hits: list[dict[str, object]] = []
    _minmax(hits)
    assert hits == []


def test_minmax_all_equal_scores_sets_all_one() -> None:
    hits: list[dict[str, object]] = [
        {"id": "a", "score": 5.0},
        {"id": "b", "score": 5.0},
    ]
    _minmax(hits)
    assert hits[0]["score"] == 1.0
    assert hits[1]["score"] == 1.0


def test_hybrid_combine_weighted_sum_and_respects_size() -> None:
    # Asymmetric ranks: BM25 favors `a`, KNN favors `b` — with knn_weight=0.7, `b` wins top-1.
    bm25: list[dict[str, object]] = [
        {"id": "a", "index": "i", "score": 10.0, "source": {"x": 1}},
        {"id": "b", "index": "i", "score": 5.0, "source": {"x": 2}},
    ]
    knn: list[dict[str, object]] = [
        {"id": "b", "index": "i", "score": 1.0, "source": {"x": 2}},
        {"id": "a", "index": "i", "score": 0.0, "source": {"x": 1}},
    ]
    params = SearchParams(
        q="q",
        mode="hybrid",
        index_key="all",
        size=1,
        bm25_weight=0.3,
        knn_weight=0.7,
        explain=False,
    )
    out = _hybrid_combine(bm25, knn, params)
    assert len(out) == 1
    assert out[0]["id"] == "b"


def test_hybrid_combine_includes_score_breakdown_when_explain_true() -> None:
    bm25: list[dict[str, object]] = [
        {"id": "a", "index": "i", "score": 1.0, "source": {}},
    ]
    knn: list[dict[str, object]] = [
        {"id": "a", "index": "i", "score": 1.0, "source": {}},
    ]
    params = SearchParams(
        q="q",
        mode="hybrid",
        index_key="all",
        size=10,
        explain=True,
    )
    out = _hybrid_combine(bm25, knn, params)
    assert len(out) == 1
    br = out[0].get("score_breakdown")
    assert isinstance(br, dict)
    assert br.get("bm25_rank") == 1
    assert br.get("knn_rank") == 1
    assert br.get("bm25_rank_score") == 1.0
    assert br.get("knn_rank_score") == 1.0


def test_rrf_combine_orders_by_reciprocal_rank_fusion() -> None:
    # Asymmetric lists: `b` is strong in both; `a` only BM25; `c` only KNN — `b` wins RRF.
    bm25: list[dict[str, object]] = [
        {"id": "a", "index": "i", "score": 1.0, "source": {}},
        {"id": "b", "index": "i", "score": 0.9, "source": {}},
    ]
    knn: list[dict[str, object]] = [
        {"id": "b", "index": "i", "score": 1.0, "source": {}},
        {"id": "c", "index": "i", "score": 0.9, "source": {}},
    ]
    params = SearchParams(q="q", mode="rrf", index_key="all", size=10)
    out = _rrf_combine(bm25, knn, params)
    assert [str(d["id"]) for d in out] == ["b", "a", "c"]


def test_hybrid_combine_both_hit_lists_empty_returns_empty() -> None:
    params = SearchParams(
        q="q",
        mode=SearchMode.HYBRID,
        index_key="all",
        size=10,
    )
    assert _hybrid_combine([], [], params) == []


def test_rrf_combine_both_empty_returns_empty_within_size() -> None:
    params = SearchParams(q="q", mode=SearchMode.RRF, index_key="all", size=5)
    assert _rrf_combine([], [], params) == []


def test_rrf_combine_respects_size_limit() -> None:
    bm25: list[dict[str, object]] = [
        {"id": "a", "index": "i", "score": 1.0, "source": {}},
        {"id": "b", "index": "i", "score": 0.9, "source": {}},
    ]
    knn: list[dict[str, object]] = [
        {"id": "a", "index": "i", "score": 1.0, "source": {}},
        {"id": "b", "index": "i", "score": 0.9, "source": {}},
    ]
    params = SearchParams(q="q", mode="rrf", index_key="all", size=1)
    out = _rrf_combine(bm25, knn, params)
    assert len(out) == 1


def _assert_scores_minmax(hits: list[dict[str, object]]) -> None:
    for h in hits:
        sc = float(h["score"])
        assert 0.0 <= sc <= 1.0


def test_minmax_applied_to_all_modes_rrf_and_hybrid() -> None:
    """After combine + _minmax, all returned scores lie in [0, 1]."""
    bm25: list[dict[str, object]] = [
        {"id": "a", "index": "i", "score": 1.0, "source": {}},
        {"id": "b", "index": "i", "score": 0.9, "source": {}},
    ]
    knn: list[dict[str, object]] = [
        {"id": "b", "index": "i", "score": 1.0, "source": {}},
        {"id": "a", "index": "i", "score": 0.9, "source": {}},
    ]
    rrf_params = SearchParams(q="q", mode="rrf", index_key="all", size=10)
    rrf_hits = _rrf_combine(bm25, knn, rrf_params)
    _minmax(rrf_hits)
    _assert_scores_minmax(rrf_hits)

    hybrid_params = SearchParams(
        q="q",
        mode="hybrid",
        index_key="all",
        size=10,
        bm25_weight=0.3,
        knn_weight=0.7,
        explain=False,
    )
    hybrid_hits = _hybrid_combine(bm25, knn, hybrid_params)
    _minmax(hybrid_hits)
    _assert_scores_minmax(hybrid_hits)


def test_minmax_single_hit_sets_score_one() -> None:
    hits: list[dict[str, object]] = [{"id": "only", "score": 123.45}]
    _minmax(hits)
    assert hits[0]["score"] == 1.0
