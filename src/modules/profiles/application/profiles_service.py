"""CRUD, activation, and default seed for connection profiles."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.modules.profiles.application.active_context import (
    get_cached_bundle,
    invalidate_cache,
    set_cached_bundle,
)
from src.modules.profiles.domain.models import (
    ActiveProfileBundle,
    ConnectionProfile,
    EmbeddingConfig,
    OpenSearchAuthType,
    OpenSearchConfig,
    ProfileIndices,
)
from src.modules.profiles.infrastructure import repository
from src.modules.profiles.infrastructure.opensearch_registry import (
    close_all_opensearch_clients as _close_all_opensearch_clients_registry,
)
from src.modules.profiles.infrastructure.opensearch_registry import (
    evict_opensearch_client,
    get_or_create_opensearch_client,
    ping_opensearch_ephemeral,
)
from src.shared.exceptions import (
    NO_ACTIVE_PROFILE,
    PROFILE_NOT_FOUND,
    InvalidInputError,
    NotFoundError,
)
from src.shared.infrastructure.embedding.factory import build_embedding_backend
from src.shared.infrastructure.embedding.types import EmbeddingProvider
from src.shared.infrastructure.mongodb import get_db

logger = structlog.get_logger()

APP_ENV = os.getenv("APP_ENV", "development")

_EMBED_PROBE_TEXT = "__profile_connection_test__"


@dataclass(frozen=True, slots=True)
class ProfileSubsystemCheckData:
    """Application-layer connection check row (mapped to API in router)."""

    ok: bool
    latency_ms: float | None
    error: str | None


@dataclass(frozen=True, slots=True)
class ProfileTestConnectionData:
    """Result of OpenSearch + embedding probes for a stored profile."""

    opensearch: ProfileSubsystemCheckData
    embedding: ProfileSubsystemCheckData


DEFAULT_PROFILE_INDICES = ProfileIndices(
    indices={
        "index_a": f"{APP_ENV}_index_a_v1",
        "index_b": f"{APP_ENV}_index_b_v1",
        "index_c": f"{APP_ENV}_index_c_v1",
    },
    bm25_fields={
        "index_a": ["name^3", "description^2", "category", "tags"],
        "index_b": ["name^3", "specialization^2", "bio", "hospital"],
        "index_c": ["title^2", "body", "doctor_name"],
        "all": ["name^3", "title^2", "description^2", "body", "category", "tags"],
    },
)


def _default_opensearch_config() -> OpenSearchConfig:
    return OpenSearchConfig(
        host=os.getenv("OPENSEARCH_HOST", "localhost"),
        port=int(os.getenv("OPENSEARCH_PORT", "9200")),
        use_ssl=os.getenv("OPENSEARCH_USE_SSL", "false").lower() == "true",
        auth_type=OpenSearchAuthType.NONE,
    )


def _default_embedding_config() -> EmbeddingConfig:
    return EmbeddingConfig(
        provider=EmbeddingProvider.LOCAL_SENTENCE_TRANSFORMERS,
        model_name="all-MiniLM-L6-v2",
    )


def build_default_connection_profile() -> ConnectionProfile:
    """Construct the default profile from environment (not persisted)."""
    return ConnectionProfile(
        id=str(uuid.uuid4()),
        name="Default (local)",
        opensearch=_default_opensearch_config(),
        embedding=_default_embedding_config(),
        indices=DEFAULT_PROFILE_INDICES,
        is_active=True,
        created_at=datetime.now(UTC),
    )


async def ensure_default_profile_if_empty(db: AsyncIOMotorDatabase) -> None:
    """Insert a default profile when the collection is empty."""
    count = await repository.count_profiles(db)
    if count > 0:
        return
    profile = build_default_connection_profile()
    await repository.insert_profile(db, profile)
    log = logger.bind(
        module="profiles",
        operation="ensure_default_profile_if_empty",
        request_id="-",
    )
    log.info("default_profile_seeded", profile_id=profile.id)


async def create_profile(db: AsyncIOMotorDatabase, profile: ConnectionProfile) -> ConnectionProfile:
    await repository.insert_profile(db, profile)
    invalidate_cache()
    log = logger.bind(module="profiles", operation="create_profile")
    log.info("profile_created", profile_id=profile.id)
    return profile


async def list_profiles(db: AsyncIOMotorDatabase) -> list[ConnectionProfile]:
    return await repository.list_profiles(db)


async def get_profile(db: AsyncIOMotorDatabase, profile_id: str) -> ConnectionProfile | None:
    return await repository.get_profile(db, profile_id)


async def test_profile_connections(
    db: AsyncIOMotorDatabase,
    profile_id: str,
) -> ProfileTestConnectionData:
    """Load profile by id; run OpenSearch ping then one embedding call; never cache test OS client."""
    log = logger.bind(module="profiles", operation="test_profile_connections")
    profile = await get_profile(db, profile_id)
    if profile is None:
        raise NotFoundError(code=PROFILE_NOT_FOUND, detail="Profile not found")

    os_outcome = await ping_opensearch_ephemeral(profile.opensearch)
    opensearch_row = ProfileSubsystemCheckData(
        ok=os_outcome.ok,
        latency_ms=os_outcome.latency_ms,
        error=os_outcome.error,
    )

    t_embed = time.perf_counter()
    try:
        embed_fn = build_embedding_backend(profile.embedding)
    except InvalidInputError:
        latency_ms = (time.perf_counter() - t_embed) * 1000.0
        log.warning("embedding_backend_build_failed")
        embedding_row = ProfileSubsystemCheckData(
            ok=False,
            latency_ms=latency_ms,
            error="Embedding configuration invalid",
        )
    else:
        try:
            await embed_fn(_EMBED_PROBE_TEXT)
            latency_ms = (time.perf_counter() - t_embed) * 1000.0
            embedding_row = ProfileSubsystemCheckData(
                ok=True,
                latency_ms=latency_ms,
                error=None,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - t_embed) * 1000.0
            log.warning("embedding_call_failed", error=str(exc), exc_info=True)
            embedding_row = ProfileSubsystemCheckData(
                ok=False,
                latency_ms=latency_ms,
                error=f"Embedding call failed: {exc}",
            )

    log.info(
        "profile_connection_test_completed",
        profile_id=profile_id,
        opensearch_ok=opensearch_row.ok,
        embedding_ok=embedding_row.ok,
    )
    return ProfileTestConnectionData(opensearch=opensearch_row, embedding=embedding_row)


async def replace_profile(db: AsyncIOMotorDatabase, profile: ConnectionProfile) -> None:
    await repository.update_profile_doc(db, profile)
    evict_opensearch_client(profile.id)
    invalidate_cache()
    log = logger.bind(module="profiles", operation="replace_profile")
    log.info("profile_updated", profile_id=profile.id)


async def delete_profile(db: AsyncIOMotorDatabase, profile_id: str) -> bool:
    deleted = await repository.delete_profile_doc(db, profile_id)
    if deleted:
        evict_opensearch_client(profile_id)
        invalidate_cache()
        log = logger.bind(module="profiles", operation="delete_profile")
        log.info("profile_deleted", profile_id=profile_id)
    return deleted


async def activate_profile(db: AsyncIOMotorDatabase, profile_id: str) -> ConnectionProfile | None:
    existing = await repository.get_profile(db, profile_id)
    if existing is None:
        return None
    await repository.activate_profile_by_id(db, profile_id)
    updated = await repository.get_profile(db, profile_id)
    invalidate_cache()
    log = logger.bind(module="profiles", operation="activate_profile")
    log.info("profile_activated", profile_id=profile_id)
    return updated


async def find_active_profile(db: AsyncIOMotorDatabase) -> ConnectionProfile | None:
    return await repository.find_active_profile(db)


def close_all_opensearch_clients() -> None:
    """Application-layer shutdown: close all cached OpenSearch clients."""
    _close_all_opensearch_clients_registry()


async def get_active_profile_bundle(
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> ActiveProfileBundle:
    """Resolve the active profile: use in-memory cache or load from MongoDB and build bundle."""
    cached = get_cached_bundle()
    if cached is not None:
        return cached
    profile = await find_active_profile(db)
    if profile is None:
        raise InvalidInputError(
            code=NO_ACTIVE_PROFILE,
            detail="No active connection profile. Please activate a profile in Settings.",
        )
    os_client = get_or_create_opensearch_client(profile.id, profile.opensearch)
    embed_fn = build_embedding_backend(profile.embedding)
    bundle = ActiveProfileBundle(
        profile_id=profile.id,
        opensearch_client=os_client,
        indices=profile.indices,
        embed=embed_fn,
    )
    set_cached_bundle(bundle)
    return bundle
