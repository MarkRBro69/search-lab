"""Pydantic schemas for the search API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.shared.search_mode import SearchMode  # noqa: TC001

# OpenSearch _source values: primitives, homogeneous lists, and nested objects
DocumentField = (
    str | int | float | bool | list[str] | list[int] | list[float] | dict[str, object] | None
)

# ---------------------------------------------------------------------------
# OpenSearch native explain tree
# ---------------------------------------------------------------------------


class OsExplanationNode(BaseModel):
    """Recursive explanation node from the OpenSearch _explain API."""

    value: float = Field(..., description="Score contribution of this node")
    description: str = Field(..., description="Human-readable scoring factor")
    details: list[OsExplanationNode] = Field(default_factory=list, description="Child nodes")


OsExplanationNode.model_rebuild()


# ---------------------------------------------------------------------------
# Score breakdown (hybrid / rrf — Python-side)
# ---------------------------------------------------------------------------


class ScoreBreakdown(BaseModel):
    """Per-document score breakdown when explain=true (hybrid / rrf modes)."""

    # Hybrid mode (rank-based pool normalization)
    bm25_raw: float | None = Field(None, description="Raw BM25 score (legacy; hybrid uses ranks)")
    bm25_normalized: float | None = Field(
        None, description="BM25 after min-max (BM25-only); hybrid uses bm25_rank_score"
    )
    bm25_contribution: float | None = Field(
        None, description="bm25_weight × bm25_normalized or × bm25_rank_score (hybrid)"
    )
    knn_cosine: float | None = Field(None, description="Raw KNN cosine similarity [0, 1]")
    knn_normalized: float | None = Field(
        None, description="KNN after min-max (semantic-only); hybrid uses knn_rank_score"
    )
    knn_contribution: float | None = Field(
        None, description="knn_weight × knn_normalized or × knn_rank_score (hybrid)"
    )
    bm25_rank_score: float | None = Field(
        None,
        description="Hybrid: (pool_size − rank + 1) / pool_size from BM25 candidate list",
    )
    knn_rank_score: float | None = Field(
        None,
        description="Hybrid: (pool_size − rank + 1) / pool_size from KNN candidate list",
    )

    # RRF mode (and hybrid rank positions)
    bm25_rank: int | None = Field(None, description="Position of the document in BM25 results")
    knn_rank: int | None = Field(None, description="Position of the document in KNN results")
    rrf_bm25: float | None = Field(None, description="1 / (rrf_k + bm25_rank)")
    rrf_knn: float | None = Field(None, description="1 / (rrf_k + knn_rank)")
    rrf_k: int | None = Field(None, description="RRF constant k (default 60)")


class SearchHit(BaseModel):
    id: str = Field(..., description="Document UUID")
    index: str = Field(..., description="OpenSearch index name")
    score: float = Field(
        ...,
        description=(
            "Relevance score in [0, 1]. Min-max normalised within the returned result set "
            "for all search modes (BM25, semantic, hybrid, RRF)."
        ),
    )
    source: dict[str, DocumentField] = Field(..., description="Document fields")
    score_breakdown: ScoreBreakdown | None = Field(
        None, description="Hybrid/RRF weight breakdown (explain=true)"
    )
    os_explanation: OsExplanationNode | None = Field(
        None,
        description="Native OpenSearch TF-IDF explanation tree (BM25 mode only, explain=true)",
    )


class SearchParamsEcho(BaseModel):
    bm25_weight: float
    knn_weight: float
    num_candidates: int
    explain: bool


class SearchResponse(BaseModel):
    query: str = Field(..., description="Original search query")
    mode: SearchMode = Field(..., description="Mode used: bm25 | semantic | hybrid | rrf")
    index: str = Field(..., description="Collection searched")
    total: int = Field(..., description="Total matching documents")
    hits: list[SearchHit] = Field(..., description="Ranked result list")
    filters: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict, description="Active filters applied"
    )
    params: SearchParamsEcho | None = Field(None, description="Effective search parameters")


# ---------------------------------------------------------------------------
# Explain endpoint
# ---------------------------------------------------------------------------


class ExplainResponse(BaseModel):
    """Response from GET /search/explain/{index_key}/{doc_id}."""

    doc_id: str = Field(..., description="Document ID that was explained")
    index: str = Field(..., description="OpenSearch index name")
    matched: bool = Field(..., description="Whether the document matched the query")
    explanation: OsExplanationNode = Field(..., description="Full OpenSearch explanation tree")


# ---------------------------------------------------------------------------
# Native rank_eval endpoint
# ---------------------------------------------------------------------------


class RankEvalRating(BaseModel):
    """Relevance judgment for a single document."""

    doc_id: str = Field(..., description="Document ID")
    rating: int = Field(..., ge=0, le=3, description="0=irrelevant  1=relevant  3=highly relevant")


class RankEvalQuery(BaseModel):
    """One query with its known-relevant documents."""

    id: str = Field(..., description="Unique identifier for this query (appears in results)")
    query: str = Field(..., min_length=1, description="Search query text")
    ratings: list[RankEvalRating] = Field(..., min_length=1, description="Relevance judgments")


class RankEvalRequest(BaseModel):
    """Batch ranking evaluation via OpenSearch _rank_eval API (BM25 queries only)."""

    queries: list[RankEvalQuery] = Field(..., min_length=1)
    index: str = Field(
        ...,
        description="Single logical index key from the profile (not `all` — ratings target one physical index)",
    )
    k: int = Field(10, ge=1, le=50, description="Evaluate top-K results")
    metric: Literal["dcg", "precision", "recall", "mean_reciprocal_rank"] = Field(
        "dcg",
        description="Ranking metric to compute via OpenSearch _rank_eval (ndcg and expected_reciprocal_rank are not supported by OpenSearch)",
    )

    @model_validator(mode="after")
    def _validate_index_not_all(self) -> RankEvalRequest:
        if self.index == "all":
            raise ValueError(
                "rank_eval requires a single logical index key, not 'all', "
                "because relevance ratings must target one physical index."
            )
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "queries": [
                        {
                            "id": "example-query",
                            "query": "example search query",
                            "ratings": [
                                {"doc_id": "00000000-0000-0000-0000-000000000001", "rating": 3},
                                {"doc_id": "00000000-0000-0000-0000-000000000002", "rating": 1},
                            ],
                        }
                    ],
                    "index": "my-index",
                    "k": 10,
                    "metric": "dcg",
                }
            ]
        }
    }


class RankEvalQueryResult(BaseModel):
    metric_score: float = Field(..., description="Per-query metric score")
    unrated_docs: list[str] = Field(
        default_factory=list, description="Doc IDs returned but not in ratings"
    )


class RankEvalResponse(BaseModel):
    metric_score: float = Field(..., description="Overall metric score across all queries")
    details: dict[str, RankEvalQueryResult] = Field(..., description="Per-query breakdown")
    failures: dict[str, str] = Field(
        default_factory=dict, description="Query-level failures from OpenSearch"
    )
