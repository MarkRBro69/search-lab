"""Domain models and enums for connection profiles."""

from __future__ import annotations

from collections.abc import Awaitable, Callable  # noqa: TC003
from datetime import UTC, datetime
from enum import StrEnum

from opensearchpy import OpenSearch  # noqa: TC002
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.shared.infrastructure.embedding.types import EmbeddingConfig  # noqa: TC001


class OpenSearchAuthType(StrEnum):
    NONE = "none"
    BASIC = "basic"
    AWS_SIGNATURE_V4 = "aws_signature_v4"


class OpenSearchConfig(BaseModel):
    """OpenSearch connection settings (may include secrets — never log or expose in API responses)."""

    model_config = ConfigDict(populate_by_name=True)

    host: str
    port: int = 9200
    use_ssl: bool = False
    auth_type: OpenSearchAuthType
    username: str | None = None
    password: str | None = None
    aws_region: str | None = None

    @model_validator(mode="after")
    def validate_auth_fields(self) -> OpenSearchConfig:
        if self.auth_type == OpenSearchAuthType.BASIC and (
            not self.username or self.password is None
        ):
            msg = "BASIC auth requires username and password"
            raise ValueError(msg)
        if self.auth_type == OpenSearchAuthType.AWS_SIGNATURE_V4 and not self.aws_region:
            msg = "AWS_SIGNATURE_V4 auth requires aws_region"
            raise ValueError(msg)
        return self


class ProfileIndices(BaseModel):
    """Per-profile logical index keys, physical names, and BM25 multi_match fields."""

    model_config = ConfigDict(populate_by_name=True)

    indices: dict[str, str]
    bm25_fields: dict[str, list[str]]

    @model_validator(mode="before")
    @classmethod
    def _migrate_and_compute(cls, data: object) -> object:
        """Migrate legacy flat format and pre-compute the 'all' bm25_fields key."""
        if not isinstance(data, dict):
            return data
        # Legacy migration: flat {key: index_name} → {indices: ..., bm25_fields: ...}
        if "indices" not in data and "bm25_fields" not in data:
            flat = {k: v for k, v in data.items() if isinstance(v, str)}
            data = {"indices": flat, "bm25_fields": {k: [] for k in flat}}
        # Auto-fill combined 'all' key from per-index field lists
        bm25: dict[str, list[str]] = dict(data.get("bm25_fields", {}))
        if "all" not in bm25:
            indices: dict[str, str] = data.get("indices", {})
            merged: list[str] = []
            seen: set[str] = set()
            for logical_key in sorted(indices.keys()):
                for field in bm25.get(logical_key, []):
                    if field not in seen:
                        seen.add(field)
                        merged.append(field)
            bm25["all"] = merged
            data = {**data, "bm25_fields": bm25}
        return data

    @model_validator(mode="after")
    def _validate_keys(self) -> ProfileIndices:
        for key in self.indices:
            if "," in key:
                msg = f"Logical index key must not contain comma: {key!r}"
                raise ValueError(msg)
            if key not in self.bm25_fields:
                msg = f"bm25_fields must include an entry for each indices key, missing {key!r}"
                raise ValueError(msg)
        return self

    def to_alias_map(self) -> dict[str, str]:
        """Map logical keys to physical index names; `all` searches all configured indices."""
        out: dict[str, str] = dict(self.indices)
        if "all" in self.indices:
            out["all"] = self.indices["all"]
        else:
            physical = sorted(self.indices.values())
            out["all"] = ",".join(physical)
        return out

    def bm25_fields_for(self, index_key: str) -> list[str]:
        """BM25 field list for a logical key, falling back to the combined `all` list."""
        if index_key in self.bm25_fields:
            return list(self.bm25_fields[index_key])
        return list(self.bm25_fields.get("all", []))


class ConnectionProfile(BaseModel):
    """Stored connection profile aggregate."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    opensearch: OpenSearchConfig
    embedding: EmbeddingConfig
    indices: ProfileIndices
    is_active: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ActiveProfileBundle(BaseModel):
    """Runtime bundle: active profile id, OpenSearch client, indices, and async embedder."""

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    profile_id: str
    opensearch_client: OpenSearch
    indices: ProfileIndices
    embed: Callable[[str], Awaitable[list[float]]]

    def to_alias_map(self) -> dict[str, str]:
        return self.indices.to_alias_map()

    def to_bm25_fields_map(self) -> dict[str, list[str]]:
        return self.indices.bm25_fields
