"""Unit tests for profiles domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.modules.profiles.domain.models import OpenSearchAuthType, OpenSearchConfig, ProfileIndices


def test_profile_indices_migrates_legacy_flat_dict() -> None:
    legacy: dict[str, object] = {"index_a": "env_index_a_v1", "index_b": "env_index_b_v1"}
    pi = ProfileIndices.model_validate(legacy)
    assert pi.indices == {"index_a": "env_index_a_v1", "index_b": "env_index_b_v1"}
    assert pi.bm25_fields["index_a"] == []
    assert pi.bm25_fields["index_b"] == []
    assert "all" in pi.bm25_fields


def test_profile_indices_rejects_comma_in_logical_key() -> None:
    with pytest.raises(ValidationError):
        ProfileIndices(
            indices={"bad,key": "idx"},
            bm25_fields={"bad,key": ["f"]},
        )


def test_profile_indices_auto_fills_all_bm25_from_per_key_lists() -> None:
    pi = ProfileIndices(
        indices={
            "a": "idx_a",
            "b": "idx_b",
        },
        bm25_fields={
            "a": ["f1", "f2"],
            "b": ["f2", "f3"],
        },
    )
    assert "all" in pi.bm25_fields
    assert pi.bm25_fields["all"] == ["f1", "f2", "f3"]


def test_opensearch_config_basic_requires_password() -> None:
    with pytest.raises(ValidationError):
        OpenSearchConfig(
            host="localhost",
            auth_type=OpenSearchAuthType.BASIC,
            username="user",
            password=None,
        )
