"""HTTP API for connection profiles."""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003
from typing import Annotated

from fastapi import APIRouter, Depends, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict, Field

from src.modules.profiles.application import profiles_service
from src.modules.profiles.domain.models import (
    ConnectionProfile,
    EmbeddingConfig,
    OpenSearchAuthType,
    OpenSearchConfig,
    ProfileIndices,
)
from src.shared.exceptions import (
    PROFILE_NOT_FOUND,
    STORAGE_UNAVAILABLE,
    NotFoundError,
    ServiceUnavailableError,
)
from src.shared.infrastructure.embedding.types import EmbeddingProvider  # noqa: TC001
from src.shared.infrastructure.mongodb import get_db

router = APIRouter(prefix="/profiles", tags=["profiles"])

MongoDb = Annotated[AsyncIOMotorDatabase, Depends(get_db)]


# ---------------------------------------------------------------------------
# Public response models (secrets never exposed)
# ---------------------------------------------------------------------------


class OpenSearchConfigPublic(BaseModel):
    """OpenSearch settings without credentials."""

    model_config = ConfigDict(populate_by_name=True)

    host: str
    port: int = 9200
    use_ssl: bool = False
    auth_type: OpenSearchAuthType
    username: str | None = None
    aws_region: str | None = None
    timeout_s: int = 60


class EmbeddingConfigPublic(BaseModel):
    """Embedding settings without AWS secrets."""

    model_config = ConfigDict(populate_by_name=True)

    provider: EmbeddingProvider
    model_name: str
    aws_region: str | None = None


class ConnectionProfilePublic(BaseModel):
    """API-safe profile view."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    opensearch: OpenSearchConfigPublic
    embedding: EmbeddingConfigPublic
    indices: ProfileIndices
    is_active: bool = False
    created_at: datetime


def _to_public(profile: ConnectionProfile) -> ConnectionProfilePublic:
    o = profile.opensearch
    e = profile.embedding
    return ConnectionProfilePublic(
        id=profile.id,
        name=profile.name,
        opensearch=OpenSearchConfigPublic(
            host=o.host,
            port=o.port,
            use_ssl=o.use_ssl,
            auth_type=o.auth_type,
            username=o.username,
            aws_region=o.aws_region,
            timeout_s=o.timeout_s,
        ),
        embedding=EmbeddingConfigPublic(
            provider=e.provider,
            model_name=e.model_name,
            aws_region=e.aws_region,
        ),
        indices=profile.indices,
        is_active=profile.is_active,
        created_at=profile.created_at,
    )


class ProfileCreateBody(BaseModel):
    """Request body for creating a profile."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1)
    opensearch: OpenSearchConfig
    embedding: EmbeddingConfig
    indices: ProfileIndices


class ProfileReplaceBody(BaseModel):
    """Request body for replacing a profile."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1)
    opensearch: OpenSearchConfig
    embedding: EmbeddingConfig
    indices: ProfileIndices


class ProfileConnectionCheckResult(BaseModel):
    """Per-subsystem outcome for connection test."""

    model_config = ConfigDict(populate_by_name=True)

    ok: bool
    latency_ms: float | None
    error: str | None


class ProfileTestConnectionResponse(BaseModel):
    """OpenSearch + embedding probe results (HTTP 200 when profile exists)."""

    model_config = ConfigDict(populate_by_name=True)

    opensearch: ProfileConnectionCheckResult
    embedding: ProfileConnectionCheckResult


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ConnectionProfilePublic])
async def list_profiles_endpoint(db: MongoDb) -> list[ConnectionProfilePublic]:
    profiles = await profiles_service.list_profiles(db)
    return [_to_public(p) for p in profiles]


@router.post("", response_model=ConnectionProfilePublic, status_code=status.HTTP_201_CREATED)
async def create_profile_endpoint(db: MongoDb, body: ProfileCreateBody) -> ConnectionProfilePublic:
    profile = ConnectionProfile(
        id=str(uuid.uuid4()),
        name=body.name,
        opensearch=body.opensearch,
        embedding=body.embedding,
        indices=body.indices,
        is_active=False,
    )
    created = await profiles_service.create_profile(db, profile)
    return _to_public(created)


@router.get("/{profile_id}", response_model=ConnectionProfilePublic)
async def get_profile_endpoint(db: MongoDb, profile_id: str) -> ConnectionProfilePublic:
    profile = await profiles_service.get_profile(db, profile_id)
    if profile is None:
        raise NotFoundError(code=PROFILE_NOT_FOUND, detail="Profile not found")
    return _to_public(profile)


@router.put("/{profile_id}", response_model=ConnectionProfilePublic)
async def replace_profile_endpoint(
    db: MongoDb, profile_id: str, body: ProfileReplaceBody
) -> ConnectionProfilePublic:
    existing = await profiles_service.get_profile(db, profile_id)
    if existing is None:
        raise NotFoundError(code=PROFILE_NOT_FOUND, detail="Profile not found")
    updated = ConnectionProfile(
        id=profile_id,
        name=body.name,
        opensearch=body.opensearch,
        embedding=body.embedding,
        indices=body.indices,
        is_active=existing.is_active,
        created_at=existing.created_at,
    )
    await profiles_service.replace_profile(db, updated)
    refreshed = await profiles_service.get_profile(db, profile_id)
    if refreshed is None:
        raise ServiceUnavailableError(
            code=STORAGE_UNAVAILABLE,
            detail="Storage temporarily unavailable",
        )
    return _to_public(refreshed)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile_endpoint(db: MongoDb, profile_id: str) -> None:
    deleted = await profiles_service.delete_profile(db, profile_id)
    if not deleted:
        raise NotFoundError(code=PROFILE_NOT_FOUND, detail="Profile not found")


@router.post("/{profile_id}/activate", response_model=ConnectionProfilePublic)
async def activate_profile_endpoint(db: MongoDb, profile_id: str) -> ConnectionProfilePublic:
    activated = await profiles_service.activate_profile(db, profile_id)
    if activated is None:
        raise NotFoundError(code=PROFILE_NOT_FOUND, detail="Profile not found")
    return _to_public(activated)


@router.post("/{profile_id}/test", response_model=ProfileTestConnectionResponse)
async def test_profile_connection_endpoint(
    db: MongoDb, profile_id: str
) -> ProfileTestConnectionResponse:
    data = await profiles_service.test_profile_connections(db, profile_id)
    return ProfileTestConnectionResponse(
        opensearch=ProfileConnectionCheckResult(
            ok=data.opensearch.ok,
            latency_ms=data.opensearch.latency_ms,
            error=data.opensearch.error,
        ),
        embedding=ProfileConnectionCheckResult(
            ok=data.embedding.ok,
            latency_ms=data.embedding.latency_ms,
            error=data.embedding.error,
        ),
    )
