from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.modules.experiments.api import experiments_router
from src.modules.search.api import document_router, eval_router, search_router
from src.shared.infrastructure.embedding import get_model
from src.shared.infrastructure.mongodb import close_client as close_mongo
from src.shared.infrastructure.mongodb import get_db
from src.shared.infrastructure.opensearch import close_client_sync, get_client

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Initialize connections and warm up models on startup."""
    logger.info("app_starting")

    get_client()
    logger.info("opensearch_client_ready")

    get_db()
    logger.info("mongodb_client_ready")

    # Warm up embedding model in background (CPU-bound, runs in thread on first search)
    # Uncomment to pre-load at startup (slower boot, faster first request):
    # await asyncio.to_thread(get_model)
    get_model()
    logger.info("embedding_model_ready")

    logger.info("app_started")
    yield

    close_client_sync()
    await close_mongo()
    logger.info("app_stopped")


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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", exc_type=type(exc).__name__, detail=str(exc))
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(search_router, prefix="/api/v1")
app.include_router(document_router, prefix="/api/v1")
app.include_router(eval_router, prefix="/api/v1")
app.include_router(experiments_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Static files — UI (must be last to avoid shadowing API routes)
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory="static", html=True), name="static")
