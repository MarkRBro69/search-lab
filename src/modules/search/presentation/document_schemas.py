"""Pydantic schemas for CRUD operations on indexed documents."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Keep in sync with DocumentField in schemas.py (OpenSearch _source values)
DocumentField = (
    str | int | float | bool | list[str] | list[int] | list[float] | dict[str, object] | None
)


# ---------------------------------------------------------------------------
# Generic document response (for GET)
# ---------------------------------------------------------------------------


class DocumentResponse(BaseModel):
    """Raw document as stored in OpenSearch."""

    id: str = Field(..., description="Document UUID")
    index: str = Field(..., description="OpenSearch index name")
    source: dict[str, DocumentField] = Field(..., description="Full document fields")


class GenericDocumentRequest(BaseModel):
    """Arbitrary document body for a logical index (shape is profile-specific)."""

    data: dict[str, object] = Field(..., description="Document fields to store")


class GenericDocumentResponse(BaseModel):
    """Indexed document metadata and source."""

    id: str = Field(..., description="Document ID")
    index: str = Field(..., description="Physical OpenSearch index name")
    source: dict[str, object] = Field(
        ..., description="Stored document source (no embedding vector)"
    )
