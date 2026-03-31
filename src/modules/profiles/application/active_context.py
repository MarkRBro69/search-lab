"""In-memory cache for the active profile bundle (refreshed on activate / invalidation)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.profiles.domain.models import ActiveProfileBundle

_cached_bundle: ActiveProfileBundle | None = None


def get_cached_bundle() -> ActiveProfileBundle | None:
    return _cached_bundle


def set_cached_bundle(bundle: ActiveProfileBundle) -> None:
    global _cached_bundle  # noqa: PLW0603
    _cached_bundle = bundle


def invalidate_cache() -> None:
    global _cached_bundle  # noqa: PLW0603
    _cached_bundle = None
