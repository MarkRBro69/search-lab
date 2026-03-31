from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.modules.experiments.api import experiments_router
from src.modules.profiles.api import (
    close_all_opensearch_clients,
    ensure_default_profile_if_empty,
    profiles_router,
)
from src.modules.search.api import document_router, eval_router, search_router
from src.shared.exceptions import AppError, ServiceUnavailableError
from src.shared.infrastructure.embedding import init_local_embedding_model
from src.shared.infrastructure.logging import configure_logging
from src.shared.infrastructure.mongodb import close_client as close_mongo
from src.shared.infrastructure.mongodb import get_db

configure_logging()

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = structlog.get_logger()


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from the environment."""

    LOCAL_MODEL_NAME: str


settings = Settings(LOCAL_MODEL_NAME=os.getenv("LOCAL_MODEL_NAME", "all-MiniLM-L6-v2"))


class HealthResponse(BaseModel):
    status: Literal["ok"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Initialize connections and warm up models on startup."""
    log = logger.bind(module="main", operation="lifespan", request_id="-")
    log.info("app_starting")

    db = get_db()
    log.info("mongodb_client_ready")

    await ensure_default_profile_if_empty(db)

    init_local_embedding_model(settings.LOCAL_MODEL_NAME)
    log.info("embedding_model_ready", model=settings.LOCAL_MODEL_NAME)

    log.info("app_started")
    yield

    close_all_opensearch_clients()
    await close_mongo()
    log.info("app_stopped")


app = FastAPI(
    title="Search Lab",
    description="""
## Search Algorithm Evaluation Platform

A tool for comparing OpenSearch search algorithms across standardised IR metrics.

### Search algorithms
| Mode | Algorithm | Description |
|------|-----------|-------------|
| `bm25` | TF-IDF keyword | Exact name matching |
| `semantic` | KNN vector (all-MiniLM-L6-v2) | Descriptive / vague queries |
| `hybrid` | BM25 × weight + KNN × weight | General use (recommended) |
| `rrf` | Reciprocal Rank Fusion | Ensemble ranking, no manual weights |

### Evaluation metrics
All search modes return scores normalised to **[0, 1]**.
The `/eval` endpoint computes **NDCG@K, MRR, Precision@K, Recall@K** against ground-truth IDs.

### Experiment workflow
1. **Create algorithms** — `/experiments/algorithms` — named search configs (mode, weights, filters)
2. **Create query templates** — `/experiments/templates` — queries + ground-truth relevant IDs
3. **Run benchmark** — `/experiments/benchmark` — N algorithms × M templates → metrics matrix
4. **Inspect results** — per-pair NDCG, MRR, latency, score separation stored in MongoDB

---
Web UI available at [http://localhost:8000](http://localhost:8000)
""",
    version="0.1.0",
    contact={"name": "Search Lab"},
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Inject a unique request_id into every log entry for this request."""
    request_id = str(uuid.uuid4())
    with structlog.contextvars.bound_contextvars(request_id=request_id):
        response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------


def _app_error_json_content(exc: AppError) -> dict[str, str]:
    return {"detail": exc.detail, "code": exc.code}


@app.exception_handler(ServiceUnavailableError)
async def service_unavailable_handler(
    request: Request, exc: ServiceUnavailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_app_error_json_content(exc),
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_app_error_json_content(exc),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log = logger.bind(module="main", operation="unhandled_exception_handler")
    log.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc_module=getattr(exc, "module", None) or "unknown",
        exc_operation=getattr(exc, "operation", None) or "unknown",
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(search_router, prefix="/api/v1")
app.include_router(document_router, prefix="/api/v1")
app.include_router(eval_router, prefix="/api/v1")
app.include_router(experiments_router, prefix="/api/v1")
app.include_router(profiles_router, prefix="/api/v1")


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


# ---------------------------------------------------------------------------
# Static files — UI (must be last to avoid shadowing API routes)
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory="static", html=True), name="static")
