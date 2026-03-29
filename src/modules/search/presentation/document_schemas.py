"""Pydantic schemas for CRUD operations on indexed documents."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

# Keep in sync with DocumentField in schemas.py (OpenSearch _source values)
DocumentField = str | int | float | bool | list[str] | list[int] | list[float] | None

# ---------------------------------------------------------------------------
# Procedure
# ---------------------------------------------------------------------------


class ProcedureCreate(BaseModel):
    """Aesthetic or reconstructive medical procedure."""

    name: str = Field(
        ..., min_length=1, description="Official procedure name", examples=["Rhinoplasty"]
    )
    category: str = Field(..., description="Procedure category", examples=["Facial"])
    body_area: str = Field(..., description="Target body area", examples=["Nose"])
    description: str = Field("", description="Detailed description of the procedure")
    is_surgical: bool = Field(False, description="Whether the procedure requires surgery")
    recovery_days: int = Field(0, ge=0, description="Typical recovery time in days")
    average_cost_usd: int = Field(0, ge=0, description="Average procedure cost in USD")
    average_rating: float = Field(0.0, ge=0.0, le=5.0, description="Average patient rating (0–5)")
    review_count: int = Field(0, ge=0, description="Total number of patient reviews")
    tags: list[str] = Field(
        default_factory=list,
        description="Searchable tags",
        examples=[["anti-aging", "rejuvenation"]],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Rhinoplasty",
                    "category": "Facial",
                    "body_area": "Nose",
                    "description": "Surgical reshaping of the nose to improve appearance or breathing.",
                    "is_surgical": True,
                    "recovery_days": 14,
                    "average_cost_usd": 8500,
                    "average_rating": 4.2,
                    "review_count": 0,
                    "tags": ["facial-harmony", "anti-aging", "rejuvenation"],
                }
            ]
        }
    }


class ProcedureResponse(ProcedureCreate):
    id: str = Field(..., description="Unique document ID (UUID)")


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


class DoctorCreate(BaseModel):
    """Board-certified medical doctor performing aesthetic procedures."""

    name: str = Field(
        ..., min_length=1, description="Full name with title", examples=["Dr. Sarah Johnson"]
    )
    specialty: str = Field(..., description="Medical specialty", examples=["Plastic Surgeon"])
    city: str = Field("", description="Practice city", examples=["New York"])
    state: str = Field("", description="Practice state (2-letter code)", examples=["NY"])
    years_experience: int = Field(0, ge=0, description="Years of clinical experience")
    average_rating: float = Field(0.0, ge=0.0, le=5.0, description="Average patient rating (0–5)")
    review_count: int = Field(0, ge=0, description="Total number of patient reviews")
    bio: str = Field("", description="Professional biography")
    certifications: list[str] = Field(
        default_factory=list,
        description="Board certifications",
        examples=[["American Board of Plastic Surgery"]],
    )
    procedures_performed: list[str] = Field(
        default_factory=list,
        description="Procedures this doctor specialises in",
        examples=[["Rhinoplasty", "Facelift", "Brow Lift"]],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Dr. Sarah Johnson",
                    "specialty": "Plastic Surgeon",
                    "city": "New York",
                    "state": "NY",
                    "years_experience": 15,
                    "average_rating": 4.7,
                    "review_count": 0,
                    "bio": "Dr. Johnson is a board-certified plastic surgeon specialising in facial rejuvenation and body contouring.",
                    "certifications": [
                        "American Board of Plastic Surgery",
                        "American Society of Aesthetic Plastic Surgery",
                    ],
                    "procedures_performed": [
                        "Rhinoplasty",
                        "Facelift",
                        "Brow Lift",
                        "Botox Injections",
                    ],
                }
            ]
        }
    }


class DoctorResponse(DoctorCreate):
    id: str = Field(..., description="Unique document ID (UUID)")


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


class ReviewCreate(BaseModel):
    """Patient review of a procedure or doctor."""

    procedure_id: str = Field("", description="ID of the reviewed procedure (if applicable)")
    procedure_name: str = Field(
        "", description="Name of the reviewed procedure", examples=["Rhinoplasty"]
    )
    doctor_id: str = Field("", description="ID of the treating doctor (if applicable)")
    doctor_name: str = Field(
        "", description="Name of the treating doctor", examples=["Dr. Sarah Johnson"]
    )
    rating: int = Field(..., ge=1, le=5, description="Overall satisfaction rating (1–5 stars)")
    title: str = Field(
        ..., min_length=1, description="Short review headline", examples=["Life-changing results!"]
    )
    content: str = Field(..., min_length=1, description="Full review text")
    review_date: date = Field(
        default_factory=date.today, description="Date of the review (YYYY-MM-DD)"
    )
    helpful_count: int = Field(0, ge=0, description="Number of users who found this review helpful")
    verified: bool = Field(False, description="Whether the procedure was verified by the clinic")
    worth_it: Literal["Excellent", "Good", "Not Worth It"] = Field(
        "Good", description="Patient's overall verdict"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "procedure_id": "",
                    "procedure_name": "Rhinoplasty",
                    "doctor_id": "",
                    "doctor_name": "Dr. Sarah Johnson",
                    "rating": 5,
                    "title": "Life-changing results, highly recommend!",
                    "content": "I had my rhinoplasty done six months ago and the results are beyond my expectations. Recovery was manageable and Dr. Johnson was incredibly supportive throughout the entire process.",
                    "review_date": "2025-09-15",
                    "helpful_count": 0,
                    "verified": True,
                    "worth_it": "Excellent",
                }
            ]
        }
    }


class ReviewResponse(ReviewCreate):
    id: str = Field(..., description="Unique document ID (UUID)")


# ---------------------------------------------------------------------------
# Generic document response (for GET)
# ---------------------------------------------------------------------------


class DocumentResponse(BaseModel):
    """Raw document as stored in OpenSearch."""

    id: str = Field(..., description="Document UUID")
    index: str = Field(..., description="OpenSearch index name")
    source: dict[str, DocumentField] = Field(..., description="Full document fields")


# ---------------------------------------------------------------------------
# Type maps — used by router and service
# ---------------------------------------------------------------------------

DOC_TYPES = Literal["procedures", "doctors", "reviews"]

CREATE_SCHEMA: dict[str, type[BaseModel]] = {
    "procedures": ProcedureCreate,
    "doctors": DoctorCreate,
    "reviews": ReviewCreate,
}

RESPONSE_SCHEMA: dict[str, type[BaseModel]] = {
    "procedures": ProcedureResponse,
    "doctors": DoctorResponse,
    "reviews": ReviewResponse,
}
