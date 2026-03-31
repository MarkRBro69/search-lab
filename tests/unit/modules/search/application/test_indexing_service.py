"""Unit tests for indexing_service CRUD and helpers."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from src.modules.search.application import indexing_service as idx
from src.modules.search.application.indexing_service import (
    _embedding_source_text,
    _serialize,
    create_document,
    delete_document_by_id,
    get_document_by_id,
    update_document,
)


def test_serialize_date_to_iso_preserves_field_name() -> None:
    d = date(2024, 6, 15)
    out = _serialize({"review_date": d, "other": 1})
    assert out["review_date"] == "2024-06-15"
    assert out["other"] == 1


def test_embedding_source_text_prefers_non_empty_embedding_text() -> None:
    data: dict[str, object] = {"embedding_text": "  hello  ", "title": "x"}
    assert _embedding_source_text(data) == "  hello  "


def test_embedding_source_text_concat_string_values_when_no_embedding_text() -> None:
    data: dict[str, object] = {"a": "foo", "b": 99, "c": "bar"}
    assert _embedding_source_text(data) == "foo bar"


async def test_create_document_generates_id_embeds_removes_embedding_text_indexes(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    mock_embed: AsyncMock,
) -> None:
    fixed_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    with (
        patch.object(uuid, "uuid4", return_value=fixed_id),
        patch.object(idx, "index_document", return_value={"result": "created"}) as mock_index,
    ):
        out = await create_document(
            mock_os_client,
            "all",
            {"title": "t", "embedding_text": "to embed"},
            index_alias,
            mock_embed,
        )

    mock_embed.assert_awaited_once_with("to embed")
    mock_index.assert_called_once()
    call_args = mock_index.call_args[0]
    assert call_args[1] == "all"
    assert call_args[2] == str(fixed_id)
    body = call_args[3]
    assert "embedding_text" not in body
    assert "embedding" in body
    assert "embedding" not in out


async def test_get_document_by_id_found_false_returns_none(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    with patch.object(idx, "get_document", return_value={"found": False}):
        assert await get_document_by_id(mock_os_client, "all", "x", index_alias) is None


async def test_get_document_by_id_invalid_source_returns_none(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    with patch.object(idx, "get_document", return_value={"found": True, "_source": "bad"}):
        assert await get_document_by_id(mock_os_client, "all", "x", index_alias) is None


async def test_update_document_not_found_returns_none(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    mock_embed: AsyncMock,
) -> None:
    with patch.object(idx, "get_document", return_value=None):
        out = await update_document(
            mock_os_client,
            "all",
            "id1",
            {"x": 1},
            index_alias,
            mock_embed,
        )
    assert out is None
    mock_embed.assert_not_awaited()


async def test_update_document_merges_and_recomputes_embedding(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
    mock_embed: AsyncMock,
) -> None:
    existing = {
        "found": True,
        "_source": {"title": "old", "id": "id1"},
    }
    with (
        patch.object(idx, "get_document", return_value=existing),
        patch.object(idx, "index_document", return_value={}) as mock_index,
    ):
        await update_document(
            mock_os_client,
            "all",
            "id1",
            {"title": "new"},
            index_alias,
            mock_embed,
        )
    mock_embed.assert_awaited_once()
    indexed_body = mock_index.call_args[0][3]
    assert indexed_body["title"] == "new"


async def test_delete_document_by_id_bool_matches_delete_document(
    mock_os_client: MagicMock,
    index_alias: dict[str, str],
) -> None:
    with patch.object(idx, "delete_document", return_value=True):
        assert await delete_document_by_id(mock_os_client, "all", "d1", index_alias) is True
    with patch.object(idx, "delete_document", return_value=False):
        assert await delete_document_by_id(mock_os_client, "all", "d1", index_alias) is False
