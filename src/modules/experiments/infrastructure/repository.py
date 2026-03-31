"""MongoDB CRUD operations for the Experiments module.

Conventions:
- Each domain model is stored in its own collection.
- We map model.id → MongoDB _id so queries use _id index.
- All functions accept a Motor database instance (injected from FastAPI DI).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from src.modules.experiments.domain.models import Algorithm, BenchmarkRun, QueryTemplate

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

logger = structlog.get_logger()

_COL_ALGORITHMS = "algorithms"
_COL_TEMPLATES = "query_templates"
_COL_RUNS = "benchmark_runs"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_mongo(doc: dict) -> dict:
    """Replace 'id' key with '_id' for MongoDB storage."""
    d = dict(doc)
    d["_id"] = d.pop("id")
    return d


def _from_mongo(doc: dict | None) -> dict | None:
    """Restore 'id' from '_id' when reading from MongoDB."""
    if doc is None:
        return None
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    return d


# ---------------------------------------------------------------------------
# Algorithm repository
# ---------------------------------------------------------------------------


async def create_algorithm(db: AsyncIOMotorDatabase, algo: Algorithm) -> Algorithm:  # type: ignore[type-arg]
    await db[_COL_ALGORITHMS].insert_one(_to_mongo(algo.model_dump()))
    log = logger.bind(module="experiments", operation="create_algorithm")
    log.info("algo_created", id=algo.id, name=algo.name)
    return algo


async def list_algorithms(db: AsyncIOMotorDatabase) -> list[Algorithm]:  # type: ignore[type-arg]
    cursor = db[_COL_ALGORITHMS].find().sort("created_at", -1)
    docs = await cursor.to_list(length=200)
    return [Algorithm.model_validate(_from_mongo(d)) for d in docs]


async def get_algorithm(db: AsyncIOMotorDatabase, algo_id: str) -> Algorithm | None:  # type: ignore[type-arg]
    doc = await db[_COL_ALGORITHMS].find_one({"_id": algo_id})
    return Algorithm.model_validate(_from_mongo(doc)) if doc else None


async def delete_algorithm(db: AsyncIOMotorDatabase, algo_id: str) -> bool:  # type: ignore[type-arg]
    result = await db[_COL_ALGORITHMS].delete_one({"_id": algo_id})
    return result.deleted_count == 1


# ---------------------------------------------------------------------------
# QueryTemplate repository
# ---------------------------------------------------------------------------


async def create_template(db: AsyncIOMotorDatabase, template: QueryTemplate) -> QueryTemplate:  # type: ignore[type-arg]
    await db[_COL_TEMPLATES].insert_one(_to_mongo(template.model_dump()))
    log = logger.bind(module="experiments", operation="create_template")
    log.info("template_created", id=template.id, name=template.name)
    return template


async def list_templates(db: AsyncIOMotorDatabase) -> list[QueryTemplate]:  # type: ignore[type-arg]
    cursor = db[_COL_TEMPLATES].find().sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    return [QueryTemplate.model_validate(_from_mongo(d)) for d in docs]


async def get_template(db: AsyncIOMotorDatabase, template_id: str) -> QueryTemplate | None:  # type: ignore[type-arg]
    doc = await db[_COL_TEMPLATES].find_one({"_id": template_id})
    return QueryTemplate.model_validate(_from_mongo(doc)) if doc else None


async def update_template(db: AsyncIOMotorDatabase, template: QueryTemplate) -> QueryTemplate:  # type: ignore[type-arg]
    data = _to_mongo(template.model_dump())
    _id = data.pop("_id")
    await db[_COL_TEMPLATES].replace_one({"_id": _id}, {"_id": _id, **data})
    log = logger.bind(module="experiments", operation="update_template")
    log.info("template_updated", id=template.id)
    return template


async def delete_template(db: AsyncIOMotorDatabase, template_id: str) -> bool:  # type: ignore[type-arg]
    result = await db[_COL_TEMPLATES].delete_one({"_id": template_id})
    return result.deleted_count == 1


# ---------------------------------------------------------------------------
# BenchmarkRun repository
# ---------------------------------------------------------------------------


async def save_run(db: AsyncIOMotorDatabase, run: BenchmarkRun) -> BenchmarkRun:  # type: ignore[type-arg]
    await db[_COL_RUNS].insert_one(_to_mongo(run.model_dump()))
    log = logger.bind(module="experiments", operation="save_run")
    log.info("benchmark_run_saved", id=run.id, name=run.name)
    return run


async def list_runs(db: AsyncIOMotorDatabase) -> list[BenchmarkRun]:  # type: ignore[type-arg]
    cursor = db[_COL_RUNS].find({}, {"results": 0}).sort("created_at", -1)
    docs = await cursor.to_list(length=100)
    # results field excluded for list view — fill with empty dict for model validation
    for d in docs:
        d.setdefault("results", {})
    return [BenchmarkRun.model_validate(_from_mongo(d)) for d in docs]


async def get_run(db: AsyncIOMotorDatabase, run_id: str) -> BenchmarkRun | None:  # type: ignore[type-arg]
    doc = await db[_COL_RUNS].find_one({"_id": run_id})
    return BenchmarkRun.model_validate(_from_mongo(doc)) if doc else None


async def delete_run(db: AsyncIOMotorDatabase, run_id: str) -> bool:  # type: ignore[type-arg]
    result = await db[_COL_RUNS].delete_one({"_id": run_id})
    return result.deleted_count == 1
