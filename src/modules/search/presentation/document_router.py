"""CRUD router for indexed documents — logical index keys come from the active profile."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Path, status
from opensearchpy.exceptions import TransportError

from src.modules.profiles.api import ActiveProfileBundle, get_active_profile_bundle
from src.modules.search.application.indexing_service import (
    create_document,
    delete_document_by_id,
    get_document_by_id,
    update_document,
)
from src.modules.search.presentation.document_schemas import (
    GenericDocumentRequest,
    GenericDocumentResponse,
)
from src.shared.exceptions import (
    DOCUMENT_NOT_FOUND,
    INVALID_INDEX_KEY,
    SEARCH_UNAVAILABLE,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)

logger = structlog.get_logger(module="search")

router = APIRouter(prefix="/documents", tags=["documents"])

ProfileBundle = Annotated[ActiveProfileBundle, Depends(get_active_profile_bundle)]

_INDEX_KEY_PATH = Path(
    description="Logical index key configured on the active connection profile (not `all` for writes)",
    openapi_examples={
        "products": {"summary": "Products index", "value": "products"},
        "articles": {"summary": "Articles index", "value": "articles"},
    },
)
_DOC_ID_PATH = Path(description="Document UUID returned by the create endpoint")


def _validate_index_key(bundle: ActiveProfileBundle, index_key: str, *, for_write: bool) -> None:
    if index_key not in bundle.indices.indices:
        raise UnprocessableEntityError(
            code=INVALID_INDEX_KEY,
            detail=f"Unknown index key {index_key!r} for the active profile",
        )
    if for_write and index_key == "all":
        raise UnprocessableEntityError(
            code=INVALID_INDEX_KEY,
            detail="Write operations cannot target logical index key 'all'",
        )


def _physical_index(bundle: ActiveProfileBundle, index_key: str) -> str:
    return bundle.to_alias_map()[index_key]


def _source_from_result(result: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in result.items() if k != "id"}


# ---------------------------------------------------------------------------
# CREATE  POST /documents/{index_key}
# ---------------------------------------------------------------------------


@router.post(
    "/{index_key}",
    response_model=GenericDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a document",
    description="""
Create a new document in the logical index and generate a **semantic embedding**.

The body is a generic JSON object; optional `embedding_text` overrides the text used for the vector.
Otherwise, embedding text is derived from all string field values.

Write operations cannot use the logical key `all` (use a specific named index).
""",
    responses={
        201: {"description": "Document created and indexed successfully"},
        422: {"description": "Unknown index key or invalid target"},
    },
)
async def create(
    bundle: ProfileBundle,
    index_key: Annotated[str, _INDEX_KEY_PATH],
    body: GenericDocumentRequest,
) -> GenericDocumentResponse:
    log = logger.bind(operation="document_create")
    _validate_index_key(bundle, index_key, for_write=True)
    index_alias = bundle.to_alias_map()
    try:
        result = await create_document(
            bundle.opensearch_client,
            index_key,
            body.data,
            index_alias,
            bundle.embed,
        )
    except TransportError as err:
        raise ServiceUnavailableError(
            code=SEARCH_UNAVAILABLE,
            detail="Search service temporarily unavailable",
        ) from err
    doc_id = str(result["id"])
    source = _source_from_result(result)
    log.info("document_create_ok", index_key=index_key, doc_id=doc_id)
    return GenericDocumentResponse(
        id=doc_id,
        index=_physical_index(bundle, index_key),
        source=source,
    )


# ---------------------------------------------------------------------------
# READ  GET /documents/{index_key}/{doc_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{index_key}/{doc_id}",
    response_model=GenericDocumentResponse,
    summary="Get a document by ID",
    description="Retrieve a single document by UUID from the named logical index.",
    responses={
        200: {"description": "Document found"},
        404: {"description": "Document not found"},
    },
)
async def read(
    bundle: ProfileBundle,
    index_key: Annotated[str, _INDEX_KEY_PATH],
    doc_id: Annotated[str, _DOC_ID_PATH],
) -> GenericDocumentResponse:
    log = logger.bind(operation="document_read")
    _validate_index_key(bundle, index_key, for_write=False)
    index_alias = bundle.to_alias_map()
    try:
        source = await get_document_by_id(bundle.opensearch_client, index_key, doc_id, index_alias)
    except TransportError as err:
        raise ServiceUnavailableError(
            code=SEARCH_UNAVAILABLE,
            detail="Search service temporarily unavailable",
        ) from err
    if source is None:
        raise NotFoundError(code=DOCUMENT_NOT_FOUND, detail="Document not found")

    log.info("document_read_ok", index_key=index_key, doc_id=doc_id)
    return GenericDocumentResponse(
        id=doc_id,
        index=_physical_index(bundle, index_key),
        source=source,
    )


# ---------------------------------------------------------------------------
# UPDATE  PUT /documents/{index_key}/{doc_id}
# ---------------------------------------------------------------------------


@router.put(
    "/{index_key}/{doc_id}",
    response_model=GenericDocumentResponse,
    summary="Update a document",
    description="""
Replace an existing document (PUT semantics). The embedding is regenerated from the new data.
""",
    responses={
        200: {"description": "Document updated and re-indexed"},
        404: {"description": "Document not found"},
        422: {"description": "Validation error"},
    },
)
async def update(
    bundle: ProfileBundle,
    index_key: Annotated[str, _INDEX_KEY_PATH],
    doc_id: Annotated[str, _DOC_ID_PATH],
    body: GenericDocumentRequest,
) -> GenericDocumentResponse:
    log = logger.bind(operation="document_update")
    _validate_index_key(bundle, index_key, for_write=True)
    index_alias = bundle.to_alias_map()
    try:
        result = await update_document(
            bundle.opensearch_client,
            index_key,
            doc_id,
            body.data,
            index_alias,
            bundle.embed,
        )
    except TransportError as err:
        raise ServiceUnavailableError(
            code=SEARCH_UNAVAILABLE,
            detail="Search service temporarily unavailable",
        ) from err
    if result is None:
        raise NotFoundError(code=DOCUMENT_NOT_FOUND, detail="Document not found")
    source = _source_from_result({**result, "id": doc_id})
    log.info("document_update_ok", index_key=index_key, doc_id=doc_id)
    return GenericDocumentResponse(
        id=doc_id,
        index=_physical_index(bundle, index_key),
        source=source,
    )


# ---------------------------------------------------------------------------
# DELETE  DELETE /documents/{index_key}/{doc_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/{index_key}/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    description="Remove a document from the logical index.",
    responses={
        204: {"description": "Document deleted successfully"},
        404: {"description": "Document not found"},
    },
)
async def delete(
    bundle: ProfileBundle,
    index_key: Annotated[str, _INDEX_KEY_PATH],
    doc_id: Annotated[str, _DOC_ID_PATH],
) -> None:
    log = logger.bind(operation="document_delete")
    _validate_index_key(bundle, index_key, for_write=True)
    index_alias = bundle.to_alias_map()
    try:
        deleted = await delete_document_by_id(
            bundle.opensearch_client, index_key, doc_id, index_alias
        )
    except TransportError as err:
        raise ServiceUnavailableError(
            code=SEARCH_UNAVAILABLE,
            detail="Search service temporarily unavailable",
        ) from err
    if not deleted:
        raise NotFoundError(code=DOCUMENT_NOT_FOUND, detail="Document not found")
    log.info("document_delete_ok", index_key=index_key, doc_id=doc_id)
