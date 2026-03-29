"""CRUD router for indexed documents (procedures, doctors, reviews)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from opensearchpy import OpenSearch

from src.modules.search.application.indexing_service import (
    create_document,
    delete_document_by_id,
    get_document_by_id,
    update_document,
)
from src.modules.search.presentation.document_schemas import (
    CREATE_SCHEMA,
    DOC_TYPES,
    RESPONSE_SCHEMA,
    DocumentResponse,
)
from src.shared.infrastructure.opensearch import get_client

router = APIRouter(prefix="/documents", tags=["documents"])


def _os_client() -> OpenSearch:
    return get_client()


OSClient = Annotated[OpenSearch, Depends(_os_client)]

_DOC_TYPE_PATH = Path(
    description="Document collection: **procedures**, **doctors**, or **reviews**",
    openapi_examples={
        "procedures": {"summary": "Procedures", "value": "procedures"},
        "doctors": {"summary": "Doctors", "value": "doctors"},
        "reviews": {"summary": "Reviews", "value": "reviews"},
    },
)
_DOC_ID_PATH = Path(description="Document UUID returned by the create endpoint")


def _validate_type(doc_type: str) -> None:
    if doc_type not in CREATE_SCHEMA:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown document type '{doc_type}'. Must be one of: {list(CREATE_SCHEMA)}",
        )


def _build_response(doc_type: str, source: dict[str, Any]) -> dict:
    schema = RESPONSE_SCHEMA[doc_type]
    return schema.model_validate(source).model_dump()


# ---------------------------------------------------------------------------
# Examples for request bodies
# ---------------------------------------------------------------------------

_PROCEDURE_EXAMPLE = {
    "name": "Laser Skin Resurfacing",
    "category": "Skin",
    "body_area": "Face",
    "description": "Advanced CO2 laser treatment to improve skin texture, reduce wrinkles and age spots.",
    "is_surgical": False,
    "recovery_days": 7,
    "average_cost_usd": 2800,
    "average_rating": 4.5,
    "review_count": 0,
    "tags": ["anti-aging", "skin-texture", "rejuvenation"],
}

_DOCTOR_EXAMPLE = {
    "name": "Dr. Emily Carter",
    "specialty": "Dermatologist",
    "city": "Los Angeles",
    "state": "CA",
    "years_experience": 12,
    "average_rating": 4.9,
    "review_count": 0,
    "bio": "Dr. Carter is a board-certified dermatologist specialising in laser treatments and skin rejuvenation.",
    "certifications": ["American Board of Dermatology"],
    "procedures_performed": ["Laser Skin Resurfacing", "Botox Injections", "Chemical Peel"],
}

_REVIEW_EXAMPLE = {
    "procedure_name": "Laser Skin Resurfacing",
    "doctor_name": "Dr. Emily Carter",
    "rating": 5,
    "title": "Amazing results after just one session!",
    "content": "My skin looks 10 years younger. Minimal downtime and the staff was very professional.",
    "review_date": "2025-11-20",
    "helpful_count": 0,
    "verified": True,
    "worth_it": "Excellent",
}

_CREATE_EXAMPLES = {
    "procedure": {"summary": "New procedure", "value": _PROCEDURE_EXAMPLE},
    "doctor": {"summary": "New doctor", "value": _DOCTOR_EXAMPLE},
    "review": {"summary": "New review", "value": _REVIEW_EXAMPLE},
}

_UPDATE_PROCEDURE_EXAMPLE = {
    **_PROCEDURE_EXAMPLE,
    "average_rating": 4.8,
    "review_count": 24,
    "average_cost_usd": 3200,
}
_UPDATE_DOCTOR_EXAMPLE = {
    **_DOCTOR_EXAMPLE,
    "average_rating": 4.6,
    "review_count": 37,
    "years_experience": 13,
}
_UPDATE_REVIEW_EXAMPLE = {**_REVIEW_EXAMPLE, "helpful_count": 15, "rating": 4, "worth_it": "Good"}

_UPDATE_EXAMPLES = {
    "procedure": {"summary": "Update procedure", "value": _UPDATE_PROCEDURE_EXAMPLE},
    "doctor": {"summary": "Update doctor", "value": _UPDATE_DOCTOR_EXAMPLE},
    "review": {"summary": "Update review", "value": _UPDATE_REVIEW_EXAMPLE},
}


# ---------------------------------------------------------------------------
# CREATE  POST /documents/{doc_type}
# ---------------------------------------------------------------------------


@router.post(
    "/{doc_type}",
    status_code=status.HTTP_201_CREATED,
    summary="Create a document",
    description="""
Create a new document in the specified collection and automatically generate its **semantic embedding**.

The document is immediately available for both **BM25** and **semantic/hybrid** search after creation.

### Supported types
| `doc_type`    | Description                                  |
|---------------|----------------------------------------------|
| `procedures`  | Aesthetic or reconstructive procedure        |
| `doctors`     | Board-certified doctor or specialist         |
| `reviews`     | Patient review of a procedure or doctor      |

### Embedding
A 384-dimensional vector is generated using `all-MiniLM-L6-v2` from the most relevant text fields
(name, description, tags for procedures; name, bio, specialty for doctors; title + content for reviews).
""",
    responses={
        201: {"description": "Document created and indexed successfully"},
        422: {"description": "Validation error or unknown document type"},
    },
)
async def create(
    client: OSClient,
    doc_type: Annotated[DOC_TYPES, _DOC_TYPE_PATH],
    body: Annotated[dict[str, Any], Body(openapi_examples=_CREATE_EXAMPLES)],
) -> dict:
    _validate_type(doc_type)
    validated = CREATE_SCHEMA[doc_type].model_validate(body).model_dump()
    result = await create_document(client, doc_type, validated)
    return _build_response(doc_type, result)


# ---------------------------------------------------------------------------
# READ  GET /documents/{doc_type}/{doc_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{doc_type}/{doc_id}",
    response_model=DocumentResponse,
    summary="Get a document by ID",
    description="""
Retrieve a single document by its **UUID**.

Returns the full source object as stored in OpenSearch (without the embedding vector).
Use the `id` returned from the **create** endpoint.
""",
    responses={
        200: {"description": "Document found"},
        404: {"description": "Document not found"},
    },
)
async def read(
    client: OSClient,
    doc_type: Annotated[DOC_TYPES, _DOC_TYPE_PATH],
    doc_id: Annotated[str, _DOC_ID_PATH],
) -> DocumentResponse:
    _validate_type(doc_type)
    source = await get_document_by_id(client, doc_type, doc_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    from src.modules.search.infrastructure.repository import INDEX_ALIAS

    return DocumentResponse(
        id=doc_id,
        index=INDEX_ALIAS.get(doc_type, doc_type),
        source=source,
    )


# ---------------------------------------------------------------------------
# UPDATE  PUT /documents/{doc_type}/{doc_id}
# ---------------------------------------------------------------------------


@router.put(
    "/{doc_type}/{doc_id}",
    summary="Update a document",
    description="""
**Full replacement** of an existing document (PUT semantics — all fields must be provided).

After updating, the **semantic embedding is automatically regenerated** from the new field values,
so the document will appear correctly in semantic and hybrid search results.

> **Note:** partial updates (PATCH) are not supported. Send the complete document.
""",
    responses={
        200: {"description": "Document updated and re-indexed"},
        404: {"description": "Document not found"},
        422: {"description": "Validation error"},
    },
)
async def update(
    client: OSClient,
    doc_type: Annotated[DOC_TYPES, _DOC_TYPE_PATH],
    doc_id: Annotated[str, _DOC_ID_PATH],
    body: Annotated[dict[str, Any], Body(openapi_examples=_UPDATE_EXAMPLES)],
) -> dict:
    _validate_type(doc_type)
    validated = CREATE_SCHEMA[doc_type].model_validate(body).model_dump()
    result = await update_document(client, doc_type, doc_id, validated)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _build_response(doc_type, result)


# ---------------------------------------------------------------------------
# DELETE  DELETE /documents/{doc_type}/{doc_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/{doc_type}/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    description="""
Permanently remove a document from the OpenSearch index.

Returns **204 No Content** on success. The document is immediately removed from all search results.
Returns **404** if the document does not exist.
""",
    responses={
        204: {"description": "Document deleted successfully"},
        404: {"description": "Document not found"},
    },
)
async def delete(
    client: OSClient,
    doc_type: Annotated[DOC_TYPES, _DOC_TYPE_PATH],
    doc_id: Annotated[str, _DOC_ID_PATH],
) -> None:
    _validate_type(doc_type)
    deleted = await delete_document_by_id(client, doc_type, doc_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
