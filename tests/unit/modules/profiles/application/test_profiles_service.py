"""Unit tests for profiles_service with mocked repository."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.modules.profiles.application import profiles_service
from src.modules.profiles.domain.models import (
    ConnectionProfile,
    EmbeddingConfig,
    OpenSearchAuthType,
    OpenSearchConfig,
    ProfileIndices,
)
from src.modules.profiles.infrastructure.opensearch_registry import EphemeralPingOutcome
from src.shared.exceptions import (
    EMBEDDING_MODEL_MISMATCH,
    PROFILE_NOT_FOUND,
    InvalidInputError,
    NotFoundError,
)
from src.shared.infrastructure.embedding.types import EmbeddingProvider


@pytest.fixture
def mock_db() -> AsyncIOMotorDatabase:
    return MagicMock(spec=AsyncIOMotorDatabase)


async def test_ensure_default_profile_if_empty_inserts_when_count_zero(
    mock_db: AsyncIOMotorDatabase,
) -> None:
    with (
        patch.object(
            profiles_service.repository, "count_profiles", new_callable=AsyncMock
        ) as count_p,
        patch.object(
            profiles_service.repository, "insert_profile", new_callable=AsyncMock
        ) as ins_p,
    ):
        count_p.return_value = 0
        await profiles_service.ensure_default_profile_if_empty(mock_db)
        count_p.assert_awaited_once_with(mock_db)
        ins_p.assert_awaited_once()
        inserted = ins_p.await_args.args[1]
        assert isinstance(inserted, ConnectionProfile)


async def test_ensure_default_profile_if_empty_skips_when_count_positive(
    mock_db: AsyncIOMotorDatabase,
) -> None:
    with (
        patch.object(
            profiles_service.repository, "count_profiles", new_callable=AsyncMock
        ) as count_p,
        patch.object(
            profiles_service.repository, "insert_profile", new_callable=AsyncMock
        ) as ins_p,
    ):
        count_p.return_value = 3
        await profiles_service.ensure_default_profile_if_empty(mock_db)
        ins_p.assert_not_awaited()


async def test_create_profile_inserts_and_invalidates_cache(mock_db: AsyncIOMotorDatabase) -> None:
    indices = ProfileIndices(
        indices={"x": "ix"},
        bm25_fields={"x": ["t"], "all": ["t"]},
    )
    profile = ConnectionProfile(
        id="pid-1",
        name="p",
        opensearch=OpenSearchConfig(host="h", auth_type=OpenSearchAuthType.NONE),
        embedding=EmbeddingConfig(
            provider=EmbeddingProvider.LOCAL_SENTENCE_TRANSFORMERS, model_name="m"
        ),
        indices=indices,
    )
    with (
        patch.object(
            profiles_service.repository, "insert_profile", new_callable=AsyncMock
        ) as ins_p,
        patch.object(profiles_service, "invalidate_cache") as inv,
    ):
        out = await profiles_service.create_profile(mock_db, profile)
        ins_p.assert_awaited_once_with(mock_db, profile)
        inv.assert_called_once()
        assert out is profile


async def test_activate_profile_returns_none_when_profile_missing(
    mock_db: AsyncIOMotorDatabase,
) -> None:
    with patch.object(profiles_service.repository, "get_profile", new_callable=AsyncMock) as get_p:
        get_p.return_value = None
        result = await profiles_service.activate_profile(mock_db, "missing-id")
        assert result is None
        get_p.assert_awaited_once_with(mock_db, "missing-id")


def _sample_profile() -> ConnectionProfile:
    indices = ProfileIndices(
        indices={"x": "ix"},
        bm25_fields={"x": ["t"], "all": ["t"]},
    )
    return ConnectionProfile(
        id="pid-test",
        name="test",
        opensearch=OpenSearchConfig(host="h", auth_type=OpenSearchAuthType.NONE),
        embedding=EmbeddingConfig(
            provider=EmbeddingProvider.LOCAL_SENTENCE_TRANSFORMERS,
            model_name="all-MiniLM-L6-v2",
        ),
        indices=indices,
    )


async def test_test_profile_connections_both_ok(mock_db: AsyncIOMotorDatabase) -> None:
    profile = _sample_profile()
    embed_mock = AsyncMock(return_value=[0.1, 0.2])

    with (
        patch.object(profiles_service, "get_profile", new_callable=AsyncMock) as gp,
        patch.object(
            profiles_service,
            "ping_opensearch_ephemeral",
            new_callable=AsyncMock,
        ) as ping_p,
        patch.object(profiles_service, "build_embedding_backend") as beb,
    ):
        gp.return_value = profile
        ping_p.return_value = EphemeralPingOutcome(ok=True, latency_ms=3.5, error=None)
        beb.return_value = embed_mock
        out = await profiles_service.test_profile_connections(mock_db, profile.id)
        assert out.opensearch.ok is True
        assert out.opensearch.error is None
        assert out.embedding.ok is True
        assert out.embedding.error is None
        ping_p.assert_awaited_once()
        beb.assert_called_once_with(profile.embedding)
        embed_mock.assert_awaited_once_with("__profile_connection_test__")


async def test_test_profile_connections_ping_fail_still_runs_embedding(
    mock_db: AsyncIOMotorDatabase,
) -> None:
    profile = _sample_profile()

    async def _embed(_text: str) -> list[float]:
        return [0.1]

    with (
        patch.object(profiles_service, "get_profile", new_callable=AsyncMock) as gp,
        patch.object(
            profiles_service,
            "ping_opensearch_ephemeral",
            new_callable=AsyncMock,
        ) as ping_p,
        patch.object(profiles_service, "build_embedding_backend") as beb,
    ):
        gp.return_value = profile
        ping_p.return_value = EphemeralPingOutcome(
            ok=False, latency_ms=10.0, error="OpenSearch ping failed"
        )
        beb.return_value = _embed
        out = await profiles_service.test_profile_connections(mock_db, profile.id)
        assert out.opensearch.ok is False
        assert out.embedding.ok is True
        beb.assert_called_once()


async def test_test_profile_connections_embed_call_fails(mock_db: AsyncIOMotorDatabase) -> None:
    profile = _sample_profile()

    async def _embed(_text: str) -> list[float]:
        msg = "simulated downstream failure"
        raise RuntimeError(msg)

    with (
        patch.object(profiles_service, "get_profile", new_callable=AsyncMock) as gp,
        patch.object(
            profiles_service,
            "ping_opensearch_ephemeral",
            new_callable=AsyncMock,
        ) as ping_p,
        patch.object(profiles_service, "build_embedding_backend") as beb,
    ):
        gp.return_value = profile
        ping_p.return_value = EphemeralPingOutcome(ok=True, latency_ms=1.0, error=None)
        beb.return_value = _embed
        out = await profiles_service.test_profile_connections(mock_db, profile.id)
        assert out.opensearch.ok is True
        assert out.embedding.ok is False
        assert out.embedding.error is not None
        assert out.embedding.error.startswith("Embedding call failed")


async def test_test_profile_connections_build_backend_invalid(
    mock_db: AsyncIOMotorDatabase,
) -> None:
    profile = _sample_profile()

    def _raise(_cfg: EmbeddingConfig) -> None:
        raise InvalidInputError(code=EMBEDDING_MODEL_MISMATCH, detail="bad config")

    with (
        patch.object(profiles_service, "get_profile", new_callable=AsyncMock) as gp,
        patch.object(
            profiles_service,
            "ping_opensearch_ephemeral",
            new_callable=AsyncMock,
        ) as ping_p,
        patch.object(profiles_service, "build_embedding_backend", side_effect=_raise),
    ):
        gp.return_value = profile
        ping_p.return_value = EphemeralPingOutcome(ok=True, latency_ms=1.0, error=None)
        out = await profiles_service.test_profile_connections(mock_db, profile.id)
        assert out.opensearch.ok is True
        assert out.embedding.ok is False
        assert out.embedding.error == "Embedding configuration invalid"


async def test_test_profile_connections_profile_not_found(mock_db: AsyncIOMotorDatabase) -> None:
    with patch.object(profiles_service, "get_profile", new_callable=AsyncMock) as gp:
        gp.return_value = None
        with pytest.raises(NotFoundError) as exc_info:
            await profiles_service.test_profile_connections(mock_db, "missing")
        assert exc_info.value.code == PROFILE_NOT_FOUND
