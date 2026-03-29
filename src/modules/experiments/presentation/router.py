"""REST API for the Experiments module.

Endpoints
─────────
Algorithms
  POST   /experiments/algorithms          Create algorithm config
  GET    /experiments/algorithms          List all algorithm configs
  DELETE /experiments/algorithms/{id}     Delete algorithm config

Templates
  POST   /experiments/templates           Create query template
  GET    /experiments/templates           List all query templates
  PUT    /experiments/templates/{id}      Update template (e.g. add relevant IDs)
  DELETE /experiments/templates/{id}      Delete template

Benchmark
  POST   /experiments/benchmark           Start a benchmark run
  GET    /experiments/benchmark           List past runs (without per-pair details)
  GET    /experiments/benchmark/{id}      Fetch a full run with all results
  DELETE /experiments/benchmark/{id}      Delete a run
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path
from opensearchpy import OpenSearch
from pydantic import BaseModel, Field

from src.modules.experiments.application import experiments_service
from src.modules.experiments.domain.models import (
    Algorithm,
    AlgorithmFilters,
    BenchmarkRun,
    QueryTemplate,
)
from src.shared.infrastructure.mongodb import get_db
from src.shared.infrastructure.opensearch import get_client

logger = structlog.get_logger()

router = APIRouter(prefix="/experiments", tags=["experiments"])


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def _os_client() -> OpenSearch:
    return get_client()


def _db():  # type: ignore[return]
    return get_db()


OSClient = Annotated[OpenSearch, Depends(_os_client)]
MongoDb = Annotated[object, Depends(_db)]  # Motor DB — typed loosely for DI


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class AlgorithmCreate(BaseModel):
    name: str
    description: str = ""
    mode: str = "hybrid"
    bm25_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    knn_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    num_candidates: int = Field(default=50, ge=10, le=500)
    index: str = "all"
    filters: AlgorithmFilters = Field(default_factory=AlgorithmFilters)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Hybrid 30/70",
                    "description": "Balanced hybrid — BM25 30%, KNN 70%",
                    "mode": "hybrid",
                    "bm25_weight": 0.3,
                    "knn_weight": 0.7,
                    "num_candidates": 50,
                    "index": "all",
                    "filters": {},
                },
                {
                    "name": "RRF no-filter",
                    "mode": "rrf",
                    "num_candidates": 100,
                    "index": "all",
                    "filters": {},
                },
                {
                    "name": "BM25 surgical only",
                    "mode": "bm25",
                    "index": "procedures",
                    "filters": {"is_surgical": True},
                },
            ]
        }
    }


class TemplateCreate(BaseModel):
    name: str
    query: str
    index: str = "all"
    relevant_ids: list[str] = Field(default_factory=list)
    notes: str = ""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "rhinoplasty intent",
                    "query": "nose job rhinoplasty",
                    "index": "all",
                    "relevant_ids": ["abc-123", "def-456"],
                    "notes": "Marked from search UI",
                }
            ]
        }
    }


class TemplateUpdate(BaseModel):
    name: str | None = None
    query: str | None = None
    index: str | None = None
    relevant_ids: list[str] | None = None
    notes: str | None = None


class BenchmarkRequest(BaseModel):
    name: str = Field(default="", description="Optional label for this run")
    algorithm_ids: list[str] = Field(..., description="IDs of Algorithm configs to evaluate")
    template_ids: list[str] = Field(..., description="IDs of QueryTemplates to evaluate against")
    k: int = Field(default=10, ge=1, le=100, description="@K used for all metrics")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Hybrid vs RRF — cosmetic queries",
                    "algorithm_ids": ["<algo-id-1>", "<algo-id-2>"],
                    "template_ids": ["<template-id-1>", "<template-id-2>"],
                    "k": 10,
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Algorithm endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/algorithms",
    response_model=Algorithm,
    status_code=201,
    summary="Create algorithm configuration",
    description=(
        "Save a named search configuration (mode, weights, filters) that can later be "
        "used as one axis in a benchmark run."
    ),
)
async def create_algorithm(db: MongoDb, body: AlgorithmCreate) -> Algorithm:
    algo = Algorithm(**body.model_dump())
    return await experiments_service.create_algorithm(db, algo)


@router.get(
    "/algorithms",
    response_model=list[Algorithm],
    summary="List algorithm configurations",
)
async def list_algorithms(db: MongoDb) -> list[Algorithm]:
    return await experiments_service.list_algorithms(db)


@router.delete(
    "/algorithms/{algo_id}",
    status_code=204,
    summary="Delete algorithm configuration",
)
async def delete_algorithm(
    db: MongoDb,
    algo_id: str = Path(description="Algorithm ID"),
) -> None:
    deleted = await experiments_service.delete_algorithm(db, algo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Algorithm not found")


# ---------------------------------------------------------------------------
# QueryTemplate endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/templates",
    response_model=QueryTemplate,
    status_code=201,
    summary="Create query template",
    description=(
        "Save a named query with ground-truth relevant document IDs. "
        "You can create an empty template first and add `relevant_ids` later via PUT "
        "(e.g. after marking results in the search UI)."
    ),
)
async def create_template(db: MongoDb, body: TemplateCreate) -> QueryTemplate:
    template = QueryTemplate(**body.model_dump())
    return await experiments_service.create_template(db, template)


@router.get(
    "/templates",
    response_model=list[QueryTemplate],
    summary="List query templates",
)
async def list_templates(db: MongoDb) -> list[QueryTemplate]:
    return await experiments_service.list_templates(db)


@router.put(
    "/templates/{template_id}",
    response_model=QueryTemplate,
    summary="Update query template",
    description="Partial update — only supplied fields are changed.",
)
async def update_template(
    db: MongoDb,
    body: TemplateUpdate,
    template_id: str = Path(description="Template ID"),
) -> QueryTemplate:
    from src.modules.experiments.infrastructure.repository import get_template

    existing = await get_template(db, template_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Template not found")

    updated = existing.model_copy(
        update={k: v for k, v in body.model_dump().items() if v is not None}
    )
    return await experiments_service.update_template(db, updated)


@router.delete(
    "/templates/{template_id}",
    status_code=204,
    summary="Delete query template",
)
async def delete_template(
    db: MongoDb,
    template_id: str = Path(description="Template ID"),
) -> None:
    deleted = await experiments_service.delete_template(db, template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")


# ---------------------------------------------------------------------------
# Benchmark endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/benchmark",
    response_model=BenchmarkRun,
    status_code=201,
    summary="Run benchmark",
    description="""
Execute a full N × M evaluation matrix:

- **N** algorithm configurations × **M** query templates
- All pairs run concurrently for speed
- Each pair returns: NDCG@K, MRR, Precision@K, Recall@K, latency,
  score distribution stats, **score_separation** (relevant vs non-relevant gap),
  and ranked positions of relevant documents

The result is persisted in MongoDB and can be retrieved later.
""",
)
async def run_benchmark(
    db: MongoDb,
    client: OSClient,
    body: BenchmarkRequest,
) -> BenchmarkRun:
    try:
        return await experiments_service.execute_benchmark(
            db=db,
            os_client=client,
            algorithm_ids=body.algorithm_ids,
            template_ids=body.template_ids,
            k=body.k,
            name=body.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/benchmark",
    response_model=list[BenchmarkRun],
    summary="List benchmark runs",
    description="Returns metadata and summary for all past runs. Per-pair `results` are omitted for brevity.",
)
async def list_runs(db: MongoDb) -> list[BenchmarkRun]:
    return await experiments_service.list_runs(db)


@router.get(
    "/benchmark/{run_id}",
    response_model=BenchmarkRun,
    summary="Get full benchmark run",
    description="Fetch a complete run including per-pair TemplateResult analytics.",
)
async def get_run(
    db: MongoDb,
    run_id: str = Path(description="Benchmark run ID"),
) -> BenchmarkRun:
    run = await experiments_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.delete(
    "/benchmark/{run_id}",
    status_code=204,
    summary="Delete benchmark run",
)
async def delete_run(
    db: MongoDb,
    run_id: str = Path(description="Benchmark run ID"),
) -> None:
    deleted = await experiments_service.delete_run(db, run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Run not found")
