"""Indexing use case — CRUD for documents with automatic embedding generation."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from functools import partial
from typing import TYPE_CHECKING, Any

import structlog

from src.modules.search.infrastructure.repository import (
    delete_document,
    get_document,
    index_document,
)
from src.shared.infrastructure.embedding import embed_async

if TYPE_CHECKING:
    from opensearchpy import OpenSearch

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Text extractors for each document type (same logic as seed.py)
# ---------------------------------------------------------------------------


def _procedure_text(data: dict) -> str:
    tags = " ".join(data.get("tags") or [])
    return f"{data.get('name', '')} {data.get('body_area', '')} {data.get('category', '')} {data.get('description', '')} {tags}"


def _doctor_text(data: dict) -> str:
    procs = " ".join(data.get("procedures_performed") or [])
    certs = " ".join(data.get("certifications") or [])
    return (
        f"{data.get('name', '')} {data.get('specialty', '')} {data.get('bio', '')} {procs} {certs}"
    )


def _review_text(data: dict) -> str:
    return f"{data.get('title', '')} {data.get('content', '')}"


_TEXT_EXTRACTORS = {
    "procedures": _procedure_text,
    "doctors": _doctor_text,
    "reviews": _review_text,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize(data: dict) -> dict:
    """Convert non-JSON-serializable types (date → ISO string) and normalize field names."""
    result = {}
    for k, v in data.items():
        key = "date" if k == "review_date" else k
        result[key] = v.isoformat() if isinstance(v, date) else v
    return result


def _strip_embedding(source: dict) -> dict:
    source.pop("embedding", None)
    return source


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


async def create_document(
    client: OpenSearch,
    doc_type: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    doc_id = str(uuid.uuid4())
    body = _serialize({**data, "id": doc_id})

    text_fn = _TEXT_EXTRACTORS.get(doc_type)
    if text_fn:
        body["embedding"] = await embed_async(text_fn(body))

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, partial(index_document, client, doc_type, doc_id, body))

    logger.info("document_created", doc_type=doc_type, doc_id=doc_id)
    return {**_strip_embedding(body), "id": doc_id}


async def get_document_by_id(
    client: OpenSearch,
    doc_type: str,
    doc_id: str,
) -> dict[str, Any] | None:
    loop = asyncio.get_running_loop()
    resp = await loop.run_in_executor(None, partial(get_document, client, doc_type, doc_id))
    if resp is None or not resp.get("found"):
        return None
    return _strip_embedding(resp["_source"])


async def update_document(
    client: OpenSearch,
    doc_type: str,
    doc_id: str,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    loop = asyncio.get_running_loop()

    existing = await loop.run_in_executor(None, partial(get_document, client, doc_type, doc_id))
    if existing is None or not existing.get("found"):
        return None

    body = _serialize({**existing["_source"], **data, "id": doc_id})

    text_fn = _TEXT_EXTRACTORS.get(doc_type)
    if text_fn:
        body["embedding"] = await embed_async(text_fn(body))

    await loop.run_in_executor(None, partial(index_document, client, doc_type, doc_id, body))

    logger.info("document_updated", doc_type=doc_type, doc_id=doc_id)
    return _strip_embedding({k: v for k, v in body.items()})


async def delete_document_by_id(
    client: OpenSearch,
    doc_type: str,
    doc_id: str,
) -> bool:
    loop = asyncio.get_running_loop()
    deleted = await loop.run_in_executor(None, partial(delete_document, client, doc_type, doc_id))
    if deleted:
        logger.info("document_deleted", doc_type=doc_type, doc_id=doc_id)
    return deleted
