"""Domain models for the Experiments module.

Three aggregates:
  Algorithm      — named search configuration (mode, weights, filters, …)
  QueryTemplate  — named query with ground-truth relevant IDs
  BenchmarkRun   — cross-product evaluation of N algorithms × M templates
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Algorithm
# ---------------------------------------------------------------------------


class AlgorithmFilters(BaseModel):
    """Optional filters applied during benchmark evaluation."""

    min_rating: float | None = None
    max_cost_usd: int | None = None
    category: str | None = None
    body_area: str | None = None
    is_surgical: bool | None = None
    specialty: str | None = None
    min_experience: int | None = None
    worth_it: str | None = None
    verified: bool | None = None


class Algorithm(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Human-readable label, e.g. 'Hybrid 30/70 no-filter'")
    description: str = Field(default="", description="Optional notes about this configuration")
    mode: Literal["bm25", "semantic", "hybrid", "rrf"] = Field(
        default="hybrid",
        description="Search mode",
    )
    bm25_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    knn_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    num_candidates: int = Field(default=50, ge=10, le=500)
    index: str = Field(
        default="all", description="Target index: all | procedures | doctors | reviews"
    )
    filters: AlgorithmFilters = Field(default_factory=AlgorithmFilters)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# QueryTemplate
# ---------------------------------------------------------------------------


class QueryTemplate(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Short label for the template, e.g. 'rhinoplasty intent'")
    query: str = Field(..., description="The search query string")
    index: str = Field(default="all", description="Default index for this template")
    relevant_ids: list[str] = Field(
        default_factory=list,
        description="Ground-truth document IDs considered relevant for this query",
    )
    notes: str = Field(default="", description="Free-form notes or context")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# BenchmarkRun — result of running N algorithms × M templates
# ---------------------------------------------------------------------------


class TemplateResult(BaseModel):
    """All analytics collected for one (algorithm, template) pair."""

    # ── Core IR metrics ────────────────────────────────────────────────────
    ndcg_at_k: float = Field(description="Normalised Discounted Cumulative Gain @K")
    mrr: float = Field(description="Mean Reciprocal Rank — 1/position of first hit")
    precision_at_k: float = Field(description="Fraction of top-K results that are relevant")
    recall_at_k: float = Field(description="Fraction of all relevant docs found in top-K")

    # ── Performance ────────────────────────────────────────────────────────
    latency_ms: int = Field(description="Wall-clock time of the search call (ms)")

    # ── Score distribution (all returned hits) ────────────────────────────
    score_min: float = Field(description="Lowest score in the result list")
    score_max: float = Field(description="Highest score in the result list")
    score_mean: float = Field(description="Average score across all hits")
    score_std: float = Field(description="Standard deviation of scores — spread of the ranking")

    # ── Separation quality (key diagnostic) ───────────────────────────────
    relevant_score_mean: float = Field(
        description="Average score of hits that appear in relevant_ids"
    )
    non_relevant_score_mean: float = Field(description="Average score of hits NOT in relevant_ids")
    score_separation: float = Field(
        description=(
            "relevant_score_mean − non_relevant_score_mean. "
            "Higher = algorithm pushes relevant docs further above non-relevant ones."
        )
    )

    # ── Ranking positions ─────────────────────────────────────────────────
    first_relevant_position: int | None = Field(
        description="1-based rank of the first relevant hit (null if none found)"
    )
    relevant_positions: list[int] = Field(
        description="1-based positions of every relevant hit in the result list"
    )
    total_hits: int = Field(description="Number of hits returned by the query")


class AlgoSummary(BaseModel):
    """Averaged metrics for one algorithm across all templates in a run."""

    avg_ndcg_at_k: float
    avg_mrr: float
    avg_precision_at_k: float
    avg_recall_at_k: float
    avg_latency_ms: float
    avg_score_separation: float
    avg_score_mean: float


class BenchmarkRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(default="", description="Optional label for this run")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    k: int = Field(default=10, description="@K used for all metrics in this run")
    algorithm_ids: list[str]
    template_ids: list[str]
    # results[algo_id][template_id] → TemplateResult
    results: dict[str, dict[str, TemplateResult]]
    # summary[algo_id] → averaged metrics
    summary: dict[str, AlgoSummary]
