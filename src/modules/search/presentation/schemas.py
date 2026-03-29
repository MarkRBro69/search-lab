"""Pydantic schemas for the search API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# OpenSearch _source values: primitives and homogeneous lists (no nested dicts in our indices)
DocumentField = str | int | float | bool | list[str] | list[int] | list[float] | None

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

    # Hybrid mode
    bm25_raw: float | None = Field(None, description="Raw BM25 score before normalization")
    bm25_normalized: float | None = Field(
        None, description="BM25 score after min-max normalization [0, 1]"
    )
    bm25_contribution: float | None = Field(None, description="bm25_weight × bm25_normalized")
    knn_cosine: float | None = Field(None, description="Raw KNN cosine similarity [0, 1]")
    knn_normalized: float | None = Field(
        None, description="KNN score after min-max normalization [0, 1]"
    )
    knn_contribution: float | None = Field(None, description="knn_weight × knn_normalized")

    # RRF mode
    bm25_rank: int | None = Field(None, description="Position of the document in BM25 results")
    knn_rank: int | None = Field(None, description="Position of the document in KNN results")
    rrf_bm25: float | None = Field(None, description="1 / (rrf_k + bm25_rank)")
    rrf_knn: float | None = Field(None, description="1 / (rrf_k + knn_rank)")
    rrf_k: int | None = Field(None, description="RRF constant k (default 60)")


class SearchHit(BaseModel):
    id: str = Field(..., description="Document UUID")
    index: str = Field(..., description="OpenSearch index name")
    score: float = Field(
        ..., description="Relevance score [0, 1] for bm25/hybrid/rrf; cosine for semantic"
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
    mode: str = Field(..., description="Mode used: bm25 | semantic | hybrid | rrf")
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
    index: str = Field("procedures", description="procedures | doctors | reviews  (not 'all')")
    k: int = Field(10, ge=1, le=50, description="Evaluate top-K results")
    metric: Literal["dcg", "ndcg", "precision", "recall", "mean_reciprocal_rank"] = Field(
        "ndcg",
        description="Ranking metric to compute",
    )

    @model_validator(mode="after")
    def _validate_index_not_all(self) -> RankEvalRequest:
        if self.index == "all":
            raise ValueError(
                "rank_eval requires a specific index (procedures | doctors | reviews). "
                "'all' is not supported because relevance ratings need a single target index."
            )
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "queries": [
                        {
                            "id": "rhinoplasty",
                            "query": "rhinoplasty nose reshaping",
                            "ratings": [
                                {"doc_id": "0ec37382-9f2b-447e-b5b6-b60e965a9a7b", "rating": 3},
                                {"doc_id": "1cf6bd12-f08e-4bb4-b654-7fa22239b0ea", "rating": 1},
                            ],
                        }
                    ],
                    "index": "procedures",
                    "k": 10,
                    "metric": "ndcg",
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
