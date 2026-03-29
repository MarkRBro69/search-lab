"""Search parameters — single object passed through all layers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SearchParams:
    # Core
    q: str
    mode: str  # bm25 | semantic | hybrid | rrf
    index_key: str  # all | procedures | doctors | reviews
    size: int = 10

    # Hybrid weights (hybrid mode only, must sum to 1.0)
    bm25_weight: float = 0.3
    knn_weight: float = 0.7

    # KNN accuracy vs speed (hybrid / semantic / rrf)
    num_candidates: int = 50

    # Score breakdown in response
    explain: bool = False

    # ── Filters (None = not applied) ──────────────────────────────────────
    min_rating: float | None = None
    max_cost_usd: int | None = None
    category: str | None = None
    body_area: str | None = None
    is_surgical: bool | None = None
    specialty: str | None = None
    min_experience: int | None = None
    worth_it: str | None = None
    verified: bool | None = None

    # ── Derived ──────────────────────────────────────────────────────────
    @property
    def candidate_size(self) -> int:
        """How many results to fetch from each sub-query before combining."""
        return max(self.size * 3, self.num_candidates)

    def active_filters(self) -> dict:
        """Return only the filters that were explicitly set (for response echo)."""
        mapping = {
            "min_rating": self.min_rating,
            "max_cost_usd": self.max_cost_usd,
            "category": self.category,
            "body_area": self.body_area,
            "is_surgical": self.is_surgical,
            "specialty": self.specialty,
            "min_experience": self.min_experience,
            "worth_it": self.worth_it,
            "verified": self.verified,
        }
        return {k: v for k, v in mapping.items() if v is not None}
