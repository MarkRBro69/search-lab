"""Indexing use case — CRUD for documents with automatic embedding generation."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from functools import partial
from typing import TYPE_CHECKING

import structlog

from src.modules.search.infrastructure.repository import (
    delete_document,
    get_document,
    index_document,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from opensearchpy import OpenSearch

logger = structlog.get_logger(module="search")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize(data: dict[str, object]) -> dict[str, object]:
    """Convert non-JSON-serializable types (date → ISO string). Field names are preserved as-is."""
    return {k: v.isoformat() if isinstance(v, date) else v for k, v in data.items()}


def _strip_embedding(source: dict[str, object]) -> dict[str, object]:
    source.pop("embedding", None)
    return source


def _embedding_source_text(data: dict[str, object]) -> str:
    raw = data.get("embedding_text")
    if isinstance(raw, str) and raw.strip():
        return raw
    return " ".join(str(v) for v in data.values() if isinstance(v, str))


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


async def create_document(
    client: OpenSearch,
    index_key: str,
    data: dict[str, object],
    index_alias: dict[str, str],
    embed: Callable[[str], Awaitable[list[float]]],
) -> dict[str, object]:
    log = logger.bind(operation="create_document")
    doc_id = str(uuid.uuid4())
    body = _serialize({**data, "id": doc_id})

    text = _embedding_source_text(body)
    body["embedding"] = await embed(text)
    if "embedding_text" in body:
        del body["embedding_text"]

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, partial(index_document, client, index_key, doc_id, body, index_alias)
    )

    log.info("document_created", index_key=index_key, doc_id=doc_id)
    return {**_strip_embedding(dict(body)), "id": doc_id}


async def get_document_by_id(
    client: OpenSearch,
    index_key: str,
    doc_id: str,
    index_alias: dict[str, str],
) -> dict[str, object] | None:
    log = logger.bind(operation="get_document_by_id")
    loop = asyncio.get_running_loop()
    resp = await loop.run_in_executor(
        None, partial(get_document, client, index_key, doc_id, index_alias)
    )
    if resp is None or not resp.get("found"):
        return None
    src = resp.get("_source")
    if not isinstance(src, dict):
        return None
    log.debug("document_found", index_key=index_key, doc_id=doc_id)
    return _strip_embedding(dict(src))


async def update_document(
    client: OpenSearch,
    index_key: str,
    doc_id: str,
    data: dict[str, object],
    index_alias: dict[str, str],
    embed: Callable[[str], Awaitable[list[float]]],
) -> dict[str, object] | None:
    log = logger.bind(operation="update_document")
    loop = asyncio.get_running_loop()

    existing = await loop.run_in_executor(
        None, partial(get_document, client, index_key, doc_id, index_alias)
    )
    if existing is None or not existing.get("found"):
        return None

    src_prev = existing.get("_source")
    base: dict[str, object] = dict(src_prev) if isinstance(src_prev, dict) else {}
    body = _serialize({**base, **data, "id": doc_id})

    text = _embedding_source_text(body)
    body["embedding"] = await embed(text)
    if "embedding_text" in body:
        del body["embedding_text"]

    await loop.run_in_executor(
        None, partial(index_document, client, index_key, doc_id, body, index_alias)
    )

    log.info("document_updated", index_key=index_key, doc_id=doc_id)
    return _strip_embedding({k: v for k, v in body.items()})


async def delete_document_by_id(
    client: OpenSearch,
    index_key: str,
    doc_id: str,
    index_alias: dict[str, str],
) -> bool:
    log = logger.bind(operation="delete_document_by_id")
    loop = asyncio.get_running_loop()
    deleted = await loop.run_in_executor(
        None, partial(delete_document, client, index_key, doc_id, index_alias)
    )
    if deleted:
        log.info("document_deleted", index_key=index_key, doc_id=doc_id)
    return deleted
