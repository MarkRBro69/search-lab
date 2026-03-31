"""Unit tests for experiments MongoDB repository (mocked Motor)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from src.modules.experiments.domain.models import (
    Algorithm,
    BenchmarkRun,
    QueryTemplate,
    TemplateResult,
)
from src.modules.experiments.infrastructure import repository
from src.shared.search_mode import SearchMode


def _sample_template_result() -> TemplateResult:
    return TemplateResult(
        ndcg_at_k=1.0,
        mrr=1.0,
        precision_at_k=1.0,
        recall_at_k=1.0,
        latency_ms=10,
        score_min=0.0,
        score_max=1.0,
        score_mean=0.5,
        score_std=0.1,
        relevant_score_mean=1.0,
        non_relevant_score_mean=0.0,
        score_separation=1.0,
        first_relevant_position=1,
        relevant_positions=[1],
        total_hits=1,
    )


def test_to_mongo_from_mongo_round_trip_algorithm() -> None:
    algo = Algorithm(name="n", mode=SearchMode.BM25)
    raw = algo.model_dump()
    back = repository._from_mongo(repository._to_mongo(raw))
    assert back is not None
    algo2 = Algorithm.model_validate(back)
    assert algo2.id == algo.id
    assert algo2.name == "n"
    assert algo2.mode == SearchMode.BM25


def test_to_mongo_from_mongo_round_trip_query_template() -> None:
    tmpl = QueryTemplate(name="t", query="q", relevant_ids=["a", "b"])
    raw = tmpl.model_dump()
    back = repository._from_mongo(repository._to_mongo(raw))
    assert back is not None
    t2 = QueryTemplate.model_validate(back)
    assert t2.id == tmpl.id
    assert t2.relevant_ids == ["a", "b"]


def test_to_mongo_from_mongo_round_trip_benchmark_run() -> None:
    tr = _sample_template_result()
    aid = "algo-1"
    tid = "tmpl-1"
    run = BenchmarkRun(
        name="run",
        k=5,
        size=5,
        algorithm_ids=[aid],
        template_ids=[tid],
        results={aid: {tid: tr}},
        summary={},
    )
    raw = run.model_dump()
    back = repository._from_mongo(repository._to_mongo(raw))
    assert back is not None
    r2 = BenchmarkRun.model_validate(back)
    assert r2.results[aid][tid].ndcg_at_k == tr.ndcg_at_k


def _db_with_collection(name: str, coll: AsyncMock) -> MagicMock:
    db = MagicMock()

    def getitem(key: str) -> AsyncMock:
        if key == name:
            return coll
        return AsyncMock()

    db.__getitem__.side_effect = getitem
    return db


async def test_save_algorithm_calls_insert_one_with_id_as_underscore() -> None:
    coll = AsyncMock()
    coll.insert_one = AsyncMock()
    db = _db_with_collection(repository._COL_ALGORITHMS, coll)
    algo = Algorithm(name="x", mode=SearchMode.BM25)
    await repository.create_algorithm(db, algo)
    coll.insert_one.assert_awaited_once()
    doc = coll.insert_one.call_args[0][0]
    assert doc["_id"] == algo.id
    assert "id" not in doc


async def test_get_algorithm_found_and_not_found() -> None:
    algo = Algorithm(name="x", mode=SearchMode.BM25)
    dumped = repository._to_mongo(algo.model_dump())
    coll = AsyncMock()
    coll.find_one = AsyncMock(side_effect=[dumped, None])
    db = _db_with_collection(repository._COL_ALGORITHMS, coll)
    got = await repository.get_algorithm(db, algo.id)
    assert got is not None
    assert got.id == algo.id
    missing = await repository.get_algorithm(db, "nope")
    assert missing is None


async def test_list_algorithms_returns_models() -> None:
    algo = Algorithm(name="x", mode=SearchMode.BM25)
    doc = repository._to_mongo(algo.model_dump())
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[doc])
    coll = AsyncMock()
    coll.find = MagicMock(return_value=cursor)
    db = _db_with_collection(repository._COL_ALGORITHMS, coll)
    out = await repository.list_algorithms(db)
    assert len(out) == 1
    assert out[0].name == "x"


async def test_save_template_get_template_list_templates() -> None:
    tmpl = QueryTemplate(name="t", query="q")
    coll = AsyncMock()
    coll.insert_one = AsyncMock()
    db = _db_with_collection(repository._COL_TEMPLATES, coll)
    await repository.create_template(db, tmpl)
    coll.insert_one.assert_awaited_once()

    doc = repository._to_mongo(tmpl.model_dump())
    coll2 = AsyncMock()
    coll2.find_one = AsyncMock(side_effect=[doc, None])
    db2 = _db_with_collection(repository._COL_TEMPLATES, coll2)
    assert (await repository.get_template(db2, tmpl.id)) is not None
    assert await repository.get_template(db2, "missing") is None

    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[doc])
    coll3 = AsyncMock()
    coll3.find = MagicMock(return_value=cursor)
    db3 = _db_with_collection(repository._COL_TEMPLATES, coll3)
    listed = await repository.list_templates(db3)
    assert len(listed) == 1


async def test_save_run_get_run_list_runs_projection() -> None:
    tr = _sample_template_result()
    run = BenchmarkRun(
        name="r",
        k=3,
        size=3,
        algorithm_ids=["a1"],
        template_ids=["t1"],
        results={"a1": {"t1": tr}},
        summary={},
    )
    coll = AsyncMock()
    coll.insert_one = AsyncMock()
    db = _db_with_collection(repository._COL_RUNS, coll)
    await repository.save_run(db, run)
    coll.insert_one.assert_awaited_once()

    full_doc = repository._to_mongo(run.model_dump())
    coll2 = AsyncMock()
    coll2.find_one = AsyncMock(return_value=full_doc)
    db2 = _db_with_collection(repository._COL_RUNS, coll2)
    got = await repository.get_run(db2, run.id)
    assert got is not None
    assert got.results["a1"]["t1"].mrr == tr.mrr

    list_doc = {
        "_id": run.id,
        "name": run.name,
        "created_at": datetime.now(UTC),
        "k": run.k,
        "size": run.size,
        "algorithm_ids": run.algorithm_ids,
        "template_ids": run.template_ids,
        "summary": {},
    }
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[list_doc])
    coll3 = AsyncMock()
    coll3.find = MagicMock(return_value=cursor)
    db3 = _db_with_collection(repository._COL_RUNS, coll3)
    await repository.list_runs(db3)
    coll3.find.assert_called_once_with({}, {"results": 0})
