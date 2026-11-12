import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import get_current_user
from app.database import get_connection


router = APIRouter(tags=["public services"])


class ContactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    subject: str = Field(min_length=3, max_length=150)
    message: str = Field(min_length=10, max_length=3000)

    @field_validator("name", "email", "subject", "message")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name", "subject", "message")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        if not value:
            raise ValueError("This field cannot be blank.")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)


@router.post("/api/contact", status_code=status.HTTP_201_CREATED)
def create_contact_enquiry(payload: ContactRequest):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO contact_enquiries (name, email, subject, message)
            VALUES (?, ?, ?, ?)
            """,
            (payload.name, payload.email, payload.subject, payload.message),
        )
    return {
        "id": cursor.lastrowid,
        "message": "Your enquiry has been received.",
    }


@router.post("/api/grievances/{reference_number}/feedback", status_code=status.HTTP_201_CREATED)
def create_grievance_feedback(
    reference_number: str,
    payload: FeedbackRequest,
    user=Depends(get_current_user),
):
    if user["role"] != "citizen":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feedback is available to citizen accounts only.",
        )

    with get_connection() as connection:
        grievance = connection.execute(
            """
            SELECT id, status FROM grievances
            WHERE reference_number = ? AND citizen_id = ?
            """,
            (reference_number.upper(), user["id"]),
        ).fetchone()
        if grievance is None:
            raise HTTPException(status_code=404, detail="Grievance not found.")
        if grievance["status"] != "Resolved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Feedback can be submitted after a grievance is resolved.",
            )
        try:
            cursor = connection.execute(
                """
                INSERT INTO citizen_feedback (grievance_id, citizen_id, rating, comment)
                VALUES (?, ?, ?, ?)
                """,
                (
                    grievance["id"],
                    user["id"],
                    payload.rating,
                    payload.comment.strip() or None,
                ),
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed: citizen_feedback.grievance_id" in str(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Feedback has already been submitted for this grievance.",
                ) from exc
            raise

    return {"id": cursor.lastrowid, "message": "Thank you for your feedback."}
