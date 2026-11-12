from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth import get_current_user
from app.database import get_connection


admin_router = APIRouter(prefix="/api/admin", tags=["CMO administration"])
officer_router = APIRouter(prefix="/api/officer", tags=["department officers"])


class AssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: int = Field(gt=0)
    officer_id: int | None = Field(default=None, gt=0)
    remark: str = Field(default="", max_length=1000)


class RemarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remark: str = Field(min_length=1, max_length=2000)


class OfficerUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remark: str = Field(min_length=1, max_length=2000)


class ActionReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_report: str = Field(min_length=20, max_length=5000)
    resolution_details: str = Field(min_length=10, max_length=3000)


class ReportReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(accept|return)$")
    remark: str = Field(min_length=1, max_length=2000)


class EscalationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=5, max_length=2000)


def _require_role(user, expected_role: str) -> None:
    if user["role"] != expected_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires the {expected_role} role.",
        )


def _latest_assignment_sql():
    return """
        LEFT JOIN department_assignments AS current_assignment
          ON current_assignment.id = (
              SELECT MAX(assignment.id)
              FROM department_assignments AS assignment
              WHERE assignment.grievance_id = grievances.id
          )
        LEFT JOIN users AS assigned_officer
          ON assigned_officer.id = current_assignment.assigned_to_user_id
    """


def _admin_grievance_select():
    return """
        SELECT grievances.*, departments.name AS department_name,
               citizens.name AS citizen_name, citizens.email AS citizen_email,
               assigned_officer.name AS officer_name,
               current_assignment.assigned_at AS assigned_at,
               (SELECT COUNT(*) FROM attachments
                WHERE attachments.grievance_id = grievances.id) AS attachment_count
        FROM grievances
        JOIN users AS citizens ON citizens.id = grievances.citizen_id
        LEFT JOIN departments ON departments.id = grievances.assigned_department_id
    """ + _latest_assignment_sql()


def _status_change(connection, grievance, new_status, actor_id, remark):
    old_status = grievance["status"]
    if old_status == new_status:
        return
    connection.execute(
        "UPDATE grievances SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_status, grievance["id"]),
    )
    connection.execute(
        """
        INSERT INTO grievance_history (
            grievance_id, previous_status, new_status, changed_by_user_id, remark
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (grievance["id"], old_status, new_status, actor_id, remark),
    )


def _require_grievance(connection, grievance_id: int):
    grievance = connection.execute(
        "SELECT * FROM grievances WHERE id = ?", (grievance_id,)
    ).fetchone()
    if grievance is None:
        raise HTTPException(status_code=404, detail="Grievance not found.")
    return grievance


def _require_officer_assignment(connection, grievance_id: int, user):
    assignment = connection.execute(
        """
        SELECT department_assignments.id
        FROM department_assignments
        WHERE department_assignments.grievance_id = ?
          AND department_assignments.department_id = ?
          AND department_assignments.id = (
              SELECT MAX(current_assignment.id)
              FROM department_assignments AS current_assignment
              WHERE current_assignment.grievance_id = ?
          )
          AND (
              department_assignments.assigned_to_user_id = ?
              OR department_assignments.assigned_to_user_id IS NULL
          )
        ORDER BY department_assignments.id DESC
        LIMIT 1
        """,
        (grievance_id, user["department_id"], grievance_id, user["id"]),
    ).fetchone()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assigned grievance not found.")


@admin_router.get("/stats")
def admin_stats(user=Depends(get_current_user)):
    _require_role(user, "admin")
    with get_connection() as connection:
        counts = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status IN ('Submitted', 'Under Review', 'In Progress', 'Reopened')
                       THEN 1 ELSE 0 END) AS pending,
                   SUM(CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END) AS resolved,
                   SUM(CASE WHEN status != 'Resolved'
                              AND julianday('now') - julianday(created_at) > 14
                       THEN 1 ELSE 0 END) AS overdue
            FROM grievances
            """
        ).fetchone()
        districts = connection.execute(
            """
            SELECT district, COUNT(*) AS total
            FROM grievances GROUP BY district ORDER BY total DESC, district
            """
        ).fetchall()
        departments = connection.execute(
            """
            SELECT departments.name AS department, COUNT(grievances.id) AS total
            FROM departments
            LEFT JOIN grievances
              ON grievances.assigned_department_id = departments.id
            GROUP BY departments.id ORDER BY total DESC, departments.name
            """
        ).fetchall()
    return {
        "total": counts["total"] or 0,
        "pending": counts["pending"] or 0,
        "resolved": counts["resolved"] or 0,
        "overdue": counts["overdue"] or 0,
        "by_district": [dict(row) for row in districts],
        "by_department": [dict(row) for row in departments],
    }


@admin_router.get("/departments")
def admin_departments(user=Depends(get_current_user)):
    _require_role(user, "admin")
    with get_connection() as connection:
        departments = connection.execute(
            "SELECT id, name, description FROM departments ORDER BY id"
        ).fetchall()
        officers = connection.execute(
            """
            SELECT id, name, department_id
            FROM users WHERE role = 'officer' AND department_id IS NOT NULL
            ORDER BY name
            """
        ).fetchall()
    officers_by_department = {}
    for officer in officers:
        officers_by_department.setdefault(officer["department_id"], []).append(
            {"id": officer["id"], "name": officer["name"]}
        )
    return [
        {
            **dict(department),
            "officers": officers_by_department.get(department["id"], []),
        }
        for department in departments
    ]


@admin_router.get("/grievances")
def admin_list_grievances(
    district: str | None = None,
    category: str | None = None,
    priority: str | None = Query(default=None, pattern="^(Low|Medium|High)$"),
    grievance_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(Submitted|Under Review|In Progress|Resolved|Reopened)$",
    ),
    user=Depends(get_current_user),
):
    _require_role(user, "admin")
    clauses = []
    values = []
    for column, value in (
        ("grievances.district", district),
        ("grievances.category", category),
        ("grievances.priority", priority),
        ("grievances.status", grievance_status),
    ):
        if value:
            clauses.append(f"{column} = ?")
            values.append(value)
    query = _admin_grievance_select()
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY grievances.created_at DESC"
    with get_connection() as connection:
        rows = connection.execute(query, values).fetchall()
    return [dict(row) for row in rows]


@admin_router.get("/grievances/{grievance_id}")
def admin_get_grievance(grievance_id: int, user=Depends(get_current_user)):
    _require_role(user, "admin")
    with get_connection() as connection:
        grievance = connection.execute(
            _admin_grievance_select() + " WHERE grievances.id = ?",
            (grievance_id,),
        ).fetchone()
        if grievance is None:
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
            (grievance_id,),
        ).fetchall()
        remarks = connection.execute(
            """
            SELECT grievance_internal_remarks.remark,
                   grievance_internal_remarks.created_at, users.name AS author
            FROM grievance_internal_remarks
            JOIN users ON users.id = grievance_internal_remarks.user_id
            WHERE grievance_internal_remarks.grievance_id = ?
            ORDER BY grievance_internal_remarks.created_at,
                     grievance_internal_remarks.id
            """,
            (grievance_id,),
        ).fetchall()
        attachments = connection.execute(
            """
            SELECT id, original_filename, content_type, created_at
            FROM attachments WHERE grievance_id = ? ORDER BY id
            """,
            (grievance_id,),
        ).fetchall()
        reports = connection.execute(
            """
            SELECT department_reports.*, users.name AS officer_name
            FROM department_reports
            JOIN users ON users.id = department_reports.officer_id
            WHERE department_reports.grievance_id = ?
            ORDER BY department_reports.submitted_at DESC
            """,
            (grievance_id,),
        ).fetchall()
        escalations = connection.execute(
            """
            SELECT grievance_escalations.reason, grievance_escalations.created_at,
                   users.name AS escalated_by
            FROM grievance_escalations
            JOIN users ON users.id = grievance_escalations.escalated_by_user_id
            WHERE grievance_escalations.grievance_id = ?
            ORDER BY grievance_escalations.created_at, grievance_escalations.id
            """,
            (grievance_id,),
        ).fetchall()
        ai_suggestion = connection.execute(
            """
            SELECT ai_suggestions.suggested_department, ai_suggestions.category,
                   ai_suggestions.priority, ai_suggestions.summary,
                   ai_suggestions.duplicate_possible, ai_suggestions.source,
                   ai_suggestions.model, ai_suggestions.created_at,
                   users.name AS suggested_by
            FROM ai_suggestions
            JOIN users ON users.id = ai_suggestions.user_id
            WHERE ai_suggestions.grievance_id = ?
            ORDER BY ai_suggestions.created_at DESC, ai_suggestions.id DESC
            LIMIT 1
            """,
            (grievance_id,),
        ).fetchone()
    return {
        **dict(grievance),
        "history": [dict(row) for row in history],
        "internal_remarks": [dict(row) for row in remarks],
        "attachments": [dict(row) for row in attachments],
        "reports": [dict(row) for row in reports],
        "escalations": [dict(row) for row in escalations],
        "ai_suggestion": (
            {
                **dict(ai_suggestion),
                "duplicate_possible": bool(ai_suggestion["duplicate_possible"]),
                "requires_human_review": True,
            }
            if ai_suggestion
            else None
        ),
    }


@admin_router.post("/grievances/{grievance_id}/review")
def admin_start_review(
    grievance_id: int,
    payload: RemarkRequest,
    user=Depends(get_current_user),
):
    _require_role(user, "admin")
    with get_connection() as connection:
        grievance = _require_grievance(connection, grievance_id)
        if grievance["status"] != "Submitted":
            raise HTTPException(
                status_code=409,
                detail="Only submitted grievances can enter CMO review.",
            )
        _status_change(
            connection,
            grievance,
            "Under Review",
            user["id"],
            payload.remark.strip(),
        )
    return {"message": "Grievance is now under CMO review.", "status": "Under Review"}


@admin_router.post("/grievances/{grievance_id}/assign")
def admin_assign_grievance(
    grievance_id: int,
    payload: AssignmentRequest,
    user=Depends(get_current_user),
):
    _require_role(user, "admin")
    remark = payload.remark.strip()
    with get_connection() as connection:
        grievance = _require_grievance(connection, grievance_id)
        if grievance["status"] == "Resolved":
            raise HTTPException(
                status_code=409,
                detail="Resolved grievances must be reopened before reassignment.",
            )
        if grievance["status"] == "Submitted":
            raise HTTPException(
                status_code=409,
                detail="Move the grievance to Under Review before forwarding it.",
            )
        department = connection.execute(
            "SELECT id FROM departments WHERE id = ?", (payload.department_id,)
        ).fetchone()
        if department is None:
            raise HTTPException(status_code=404, detail="Department not found.")
        if payload.officer_id is not None:
            officer = connection.execute(
                """
                SELECT id FROM users
                WHERE id = ? AND role = 'officer' AND department_id = ?
                """,
                (payload.officer_id, payload.department_id),
            ).fetchone()
            if officer is None:
                raise HTTPException(
                    status_code=422,
                    detail="Choose an officer assigned to the selected department.",
                )
        connection.execute(
            """
            UPDATE grievances
            SET assigned_department_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (payload.department_id, grievance_id),
        )
        connection.execute(
            """
            INSERT INTO department_assignments (
                grievance_id, department_id, assigned_by_user_id,
                assigned_to_user_id, remark
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                grievance_id,
                payload.department_id,
                user["id"],
                payload.officer_id,
                remark or None,
            ),
        )
        if grievance["status"] in ("Under Review", "Reopened"):
            _status_change(
                connection,
                grievance,
                "In Progress",
                user["id"],
                "Grievance forwarded to the assigned department",
            )
        if remark:
            connection.execute(
                """
                INSERT INTO grievance_internal_remarks (grievance_id, user_id, remark)
                VALUES (?, ?, ?)
                """,
                (grievance_id, user["id"], remark),
            )
    return {"message": "Grievance assigned to department.", "status": "In Progress"}


@admin_router.post("/grievances/{grievance_id}/remarks")
def admin_add_remark(
    grievance_id: int,
    payload: RemarkRequest,
    user=Depends(get_current_user),
):
    _require_role(user, "admin")
    with get_connection() as connection:
        _require_grievance(connection, grievance_id)
        connection.execute(
            """
            INSERT INTO grievance_internal_remarks (grievance_id, user_id, remark)
            VALUES (?, ?, ?)
            """,
            (grievance_id, user["id"], payload.remark.strip()),
        )
    return {"message": "Internal CMO remark saved."}


@admin_router.post("/grievances/{grievance_id}/escalate")
def admin_escalate_grievance(
    grievance_id: int,
    payload: EscalationRequest,
    user=Depends(get_current_user),
):
    _require_role(user, "admin")
    reason = payload.reason.strip()
    if len(reason) < 5:
        raise HTTPException(status_code=422, detail="Provide an escalation reason.")
    with get_connection() as connection:
        grievance = _require_grievance(connection, grievance_id)
        if grievance["status"] == "Resolved":
            raise HTTPException(
                status_code=409, detail="Resolved grievances cannot be escalated."
            )
        overdue = connection.execute(
            "SELECT julianday('now') - julianday(created_at) > 14 AS overdue "
            "FROM grievances WHERE id = ?",
            (grievance_id,),
        ).fetchone()["overdue"]
        if not overdue:
            raise HTTPException(
                status_code=409,
                detail="Only grievances open for more than 14 days can be escalated.",
            )
        connection.execute(
            """
            INSERT INTO grievance_escalations (grievance_id, escalated_by_user_id, reason)
            VALUES (?, ?, ?)
            """,
            (grievance_id, user["id"], reason),
        )
        connection.execute(
            """
            INSERT INTO grievance_internal_remarks (grievance_id, user_id, remark)
            VALUES (?, ?, ?)
            """,
            (grievance_id, user["id"], f"Escalated: {reason}"),
        )
    return {"message": "Grievance escalated for priority follow-up."}


@admin_router.post("/grievances/{grievance_id}/reopen")
def admin_reopen_grievance(
    grievance_id: int,
    payload: RemarkRequest,
    user=Depends(get_current_user),
):
    _require_role(user, "admin")
    with get_connection() as connection:
        grievance = _require_grievance(connection, grievance_id)
        if grievance["status"] != "Resolved":
            raise HTTPException(
                status_code=409, detail="Only resolved grievances can be reopened."
            )
        _status_change(
            connection,
            grievance,
            "Reopened",
            user["id"],
            payload.remark.strip(),
        )
    return {"message": "Grievance reopened.", "status": "Reopened"}


@admin_router.post("/reports/{report_id}/review")
def admin_review_report(
    report_id: int,
    payload: ReportReviewRequest,
    user=Depends(get_current_user),
):
    _require_role(user, "admin")
    remark = payload.remark.strip()
    with get_connection() as connection:
        report = connection.execute(
            "SELECT * FROM department_reports WHERE id = ?", (report_id,)
        ).fetchone()
        if report is None:
            raise HTTPException(status_code=404, detail="Department report not found.")
        if report["review_status"] != "Pending Review":
            raise HTTPException(
                status_code=409, detail="This report has already been reviewed."
            )
        grievance = _require_grievance(connection, report["grievance_id"])
        review_status = "Accepted" if payload.decision == "accept" else "Returned"
        connection.execute(
            """
            UPDATE department_reports
            SET review_status = ?, reviewed_by_user_id = ?, review_remark = ?,
                reviewed_at = ?
            WHERE id = ?
            """,
            (
                review_status,
                user["id"],
                remark,
                datetime.now(timezone.utc).isoformat(),
                report_id,
            ),
        )
        if payload.decision == "accept":
            _status_change(
                connection,
                grievance,
                "Resolved",
                user["id"],
                "CMO reviewed and accepted the department action report",
            )
        elif grievance["status"] != "In Progress":
            _status_change(
                connection,
                grievance,
                "In Progress",
                user["id"],
                "Department action report returned for further action",
            )
        else:
            connection.execute(
                """
                INSERT INTO grievance_history (
                    grievance_id, previous_status, new_status,
                    changed_by_user_id, remark
                )
                VALUES (?, 'In Progress', 'In Progress', ?, ?)
                """,
                (
                    grievance["id"],
                    user["id"],
                    "Department action report returned for further action",
                ),
            )
        connection.execute(
            """
            INSERT INTO grievance_internal_remarks (grievance_id, user_id, remark)
            VALUES (?, ?, ?)
            """,
            (grievance["id"], user["id"], f"Report {review_status.lower()}: {remark}"),
        )
    return {"message": f"Report {review_status.lower()}.", "status": review_status}


@admin_router.get("/grievances/{grievance_id}/attachments/{attachment_id}")
def admin_download_attachment(
    grievance_id: int,
    attachment_id: int,
    user=Depends(get_current_user),
):
    _require_role(user, "admin")
    from fastapi.responses import FileResponse

    from app.grievances import UPLOAD_DIRECTORY

    with get_connection() as connection:
        attachment = connection.execute(
            """
            SELECT stored_filename, original_filename, content_type
            FROM attachments WHERE grievance_id = ? AND id = ?
            """,
            (grievance_id, attachment_id),
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


@officer_router.get("/grievances")
def officer_list_grievances(user=Depends(get_current_user)):
    _require_role(user, "officer")
    if user["department_id"] is None:
        raise HTTPException(status_code=403, detail="Officer has no assigned department.")
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT grievances.id, grievances.reference_number, grievances.district,
                   grievances.category, grievances.subject, grievances.priority,
                   grievances.status, grievances.created_at,
                   citizens.name AS citizen_name, departments.name AS department_name
            FROM grievances
            JOIN users AS citizens ON citizens.id = grievances.citizen_id
            JOIN departments ON departments.id = grievances.assigned_department_id
            JOIN department_assignments
              ON department_assignments.id = (
                  SELECT MAX(assignment.id)
                  FROM department_assignments AS assignment
                  WHERE assignment.grievance_id = grievances.id
              )
            WHERE department_assignments.department_id = ?
              AND (department_assignments.assigned_to_user_id IS NULL
                   OR department_assignments.assigned_to_user_id = ?)
            ORDER BY grievances.updated_at DESC
            """,
            (user["department_id"], user["id"]),
        ).fetchall()
    return [dict(row) for row in rows]


@officer_router.get("/grievances/{grievance_id}")
def officer_get_grievance(grievance_id: int, user=Depends(get_current_user)):
    _require_role(user, "officer")
    with get_connection() as connection:
        _require_officer_assignment(connection, grievance_id, user)
        grievance = connection.execute(
            """
            SELECT grievances.*, citizens.name AS citizen_name,
                   departments.name AS department_name
            FROM grievances
            JOIN users AS citizens ON citizens.id = grievances.citizen_id
            LEFT JOIN departments ON departments.id = grievances.assigned_department_id
            WHERE grievances.id = ?
            """,
            (grievance_id,),
        ).fetchone()
        history = connection.execute(
            """
            SELECT grievance_history.new_status, grievance_history.remark,
                   grievance_history.created_at, users.name AS changed_by
            FROM grievance_history
            JOIN users ON users.id = grievance_history.changed_by_user_id
            WHERE grievance_history.grievance_id = ?
            ORDER BY grievance_history.created_at, grievance_history.id
            """,
            (grievance_id,),
        ).fetchall()
        attachments = connection.execute(
            """
            SELECT id, original_filename, content_type
            FROM attachments WHERE grievance_id = ? ORDER BY id
            """,
            (grievance_id,),
        ).fetchall()
    return {
        **dict(grievance),
        "history": [dict(row) for row in history],
        "attachments": [dict(row) for row in attachments],
    }


@officer_router.get("/grievances/{grievance_id}/attachments/{attachment_id}")
def officer_download_attachment(
    grievance_id: int,
    attachment_id: int,
    user=Depends(get_current_user),
):
    _require_role(user, "officer")
    from fastapi.responses import FileResponse

    from app.grievances import UPLOAD_DIRECTORY

    with get_connection() as connection:
        _require_officer_assignment(connection, grievance_id, user)
        attachment = connection.execute(
            """
            SELECT stored_filename, original_filename, content_type
            FROM attachments WHERE grievance_id = ? AND id = ?
            """,
            (grievance_id, attachment_id),
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


@officer_router.post("/grievances/{grievance_id}/update")
def officer_update_grievance(
    grievance_id: int,
    payload: OfficerUpdateRequest,
    user=Depends(get_current_user),
):
    _require_role(user, "officer")
    with get_connection() as connection:
        _require_officer_assignment(connection, grievance_id, user)
        grievance = _require_grievance(connection, grievance_id)
        if grievance["status"] == "Resolved":
            raise HTTPException(
                status_code=409,
                detail="Resolved grievances must be reopened by the CMO before further updates.",
            )
        _status_change(
            connection,
            grievance,
            "In Progress",
            user["id"],
            payload.remark.strip(),
        )
        if grievance["status"] == "In Progress":
            connection.execute(
                "UPDATE grievances SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (grievance_id,),
            )
            connection.execute(
                """
                INSERT INTO grievance_history (
                    grievance_id, previous_status, new_status,
                    changed_by_user_id, remark
                )
                VALUES (?, 'In Progress', 'In Progress', ?, ?)
                """,
                (grievance_id, user["id"], payload.remark.strip()),
            )
    return {"message": "Investigation update saved.", "status": "In Progress"}


@officer_router.post("/grievances/{grievance_id}/reports", status_code=201)
def officer_submit_report(
    grievance_id: int,
    payload: ActionReportRequest,
    user=Depends(get_current_user),
):
    _require_role(user, "officer")
    with get_connection() as connection:
        _require_officer_assignment(connection, grievance_id, user)
        grievance = _require_grievance(connection, grievance_id)
        if grievance["status"] == "Resolved":
            raise HTTPException(
                status_code=409,
                detail="Resolved grievances cannot receive another action report.",
            )
        pending = connection.execute(
            """
            SELECT id FROM department_reports
            WHERE grievance_id = ? AND review_status = 'Pending Review'
            """,
            (grievance_id,),
        ).fetchone()
        if pending is not None:
            raise HTTPException(
                status_code=409,
                detail="An action report is already awaiting CMO review.",
            )
        cursor = connection.execute(
            """
            INSERT INTO department_reports (
                grievance_id, officer_id, action_report, resolution_details
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                grievance_id,
                user["id"],
                payload.action_report.strip(),
                payload.resolution_details.strip(),
            ),
        )
        _status_change(
            connection,
            grievance,
            "In Progress",
            user["id"],
            "Department submitted an action-taken report for CMO review",
        )
    return {
        "id": cursor.lastrowid,
        "review_status": "Pending Review",
        "message": "Action report submitted to the CMO for review.",
    }
