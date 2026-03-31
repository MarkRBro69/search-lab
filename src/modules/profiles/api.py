"""Public interface for the profiles module."""

from __future__ import annotations

from src.modules.profiles.application.profiles_service import (
    close_all_opensearch_clients,
    ensure_default_profile_if_empty,
    get_active_profile_bundle,
)
from src.modules.profiles.domain.models import (
    ActiveProfileBundle,
    ConnectionProfile,
    OpenSearchAuthType,
    OpenSearchConfig,
    ProfileIndices,
)
from src.modules.profiles.presentation.router import router as profiles_router
from src.shared.infrastructure.embedding.types import EmbeddingConfig, EmbeddingProvider

__all__ = [
    "ActiveProfileBundle",
    "ConnectionProfile",
    "EmbeddingConfig",
    "EmbeddingProvider",
    "OpenSearchAuthType",
    "OpenSearchConfig",
    "ProfileIndices",
    "close_all_opensearch_clients",
    "ensure_default_profile_if_empty",
    "get_active_profile_bundle",
    "profiles_router",
]
