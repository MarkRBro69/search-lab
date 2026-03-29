"""FastAPI router for the search module."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from opensearchpy import NotFoundError, OpenSearch

from src.modules.search.application.search_params import SearchParams
from src.modules.search.application.search_service import explain_document_async, search
from src.modules.search.presentation.schemas import (
    ExplainResponse,
    OsExplanationNode,
    SearchResponse,
)
from src.shared.infrastructure.opensearch import get_client

router = APIRouter(prefix="/search", tags=["search"])


def _os_client() -> OpenSearch:
    return get_client()


OSClient = Annotated[OpenSearch, Depends(_os_client)]


@router.get(
    "",
    response_model=SearchResponse,
    summary="Search documents",
    description="""
Full-text and semantic search across the collections.

### Modes
| Mode       | Algorithm | Score range | Best for |
|------------|-----------|-------------|----------|
| `bm25`     | TF-IDF keyword (min-max normalised) | [0, 1] | Exact names |
| `semantic` | KNN cosine similarity | [0, 1] | Descriptive queries |
| `hybrid`   | BM25 × weight + KNN × weight (both normalised) | [0, 1] | General use |
| `rrf`      | Reciprocal Rank Fusion (rank-based, no normalisation needed) | ~0.01–0.03 | Comparing ranked lists |

### Hybrid weights
`bm25_weight + knn_weight` should equal **1.0**. Default: **0.3 / 0.7** (KNN-dominant).

### Score breakdown
Add `explain=true` to see how each component contributed to the final score.

### Filters
All filters are optional and can be combined freely. Unknown fields are silently ignored for cross-index searches.
""",
    responses={
        200: {"description": "Search executed successfully"},
        422: {"description": "Validation error"},
    },
)
async def search_endpoint(
    client: OSClient,
    # ── Core ──────────────────────────────────────────────────────────────
    q: Annotated[
        str,
        Query(
            min_length=1,
            max_length=500,
            description="Search query text",
            openapi_examples={
                "procedure": {"summary": "Procedure name", "value": "rhinoplasty nose reshaping"},
                "descriptive": {
                    "summary": "Descriptive query",
                    "value": "anti aging face treatment",
                },
                "doctor": {"summary": "Doctor search", "value": "plastic surgeon Los Angeles"},
                "review": {
                    "summary": "Review sentiment",
                    "value": "worth it no scars great results",
                },
            },
        ),
    ],
    mode: Annotated[
        str,
        Query(description="Search algorithm: bm25 | semantic | hybrid | rrf"),
    ] = "hybrid",
    index: Annotated[
        str,
        Query(description="Collection: all | procedures | doctors | reviews"),
    ] = "all",
    size: Annotated[int, Query(ge=1, le=50, description="Results to return (1–50)")] = 10,
    # ── Hybrid tuning ─────────────────────────────────────────────────────
    bm25_weight: Annotated[
        float,
        Query(ge=0.0, le=1.0, description="BM25 weight for hybrid mode (default 0.3)"),
    ] = 0.3,
    knn_weight: Annotated[
        float,
        Query(ge=0.0, le=1.0, description="KNN weight for hybrid mode (default 0.7)"),
    ] = 0.7,
    num_candidates: Annotated[
        int,
        Query(
            ge=10,
            le=500,
            description="KNN candidates per shard — higher = more accurate but slower (default 50)",
        ),
    ] = 50,
    explain: Annotated[
        bool,
        Query(description="Include per-document score breakdown in response"),
    ] = False,
    # ── Filters ───────────────────────────────────────────────────────────
    min_rating: Annotated[
        float | None,
        Query(
            ge=0.0,
            le=5.0,
            description="Minimum average_rating (procedures/doctors) or rating (reviews)",
        ),
    ] = None,
    max_cost_usd: Annotated[
        int | None,
        Query(ge=0, description="Maximum average_cost_usd (procedures only)"),
    ] = None,
    category: Annotated[
        str | None,
        Query(description="Exact procedure category (e.g. Facial, Body, Skin)"),
    ] = None,
    body_area: Annotated[
        str | None,
        Query(description="Exact body area (e.g. Nose, Face, Abdomen)"),
    ] = None,
    is_surgical: Annotated[
        bool | None,
        Query(description="Filter by surgical flag (procedures only)"),
    ] = None,
    specialty: Annotated[
        str | None,
        Query(description="Doctor specialty (e.g. 'Plastic Surgeon')"),
    ] = None,
    min_experience: Annotated[
        int | None,
        Query(ge=0, description="Minimum years of doctor experience"),
    ] = None,
    worth_it: Annotated[
        str | None,
        Query(description="Review verdict: Excellent | Good | Not Worth It"),
    ] = None,
    verified: Annotated[
        bool | None,
        Query(description="Filter reviews by verified status"),
    ] = None,
) -> SearchResponse:
    params = SearchParams(
        q=q,
        mode=mode,
        index_key=index,
        size=size,
        bm25_weight=bm25_weight,
        knn_weight=knn_weight,
        num_candidates=num_candidates,
        explain=explain,
        min_rating=min_rating,
        max_cost_usd=max_cost_usd,
        category=category,
        body_area=body_area,
        is_surgical=is_surgical,
        specialty=specialty,
        min_experience=min_experience,
        worth_it=worth_it,
        verified=verified,
    )
    result = await search(client, params)
    return SearchResponse(**result)


@router.get(
    "/explain/{index_key}/{doc_id}",
    response_model=ExplainResponse,
    summary="Explain document ranking",
    description="""
Ask OpenSearch **why** a specific document did (or did not) match a BM25 query.

Returns the full TF-IDF/BM25 explanation tree with per-token and per-field score breakdowns.

### When to use
- Understand why document A ranks above document B
- Debug unexpected relevance scores
- Validate field boost settings (`name^3`, `description^2`, etc.)

### Note
This uses the native OpenSearch `_explain` API and only works for BM25 scoring.
For hybrid/RRF modes, use `explain=true` on the main search endpoint to get the
Python-side score breakdown instead.
""",
    responses={
        200: {"description": "Explanation returned"},
        404: {"description": "Document not found in the specified index"},
    },
)
async def explain_endpoint(
    client: OSClient,
    index_key: str,
    doc_id: str,
    q: Annotated[
        str,
        Query(min_length=1, max_length=500, description="Query to explain ranking against"),
    ],
) -> ExplainResponse:
    try:
        raw = await explain_document_async(client, index_key, doc_id, q)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Document '{doc_id}' not found in index '{index_key}'"
        ) from exc
    return ExplainResponse(
        doc_id=raw["_id"],
        index=raw["_index"],
        matched=raw["matched"],
        explanation=OsExplanationNode.model_validate(raw["explanation"]),
    )
