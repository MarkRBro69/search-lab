"""Evaluation router — offline relevance metrics for search experiments."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from opensearchpy import OpenSearch
from pydantic import BaseModel, Field

from src.modules.search.application.eval_service import evaluate, rank_eval
from src.modules.search.application.search_params import SearchParams
from src.modules.search.presentation.schemas import (
    RankEvalQueryResult,
    RankEvalRequest,
    RankEvalResponse,
)
from src.shared.infrastructure.opensearch import get_client

router = APIRouter(prefix="/eval", tags=["eval"])


def _os_client() -> OpenSearch:
    return get_client()


OSClient = Annotated[OpenSearch, Depends(_os_client)]


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class EvalRequest(BaseModel):
    """Evaluation request — run a search and compare results to known relevant documents."""

    query: str = Field(..., min_length=1, description="Search query text")
    relevant_ids: list[str] = Field(
        ..., min_length=1, description="IDs of documents considered relevant"
    )

    # Search params (mirrors GET /search)
    mode: str = Field("hybrid", description="bm25 | semantic | hybrid | rrf")
    index: str = Field("all", description="all | procedures | doctors | reviews")
    k: int = Field(10, ge=1, le=50, description="Evaluate top-K results")
    bm25_weight: float = Field(0.3, ge=0.0, le=1.0)
    knn_weight: float = Field(0.7, ge=0.0, le=1.0)
    num_candidates: int = Field(50, ge=10, le=500)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "rhinoplasty nose reshaping",
                    "relevant_ids": [
                        "0ec37382-9f2b-447e-b5b6-b60e965a9a7b",
                        "1cf6bd12-f08e-4bb4-b654-7fa22239b0ea",
                    ],
                    "mode": "hybrid",
                    "index": "procedures",
                    "k": 10,
                    "bm25_weight": 0.3,
                    "knn_weight": 0.7,
                    "num_candidates": 50,
                }
            ]
        }
    }


class EvalMetrics(BaseModel):
    ndcg_at_k: float = Field(..., description="Normalised Discounted Cumulative Gain @K")
    mrr: float = Field(..., description="Mean Reciprocal Rank")
    precision_at_k: float = Field(..., description="Precision at K")
    recall_at_k: float = Field(..., description="Recall at K")


class EvalResponse(BaseModel):
    query: str
    mode: str
    index: str
    k: int
    metrics: EvalMetrics
    relevant_provided: int = Field(..., description="Number of relevant IDs you supplied")
    relevant_found: int = Field(..., description="How many were in the top-K results")
    relevant_positions: list[int] = Field(..., description="1-based positions of relevant hits")
    hits: list[dict[str, Any]] = Field(..., description="Full ranked result list")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=EvalResponse,
    summary="Evaluate search quality",
    description="""
Run a search query and measure its quality against a **ground truth** list of relevant document IDs.

### Returned metrics

| Metric | Description |
|--------|-------------|
| **NDCG@K** | Normalised Discounted Cumulative Gain — rewards relevant docs found earlier in the list |
| **MRR** | Mean Reciprocal Rank — reciprocal of the position of the *first* relevant result (1.0 = found at #1) |
| **Precision@K** | Fraction of top-K results that are relevant |
| **Recall@K** | Fraction of all known-relevant docs that appear in top-K |

### Workflow for A/B experiments
1. Run a few searches, note the IDs of documents you consider relevant.
2. Call `POST /eval` with `mode=bm25` → save metrics.
3. Call again with `mode=semantic` or `mode=rrf` → compare.
4. Tune `bm25_weight` / `knn_weight` and repeat.
""",
)
async def eval_endpoint(client: OSClient, body: EvalRequest) -> EvalResponse:
    params = SearchParams(
        q=body.query,
        mode=body.mode,
        index_key=body.index,
        size=body.k,
        bm25_weight=body.bm25_weight,
        knn_weight=body.knn_weight,
        num_candidates=body.num_candidates,
        explain=False,
    )
    result = await evaluate(client, params, body.relevant_ids)
    return EvalResponse(**result)


@router.post(
    "/rank-eval",
    response_model=RankEvalResponse,
    summary="Native OpenSearch ranking evaluation",
    description="""
Evaluate BM25 ranking quality using the native OpenSearch **`_rank_eval` API**.

Unlike `POST /eval` (which runs a single query through our search pipeline), this endpoint:
- Sends **multiple queries** to OpenSearch in a single request
- Uses OpenSearch's own scoring engine — no Python-side normalisation
- Returns per-query metric scores alongside the overall score

### Supported metrics
| Metric | Description |
|--------|-------------|
| `ndcg` | Normalised Discounted Cumulative Gain (default) |
| `dcg` | Discounted Cumulative Gain |
| `precision` | Fraction of top-K that are relevant |
| `recall` | Fraction of relevant docs found in top-K |
| `mean_reciprocal_rank` | Reciprocal of first relevant result position |

### Relevance ratings
| Value | Meaning |
|-------|---------|
| `0` | Not relevant |
| `1` | Relevant |
| `3` | Highly relevant |

### Limitation
Works only for **BM25 queries** against a **single index** (not `all`).
For hybrid / RRF quality evaluation, use `POST /eval`.
""",
)
async def rank_eval_endpoint(client: OSClient, body: RankEvalRequest) -> RankEvalResponse:
    query_inputs = [
        {
            "id": q.id,
            "query": q.query,
            "ratings": [{"doc_id": r.doc_id, "rating": r.rating} for r in q.ratings],
        }
        for q in body.queries
    ]
    result = await rank_eval(
        client=client,
        index_key=body.index,
        query_inputs=query_inputs,
        k=body.k,
        metric_name=body.metric,
    )
    details = {
        qid: RankEvalQueryResult(**data)
        for qid, data in result["details"].items()  # type: ignore[union-attr]
    }
    return RankEvalResponse(
        metric_score=result["metric_score"],  # type: ignore[arg-type]
        details=details,
        failures=result.get("failures", {}),  # type: ignore[union-attr]
    )
