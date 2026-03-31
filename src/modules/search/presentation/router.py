"""FastAPI router for the search module."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from opensearchpy.exceptions import NotFoundError as OpenSearchNotFoundError
from opensearchpy.exceptions import TransportError

from src.modules.profiles.api import ActiveProfileBundle, get_active_profile_bundle
from src.modules.search.application.search_params import SearchParams
from src.modules.search.application.search_service import explain_document_async, search
from src.modules.search.presentation.schemas import (
    ExplainResponse,
    OsExplanationNode,
    SearchResponse,
)
from src.shared.exceptions import (
    DOCUMENT_NOT_FOUND,
    SEARCH_UNAVAILABLE,
    InvalidInputError,
    ServiceUnavailableError,
)
from src.shared.exceptions import (
    NotFoundError as DocumentNotFoundAppError,
)
from src.shared.search_mode import SearchMode

router = APIRouter(prefix="/search", tags=["search"])

ProfileBundle = Annotated[ActiveProfileBundle, Depends(get_active_profile_bundle)]


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
    bundle: ProfileBundle,
    # ── Core ──────────────────────────────────────────────────────────────
    q: Annotated[
        str,
        Query(
            min_length=1,
            max_length=500,
            description="Search query text",
            openapi_examples={
                "keyword": {"summary": "Keyword query", "value": "example product name"},
                "descriptive": {
                    "summary": "Descriptive query",
                    "value": "lightweight portable device under 500",
                },
            },
        ),
    ],
    mode: Annotated[
        SearchMode,
        Query(description="Search algorithm: bm25 | semantic | hybrid | rrf"),
    ] = SearchMode.HYBRID,
    index: Annotated[
        str,
        Query(
            description=(
                "Logical index key from the active connection profile: typically `all` for "
                "combined search, or a specific named index."
            ),
        ),
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
    # ── Generic key-value filters ──────────────────────────────────────────
    filter_term: Annotated[
        list[str] | None,
        Query(
            description=(
                "Exact term filter — repeat for multiple values. "
                "Format: `field:value`. "
                "Booleans auto-detected: `in_stock:true`, `verified:false`. "
                "Example: `filter_term=category:Electronics&filter_term=in_stock:true`"
            ),
            openapi_examples={
                "string_field": {"summary": "String term", "value": "category:Electronics"},
                "boolean_field": {"summary": "Boolean term", "value": "in_stock:true"},
            },
        ),
    ] = None,
    filter_gte: Annotated[
        list[str] | None,
        Query(
            description=(
                "Numeric lower bound (≥) — repeat for multiple fields. "
                "Format: `field:number`. "
                "Example: `filter_gte=rating:4.0&filter_gte=price:100`"
            ),
        ),
    ] = None,
    filter_lte: Annotated[
        list[str] | None,
        Query(
            description=(
                "Numeric upper bound (≤) — repeat for multiple fields. "
                "Format: `field:number`. "
                "Example: `filter_lte=price:500`"
            ),
        ),
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
        filter_term=list(filter_term or []),
        filter_gte=list(filter_gte or []),
        filter_lte=list(filter_lte or []),
    )
    index_alias = bundle.to_alias_map()
    bm25_fields_by_key = bundle.to_bm25_fields_map()
    try:
        result = await search(
            bundle.opensearch_client,
            params,
            index_alias,
            bm25_fields_by_key,
            bundle.embed,
        )
    except InvalidInputError:
        raise
    except TransportError as err:
        raise ServiceUnavailableError(
            code=SEARCH_UNAVAILABLE,
            detail="Search service temporarily unavailable",
        ) from err
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
    bundle: ProfileBundle,
    index_key: str,
    doc_id: str,
    q: Annotated[
        str,
        Query(min_length=1, max_length=500, description="Query to explain ranking against"),
    ],
) -> ExplainResponse:
    try:
        index_alias = bundle.to_alias_map()
        bm25_fields_by_key = bundle.to_bm25_fields_map()
        raw = await explain_document_async(
            bundle.opensearch_client,
            index_key,
            doc_id,
            q,
            index_alias,
            bm25_fields_by_key,
        )
    except OpenSearchNotFoundError as exc:
        raise DocumentNotFoundAppError(
            code=DOCUMENT_NOT_FOUND,
            detail=f"Document '{doc_id}' not found in index '{index_key}'",
        ) from exc
    except TransportError as err:
        raise ServiceUnavailableError(
            code=SEARCH_UNAVAILABLE,
            detail="Search service temporarily unavailable",
        ) from err
    return ExplainResponse(
        doc_id=raw["_id"],
        index=raw["_index"],
        matched=raw["matched"],
        explanation=OsExplanationNode.model_validate(raw["explanation"]),
    )
