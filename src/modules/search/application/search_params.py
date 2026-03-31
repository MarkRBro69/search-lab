"""Search parameters — single object passed through all layers."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.shared.search_mode import SearchMode


def _split_pair(s: str) -> tuple[str, str] | None:
    """Split 'field:value' into (field, value). Returns None if the format is invalid."""
    idx = s.find(":")
    if idx <= 0:
        return None
    return s[:idx].strip(), s[idx + 1 :].strip()


@dataclass
class SearchParams:
    # Core
    q: str
    mode: SearchMode
    index_key: str  # logical key from profile (e.g. all, or a named index)
    size: int = 10

    # Hybrid weights (hybrid mode only, must sum to 1.0)
    bm25_weight: float = 0.3
    knn_weight: float = 0.7

    # KNN accuracy vs speed (hybrid / semantic / rrf)
    num_candidates: int = 50

    # Score breakdown in response
    explain: bool = False

    # ── Generic key-value filters ─────────────────────────────────────────
    # Format: "field:value" — repeated for multiple filters of the same type.
    # Domain-agnostic: work with any document schema, any index.
    filter_term: list[str] = field(default_factory=list)  # exact term match
    filter_gte: list[str] = field(default_factory=list)  # numeric lower bound (≥)
    filter_lte: list[str] = field(default_factory=list)  # numeric upper bound (≤)

    def __post_init__(self) -> None:
        """Validate hybrid weight sum (BM25 + KNN linear combination)."""
        if self.mode == SearchMode.HYBRID:
            w_sum = self.bm25_weight + self.knn_weight
            if abs(w_sum - 1.0) > 1e-9:
                msg = f"bm25_weight + knn_weight must equal 1.0 (got {w_sum:.6f})"
                raise ValueError(msg)

    # ── Derived ──────────────────────────────────────────────────────────
    @property
    def candidate_size(self) -> int:
        """How many results to fetch from each sub-query before combining."""
        return max(self.size * 3, self.num_candidates)

    def has_filters(self) -> bool:
        return bool(self.filter_term or self.filter_gte or self.filter_lte)

    def active_filters(self) -> dict[str, str]:
        """Return active filters for API response echo (field → value mapping)."""
        result: dict[str, str] = {}
        for s in self.filter_term:
            pair = _split_pair(s)
            if pair:
                result[f"={pair[0]}"] = pair[1]
        for s in self.filter_gte:
            pair = _split_pair(s)
            if pair:
                result[f">={pair[0]}"] = pair[1]
        for s in self.filter_lte:
            pair = _split_pair(s)
            if pair:
                result[f"<={pair[0]}"] = pair[1]
        return result
