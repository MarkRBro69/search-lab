"""Unit tests for experiments_service helpers."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.experiments.application.experiments_service import (
    _algo_to_params,
    _compute_result,
    _summarise,
    execute_benchmark,
    run_benchmark,
)
from src.modules.experiments.domain.models import (
    Algorithm,
    AlgoSummary,
    BenchmarkRun,
    QueryTemplate,
    TemplateResult,
)
from src.shared.exceptions import (
    ALGORITHM_NOT_FOUND,
    BENCHMARK_SIZE_LT_K,
    InvalidInputError,
    NotFoundError,
)

# Preserve real monotonic before tests patch `time.monotonic` on the shared `time` module.
_REAL_MONOTONIC = time.monotonic


def test_algo_to_params_uses_template_index() -> None:
    algo = Algorithm(name="a", mode="bm25")
    tmpl = QueryTemplate(name="t", query="hello", index="index_c")
    p = _algo_to_params(algo, tmpl, size=7)
    assert p.index_key == "index_c"


def test_algo_to_params_copies_query_from_template() -> None:
    algo = Algorithm(name="a", mode="bm25")
    tmpl = QueryTemplate(name="t", query="nose job", index="all")
    p = _algo_to_params(algo, tmpl, size=10)
    assert p.q == "nose job"
    assert p.size == 10


def test_algo_to_params_passes_generic_filters_to_search_params() -> None:
    from src.modules.experiments.domain.models import AlgorithmFilters

    algo = Algorithm(
        name="a",
        mode="bm25",
        filters=AlgorithmFilters(filter_term=["category:Books"], filter_gte=["price:10"]),
    )
    tmpl = QueryTemplate(name="t", query="hello", index="all")
    p = _algo_to_params(algo, tmpl, size=10)
    assert p.filter_term == ["category:Books"]
    assert p.filter_gte == ["price:10"]
    assert p.filter_lte == []


def test_compute_result_matches_known_ndcg_mrr_for_fixed_hits() -> None:
    hits: list[dict[str, object]] = [
        {"id": "rel", "score": 1.0},
        {"id": "other", "score": 0.5},
    ]
    tr = _compute_result(hits, relevant_ids=["rel"], latency_ms=12, k=2)
    assert tr.ndcg_at_k == 1.0
    assert tr.mrr == 1.0
    assert tr.precision_at_k == 0.5
    assert tr.recall_at_k == 1.0
    assert tr.first_relevant_position == 1
    assert tr.relevant_positions == [1]


def test_compute_result_empty_hits_yields_none_separation() -> None:
    tr = _compute_result([], relevant_ids=["x"], latency_ms=0, k=10)
    assert tr.ndcg_at_k == 0.0
    assert tr.mrr == 0.0
    assert tr.score_separation is None
    assert tr.relevant_score_mean is None
    assert tr.non_relevant_score_mean is None
    assert tr.total_hits == 0
    assert tr.first_relevant_position is None
    assert tr.relevant_positions == []


def test_compute_result_no_relevant_hit_mean_non_rel_is_overall_mean() -> None:
    hits: list[dict[str, object]] = [
        {"id": "a", "score": 0.2},
        {"id": "b", "score": 0.8},
    ]
    tr = _compute_result(hits, relevant_ids=["missing"], latency_ms=0, k=2)
    assert tr.relevant_score_mean is None
    assert tr.score_separation is None
    assert tr.non_relevant_score_mean == 0.5


def test_summarise_averages_template_results() -> None:
    t1 = TemplateResult(
        ndcg_at_k=1.0,
        mrr=0.5,
        precision_at_k=0.5,
        recall_at_k=0.5,
        latency_ms=100,
        score_min=0.0,
        score_max=1.0,
        score_mean=0.5,
        score_std=0.1,
        relevant_score_mean=1.0,
        non_relevant_score_mean=0.0,
        score_separation=1.0,
        first_relevant_position=1,
        relevant_positions=[1],
        total_hits=2,
    )
    t2 = TemplateResult(
        ndcg_at_k=0.0,
        mrr=0.5,
        precision_at_k=0.0,
        recall_at_k=0.0,
        latency_ms=200,
        score_min=0.0,
        score_max=0.0,
        score_mean=0.0,
        score_std=0.0,
        relevant_score_mean=0.0,
        non_relevant_score_mean=0.0,
        score_separation=0.0,
        first_relevant_position=None,
        relevant_positions=[],
        total_hits=0,
    )
    summary = _summarise({"u1": t1, "u2": t2})
    assert isinstance(summary, AlgoSummary)
    assert summary.avg_ndcg_at_k == 0.5
    assert summary.avg_latency_ms == 150.0
    assert summary.avg_score_separation == 0.5


def test_summarise_avg_score_separation_none_when_all_template_separations_none() -> None:
    t1 = TemplateResult(
        ndcg_at_k=0.0,
        mrr=0.0,
        precision_at_k=0.0,
        recall_at_k=0.0,
        latency_ms=10,
        score_min=0.0,
        score_max=1.0,
        score_mean=0.5,
        score_std=0.0,
        relevant_score_mean=None,
        non_relevant_score_mean=0.5,
        score_separation=None,
        first_relevant_position=None,
        relevant_positions=[],
        total_hits=1,
    )
    t2 = TemplateResult(
        ndcg_at_k=0.0,
        mrr=0.0,
        precision_at_k=0.0,
        recall_at_k=0.0,
        latency_ms=10,
        score_min=0.0,
        score_max=1.0,
        score_mean=0.5,
        score_std=0.0,
        relevant_score_mean=None,
        non_relevant_score_mean=0.5,
        score_separation=None,
        first_relevant_position=None,
        relevant_positions=[],
        total_hits=1,
    )
    summary = _summarise({"u1": t1, "u2": t2})
    assert summary.avg_score_separation is None


async def test_run_benchmark_composite_score_range_and_faster_algo_higher() -> None:
    """Lower average latency yields higher composite when other metrics match."""
    a_fast = Algorithm(name="Fast", mode="bm25")
    a_slow = Algorithm(name="Slow", mode="bm25")
    tmpl = QueryTemplate(name="T", query="q", index="all", relevant_ids=["d1"])
    hit: dict[str, object] = {"id": "d1", "score": 1.0, "index": "ix", "source": {}}

    async def fake_embed(_q: str) -> list[float]:
        return [0.0, 0.0]

    _mono_seq = [1000.0, 1000.05, 2000.0, 2000.25]
    _mono_i = 0

    def _mono() -> float:
        nonlocal _mono_i
        if _mono_i < len(_mono_seq):
            v = _mono_seq[_mono_i]
            _mono_i += 1
            return v
        return _REAL_MONOTONIC()

    with (
        patch(
            "src.modules.experiments.application.experiments_service.search",
            new_callable=AsyncMock,
            return_value={"hits": [hit]},
        ),
        patch(
            "src.modules.experiments.application.experiments_service.time.monotonic",
            side_effect=_mono,
        ),
    ):
        run = await run_benchmark(
            MagicMock(),
            [a_fast, a_slow],
            [tmpl],
            k=5,
            name="bench",
            index_alias={"all": "ix"},
            bm25_fields_by_key={"all": ["title"]},
            embed=fake_embed,
        )

    c_fast = run.summary[a_fast.id].composite_score
    c_slow = run.summary[a_slow.id].composite_score
    assert c_fast is not None and c_slow is not None
    assert 0.0 <= c_fast <= 1.0
    assert 0.0 <= c_slow <= 1.0
    assert c_fast > c_slow


async def test_run_benchmark_calls_search_per_pair_and_builds_matrix() -> None:
    a1 = Algorithm(name="A1", mode="bm25")
    a2 = Algorithm(name="A2", mode="bm25")
    t1 = QueryTemplate(name="T1", query="q1", index="all", relevant_ids=["d1"])
    t2 = QueryTemplate(name="T2", query="q2", index="all", relevant_ids=["d2"])

    hit = {"id": "d1", "score": 1.0, "index": "ix", "source": {}}

    async def fake_embed(_q: str) -> list[float]:
        return [0.0, 0.0]

    with patch(
        "src.modules.experiments.application.experiments_service.search",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = {"hits": [hit]}

        run = await run_benchmark(
            MagicMock(),
            [a1, a2],
            [t1, t2],
            k=5,
            name="bench",
            index_alias={"all": "ix"},
            bm25_fields_by_key={"all": ["title"]},
            embed=fake_embed,
        )

        assert mock_search.await_count == 4
        assert set(run.results.keys()) == {a1.id, a2.id}
        assert set(run.results[a1.id].keys()) == {t1.id, t2.id}
        assert run.summary[a1.id].avg_ndcg_at_k >= 0.0


async def test_run_benchmark_size_lt_k_raises_invalid_input() -> None:
    a1 = Algorithm(name="A", mode="bm25")
    t1 = QueryTemplate(name="T", query="q", index="all")
    with pytest.raises(InvalidInputError) as exc_info:
        await run_benchmark(
            MagicMock(),
            [a1],
            [t1],
            k=10,
            size=5,
            index_alias={"all": "ix"},
            bm25_fields_by_key={"all": ["title"]},
            embed=AsyncMock(return_value=[0.0]),
        )
    assert exc_info.value.code == BENCHMARK_SIZE_LT_K


async def test_execute_benchmark_missing_algorithm_raises_not_found() -> None:
    tmpl = QueryTemplate(name="t", query="q", index="all")
    with (
        patch(
            "src.modules.experiments.application.experiments_service.repository.get_algorithm",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.modules.experiments.application.experiments_service.repository.get_template",
            new_callable=AsyncMock,
            return_value=tmpl,
        ),
        pytest.raises(NotFoundError) as exc_info,
    ):
        await execute_benchmark(
            MagicMock(),
            MagicMock(),
            ["missing-algo-id"],
            [tmpl.id],
            k=5,
            size=5,
            name="",
            index_alias={"all": "ix"},
            bm25_fields_by_key={"all": ["t"]},
            embed=AsyncMock(return_value=[0.0]),
        )
    assert exc_info.value.code == ALGORITHM_NOT_FOUND


async def test_execute_benchmark_missing_template_raises_not_found() -> None:
    algo = Algorithm(name="a", mode="bm25")
    with (
        patch(
            "src.modules.experiments.application.experiments_service.repository.get_algorithm",
            new_callable=AsyncMock,
            return_value=algo,
        ),
        patch(
            "src.modules.experiments.application.experiments_service.repository.get_template",
            new_callable=AsyncMock,
            return_value=None,
        ),
        pytest.raises(NotFoundError) as exc_info,
    ):
        await execute_benchmark(
            MagicMock(),
            MagicMock(),
            [algo.id],
            ["missing-tmpl-id"],
            k=5,
            size=5,
            name="",
            index_alias={"all": "ix"},
            bm25_fields_by_key={"all": ["t"]},
            embed=AsyncMock(return_value=[0.0]),
        )
    from src.shared.exceptions import TEMPLATE_NOT_FOUND

    assert exc_info.value.code == TEMPLATE_NOT_FOUND


async def test_execute_benchmark_search_failure_does_not_save_run() -> None:
    algo = Algorithm(name="a", mode="bm25")
    tmpl = QueryTemplate(name="t", query="q", index="all")
    with (
        patch(
            "src.modules.experiments.application.experiments_service.repository.get_algorithm",
            new_callable=AsyncMock,
            return_value=algo,
        ),
        patch(
            "src.modules.experiments.application.experiments_service.repository.get_template",
            new_callable=AsyncMock,
            return_value=tmpl,
        ),
        patch(
            "src.modules.experiments.application.experiments_service.search",
            new_callable=AsyncMock,
            side_effect=RuntimeError("search failed"),
        ),
        patch(
            "src.modules.experiments.application.experiments_service.repository.save_run",
            new_callable=AsyncMock,
        ) as mock_save,
        pytest.raises(RuntimeError, match="search failed"),
    ):
        await execute_benchmark(
            MagicMock(),
            MagicMock(),
            [algo.id],
            [tmpl.id],
            k=5,
            size=5,
            name="n",
            index_alias={"all": "ix"},
            bm25_fields_by_key={"all": ["title"]},
            embed=AsyncMock(return_value=[0.0]),
        )
    mock_save.assert_not_awaited()


async def test_execute_benchmark_happy_path_saves_run() -> None:
    algo = Algorithm(name="a", mode="bm25")
    tmpl = QueryTemplate(name="t", query="q", index="all", relevant_ids=["d1"])
    hit: dict[str, object] = {"id": "d1", "score": 1.0, "index": "ix", "source": {}}
    saved_holder: dict[str, BenchmarkRun] = {}

    async def capture_save(_db: MagicMock, run: BenchmarkRun) -> BenchmarkRun:
        saved_holder["run"] = run
        return run

    with (
        patch(
            "src.modules.experiments.application.experiments_service.repository.get_algorithm",
            new_callable=AsyncMock,
            return_value=algo,
        ),
        patch(
            "src.modules.experiments.application.experiments_service.repository.get_template",
            new_callable=AsyncMock,
            return_value=tmpl,
        ),
        patch(
            "src.modules.experiments.application.experiments_service.search",
            new_callable=AsyncMock,
            return_value={"hits": [hit]},
        ),
        patch(
            "src.modules.experiments.application.experiments_service.repository.save_run",
            new_callable=AsyncMock,
            side_effect=capture_save,
        ) as mock_save,
    ):
        out = await execute_benchmark(
            MagicMock(),
            MagicMock(),
            [algo.id],
            [tmpl.id],
            k=5,
            size=5,
            name="bench",
            index_alias={"all": "ix"},
            bm25_fields_by_key={"all": ["title"]},
            embed=AsyncMock(return_value=[0.0]),
        )

    mock_save.assert_awaited_once()
    assert out.name == "bench"
    assert algo.id in out.results
    assert tmpl.id in out.results[algo.id]
    assert saved_holder["run"].algorithm_ids == [algo.id]
