"""Unit tests for experiments_service helpers."""

from __future__ import annotations

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


def test_compute_result_empty_hits_yields_zero_separation_sensible_defaults() -> None:
    tr = _compute_result([], relevant_ids=["x"], latency_ms=0, k=10)
    assert tr.ndcg_at_k == 0.0
    assert tr.mrr == 0.0
    assert tr.score_separation == 0.0
    assert tr.total_hits == 0
    assert tr.first_relevant_position is None
    assert tr.relevant_positions == []


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
