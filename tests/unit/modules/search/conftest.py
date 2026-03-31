"""Shared fixtures for search module unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_os_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_embed_vector() -> list[float]:
    return [0.1, 0.2, 0.3]


@pytest.fixture
def mock_embed(mock_embed_vector: list[float]) -> AsyncMock:
    return AsyncMock(return_value=mock_embed_vector)


@pytest.fixture
def index_alias() -> dict[str, str]:
    return {"all": "physical-all", "reviews": "physical-reviews"}


@pytest.fixture
def bm25_fields_by_key() -> dict[str, list[str]]:
    return {"all": ["title^2", "body"], "reviews": ["text"]}
