import re
import secrets
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.auth import get_current_user
from app.database import PROJECT_ROOT, get_connection


router = APIRouter(prefix="/api/grievances", tags=["grievances"])
UPLOAD_DIRECTORY = PROJECT_ROOT / "uploads"
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
}
DISTRICTS = (
    "Alappuzha",
    "Ernakulam",
    "Idukki",
    "Kannur",
    "Kasaragod",
    "Kollam",
    "Kottayam",
    "Kozhikode",
    "Malappuram",
    "Palakkad",
    "Pathanamthitta",
    "Thiruvananthapuram",
    "Thrissur",
    "Wayanad",
)
CATEGORIES = (
    "Public Infrastructure",
    "Healthcare",
    "Education",
    "Public Services",
    "Water and Sanitation",
    "Other",
)


def _require_citizen(user):
    if user["role"] != "citizen":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is available to citizen accounts only.",
        )


def _safe_original_filename(filename: str) -> str:
    return PureWindowsPath(PurePosixPath(filename).name).name[:255]


async def _read_attachment(upload: UploadFile | None):
    if upload is None or not upload.filename:
        return None

    original_filename = _safe_original_filename(upload.filename)
    extension = Path(original_filename).suffix.lower()
    allowed_type = ALLOWED_ATTACHMENT_TYPES.get(extension)
    if allowed_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Attachments must be PDF, PNG, JPG, or JPEG files.",
        )

    content = await upload.read(MAX_ATTACHMENT_BYTES + 1)
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Attachment must be 5 MB or smaller.",
        )
    expected_content_type, signature = allowed_type
    if not content.startswith(signature):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The attachment content does not match its file type.",
        )

    return {
        "original_filename": original_filename,
        "stored_filename": f"{secrets.token_hex(16)}{extension}",
        "content_type": expected_content_type,
        "content": content,
    }


def _grievance_query():
    return """
        SELECT grievances.*, departments.name AS department_name
        FROM grievances
        LEFT JOIN departments ON departments.id = grievances.assigned_department_id
    """


def _serialize_grievance(row, history=None, attachments=None):
    result = dict(row)
    result.pop("citizen_id", None)
    result.pop("assigned_department_id", None)
    result["department"] = result.pop("department_name")
    if history is not None:
        result["history"] = [dict(item) for item in history]
    if attachments is not None:
        result["attachments"] = [dict(item) for item in attachments]
    return result


@router.get("/options")
def grievance_options():
    return {"districts": DISTRICTS, "categories": CATEGORIES}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_grievance(
    district: str = Form(min_length=1, max_length=40),
    category: str = Form(min_length=1, max_length=60),
    subject: str = Form(min_length=5, max_length=150),
    description: str = Form(min_length=20, max_length=5000),
    ai_suggestion_id: int | None = Form(default=None, gt=0),
    attachment: UploadFile | None = File(default=None),
    user=Depends(get_current_user),
):
    _require_citizen(user)
    district = district.strip()
    category = category.strip()
    subject = subject.strip()
    description = description.strip()
    if district not in DISTRICTS:
        raise HTTPException(status_code=422, detail="Choose a valid Kerala district.")
    if category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="Choose a valid grievance category.")
    if len(subject) < 5 or len(description) < 20:
        raise HTTPException(
            status_code=422,
            detail="Subject must be at least 5 characters and description at least 20.",
        )

    if ai_suggestion_id is not None:
        description_hash = hashlib.sha256(description.encode("utf-8")).hexdigest()
        subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()
        with get_connection() as connection:
            suggestion = connection.execute(
                """
                SELECT id FROM ai_suggestions
                WHERE id = ? AND user_id = ? AND grievance_id IS NULL
                  AND subject_hash = ? AND description_hash = ?
                """,
                (ai_suggestion_id, user["id"], subject_hash, description_hash),
            ).fetchone()
        if suggestion is None:
            raise HTTPException(
                status_code=422,
                detail="AI suggestion is not valid for this account or complaint text.",
            )

    attachment_data = await _read_attachment(attachment)
    reference_number = f"GMK-{datetime.now().year}-{secrets.token_hex(4).upper()}"
    saved_file = None
    if attachment_data is not None:
        UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
        saved_file = UPLOAD_DIRECTORY / attachment_data["stored_filename"]
        saved_file.write_bytes(attachment_data["content"])

    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO grievances (
                    reference_number, citizen_id, district, category, subject,
                    description, status
                )
                VALUES (?, ?, ?, ?, ?, ?, 'Submitted')
                """,
                (
                    reference_number,
                    user["id"],
                    district,
                    category,
                    subject,
                    description,
                ),
            )
            grievance_id = cursor.lastrowid
            if ai_suggestion_id is not None:
                linked = connection.execute(
                    """
                    UPDATE ai_suggestions
                    SET grievance_id = ?
                    WHERE id = ? AND user_id = ? AND grievance_id IS NULL
                      AND subject_hash = ? AND description_hash = ?
                    """,
                    (
                        grievance_id,
                        ai_suggestion_id,
                        user["id"],
                        hashlib.sha256(subject.encode("utf-8")).hexdigest(),
                        hashlib.sha256(description.encode("utf-8")).hexdigest(),
                    ),
                )
                if linked.rowcount != 1:
                    raise HTTPException(
                        status_code=409,
                        detail="This AI suggestion has already been used. Analyze the complaint again.",
                    )
            connection.execute(
                """
                INSERT INTO grievance_history (
                    grievance_id, previous_status, new_status,
                    changed_by_user_id, remark
                )
                VALUES (?, NULL, 'Submitted', ?, 'Grievance submitted by citizen')
                """,
                (grievance_id, user["id"]),
            )
            if attachment_data is not None:
                connection.execute(
                    """
                    INSERT INTO attachments (
                        grievance_id, uploaded_by_user_id, original_filename,
                        stored_filename, content_type
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        grievance_id,
                        user["id"],
                        attachment_data["original_filename"],
                        attachment_data["stored_filename"],
                        attachment_data["content_type"],
                    ),
                )
    except HTTPException:
        if saved_file is not None:
            saved_file.unlink(missing_ok=True)
        raise
    except sqlite3.IntegrityError as exc:
        if saved_file is not None:
            saved_file.unlink(missing_ok=True)
        if "reference_number" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not generate a unique reference number. Please retry.",
            ) from exc
        raise
    except sqlite3.Error:
        if saved_file is not None:
            saved_file.unlink(missing_ok=True)
        raise

    with get_connection() as connection:
        created_at = connection.execute(
            "SELECT created_at FROM grievances WHERE id = ?", (grievance_id,)
        ).fetchone()["created_at"]
    return {
        "id": grievance_id,
        "reference_number": reference_number,
        "status": "Submitted",
        "created_at": created_at,
        "message": "Grievance submitted successfully.",
    }


@router.get("")
def list_my_grievances(user=Depends(get_current_user)):
    _require_citizen(user)
    with get_connection() as connection:
        rows = connection.execute(
            _grievance_query()
            + " WHERE grievances.citizen_id = ? ORDER BY grievances.created_at DESC",
            (user["id"],),
        ).fetchall()
    grievances = [_serialize_grievance(row) for row in rows]
    return {
        "total": len(grievances),
        "pending": sum(item["status"] != "Resolved" for item in grievances),
        "resolved": sum(item["status"] == "Resolved" for item in grievances),
        "grievances": grievances,
    }


@router.get("/{reference_number}")
def get_my_grievance(reference_number: str, user=Depends(get_current_user)):
    _require_citizen(user)
    if not re.fullmatch(r"GMK-\d{4}-[A-F0-9]{8}", reference_number.upper()):
        raise HTTPException(status_code=404, detail="Grievance not found.")

    with get_connection() as connection:
        row = connection.execute(
            _grievance_query()
            + """
            WHERE grievances.reference_number = ? AND grievances.citizen_id = ?
            """,
            (reference_number.upper(), user["id"]),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Grievance not found.")
        history = connection.execute(
            """
            SELECT grievance_history.new_status, grievance_history.remark,
                   grievance_history.created_at, users.name AS changed_by
            FROM grievance_history
            JOIN users ON users.id = grievance_history.changed_by_user_id
            WHERE grievance_history.grievance_id = ?
            ORDER BY grievance_history.created_at, grievance_history.id
            """,
            (row["id"],),
        ).fetchall()
        attachments = connection.execute(
            """
            SELECT id, original_filename, content_type, created_at
            FROM attachments WHERE grievance_id = ?
            ORDER BY id
            """,
            (row["id"],),
        ).fetchall()
        accepted_report = None
        if row["status"] == "Resolved":
            accepted_report = connection.execute(
                """
                SELECT resolution_details
                FROM department_reports
                WHERE grievance_id = ? AND review_status = 'Accepted'
                ORDER BY reviewed_at DESC, id DESC
                LIMIT 1
                """,
                (row["id"],),
            ).fetchone()
        ai_suggestion = connection.execute(
            """
            SELECT suggested_department, category, priority, summary,
                   duplicate_possible, source, model, created_at
            FROM ai_suggestions
            WHERE grievance_id = ? AND user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (row["id"], user["id"]),
        ).fetchone()
        feedback = connection.execute(
            "SELECT id FROM citizen_feedback WHERE grievance_id = ?",
            (row["id"],),
        ).fetchone()

    result = _serialize_grievance(row, history, attachments)
    result["resolution_details"] = (
        accepted_report["resolution_details"] if accepted_report else None
    )
    result["feedback_submitted"] = feedback is not None
    result["ai_suggestion"] = (
        {
            **dict(ai_suggestion),
            "duplicate_possible": bool(ai_suggestion["duplicate_possible"]),
            "requires_human_review": True,
        }
        if ai_suggestion
        else None
    )
    return result


@router.get("/{reference_number}/attachments/{attachment_id}")
def download_my_attachment(
    reference_number: str,
    attachment_id: int,
    user=Depends(get_current_user),
):
    _require_citizen(user)
    with get_connection() as connection:
        attachment = connection.execute(
            """
            SELECT attachments.stored_filename, attachments.original_filename,
                   attachments.content_type
            FROM attachments
            JOIN grievances ON grievances.id = attachments.grievance_id
            WHERE grievances.reference_number = ?
              AND grievances.citizen_id = ?
              AND attachments.id = ?
            """,
            (reference_number.upper(), user["id"], attachment_id),
        ).fetchone()

    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    file_path = UPLOAD_DIRECTORY / attachment["stored_filename"]
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file is unavailable.")
    return FileResponse(
        file_path,
        media_type=attachment["content_type"],
        filename=attachment["original_filename"],
    )
