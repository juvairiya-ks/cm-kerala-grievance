import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.database import get_connection, initialize_database
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.sqlite"))
    initialize_database()
    with TestClient(app) as test_client:
        yield test_client


def register_and_login(client, email="citizen@example.test"):
    account = {
        "name": "Test Citizen",
        "email": email,
        "mobile": "9876543210",
        "password": "test-password-123",
    }
    response = client.post("/api/auth/register", json=account)
    assert response.status_code == 201
    response = client.post(
        "/api/auth/login",
        json={"email": account["email"], "password": account["password"]},
    )
    assert response.status_code == 200
    return response.json()["access_token"], response.json()["user"]["id"]


def test_public_information_pages_and_department_directory(client):
    home = client.get("/")
    assert home.status_code == 200
    for label in ("Total grievances", "In progress", "Resolved", "Featured departments"):
        assert label in home.text

    about = client.get("/about")
    assert about.status_code == 200
    for section in ("PURPOSE", "VISION", "MISSION", "OBJECTIVES"):
        assert section in about.text

    for path in ("/how-it-works", "/departments", "/contact", "/faq"):
        response = client.get(path)
        assert response.status_code == 200
        assert "CM Kerala Grievance Portal" in response.text

    departments = client.get("/api/departments")
    assert departments.status_code == 200
    department_ids = [department["id"] for department in departments.json()]
    assert department_ids == sorted(department_ids)
    names = {department["name"] for department in departments.json()}
    assert len(names) >= 15
    assert {
        "Health and Family Welfare",
        "General Education",
        "Higher Education",
        "Food, Civil Supplies and Consumer Affairs",
        "Social Justice",
        "Women and Child Development",
        "Scheduled Castes and Scheduled Tribes Development",
        "Minority Welfare",
        "Backward Classes Development",
        "Non-Resident Keralites Affairs (NORKA)",
        "Public Works Department",
        "Transport",
        "Power",
        "Water Resources",
        "Agriculture, Fisheries and Animal Husbandry",
        "Industries, Commerce and Information Technology",
        "Forests, Wildlife and Environment",
    }.issubset(names)
    assert any(department["name"] in home.text for department in departments.json())
    directory = client.get("/departments")
    assert directory.status_code == 200
    assert all(name in directory.text for name in names)


def test_department_id_migration_preserves_existing_references(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy-departments.sqlite"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    initialize_database()

    with get_connection() as connection:
        department = connection.execute(
            "SELECT id, name FROM departments WHERE name = ?",
            ("Health and Family Welfare",),
        ).fetchone()
        department_id = department["id"]
        connection.execute(
            """
            INSERT INTO users (name, email, mobile, password_hash, role)
            VALUES ('CMO', 'cmo@example.test', '9876543210', 'test-hash', 'admin')
            """
        )
        admin_id = connection.execute(
            "SELECT id FROM users WHERE email = 'cmo@example.test'"
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO users (
                name, email, mobile, password_hash, role, department_id
            ) VALUES ('Officer', 'officer@example.test', '9876543211',
                      'test-hash', 'officer', ?)
            """,
            (department_id,),
        )
        officer_id = connection.execute(
            "SELECT id FROM users WHERE email = 'officer@example.test'"
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO users (name, email, mobile, password_hash, role)
            VALUES ('Citizen', 'case@example.test', '9876543212', 'test-hash', 'citizen')
            """
        )
        citizen_id = connection.execute(
            "SELECT id FROM users WHERE email = 'case@example.test'"
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO grievances (
                reference_number, citizen_id, district, category, subject,
                description, assigned_department_id
            ) VALUES ('GMK-2026-1010ABCD', ?, 'Ernakulam', 'Healthcare',
                      'Sample case', 'A sufficiently detailed fictional grievance description.', ?)
            """,
            (citizen_id, department_id),
        )
        grievance_id = connection.execute(
            "SELECT id FROM grievances WHERE reference_number = 'GMK-2026-1010ABCD'"
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO department_assignments (
                grievance_id, department_id, assigned_by_user_id, assigned_to_user_id
            ) VALUES (?, ?, ?, ?)
            """,
            (grievance_id, department_id, admin_id, officer_id),
        )
        connection.commit()

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("UPDATE departments SET id = id + 1000")
        for table, column in (
            ("users", "department_id"),
            ("grievances", "assigned_department_id"),
            ("department_assignments", "department_id"),
        ):
            connection.execute(
                f"UPDATE {table} SET {column} = {column} + 1000 "
                f"WHERE {column} IS NOT NULL"
            )

    initialize_database()

    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, name FROM departments ORDER BY id"
        ).fetchall()
        assert [row["id"] for row in rows] == list(range(1, len(rows) + 1))
        officer_department = connection.execute(
            """
            SELECT departments.name FROM users
            JOIN departments ON departments.id = users.department_id
            WHERE users.email = 'officer@example.test'
            """
        ).fetchone()["name"]
        assigned_department = connection.execute(
            """
            SELECT departments.name FROM department_assignments
            JOIN departments ON departments.id = department_assignments.department_id
            WHERE department_assignments.grievance_id = ?
            """,
            (grievance_id,),
        ).fetchone()["name"]
        grievance_department = connection.execute(
            """
            SELECT departments.name FROM grievances
            JOIN departments ON departments.id = grievances.assigned_department_id
            WHERE grievances.id = ?
            """,
            (grievance_id,),
        ).fetchone()["name"]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    assert officer_department == "Health and Family Welfare"
    assert assigned_department == "Health and Family Welfare"
    assert grievance_department == "Health and Family Welfare"


def test_contact_enquiry_is_persisted(client):
    response = client.post(
        "/api/contact",
        json={
            "name": "Demo User",
            "email": "User@Example.test",
            "subject": "Question",
            "message": "How does the demonstration work?",
        },
    )
    assert response.status_code == 201
    assert response.json()["message"] == "Your enquiry has been received."

    with get_connection() as connection:
        enquiry = connection.execute(
            "SELECT email FROM contact_enquiries WHERE id = ?",
            (response.json()["id"],),
        ).fetchone()
    assert enquiry["email"] == "user@example.test"


def test_feedback_is_owned_resolved_and_one_time(client):
    token, citizen_id = register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}
    reference = "GMK-2026-1234ABCD"
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO grievances (
                reference_number, citizen_id, district, category, subject,
                description, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'Submitted')
            """,
            (
                reference,
                citizen_id,
                "Ernakulam",
                "Public Services",
                "Sample issue",
                "A sufficiently detailed fictional grievance description.",
            ),
        )
        grievance_id = cursor.lastrowid

    payload = {"rating": 5, "comment": "Resolved in the demonstration."}
    response = client.post(
        f"/api/grievances/{reference}/feedback", json=payload, headers=headers
    )
    assert response.status_code == 409

    with get_connection() as connection:
        connection.execute(
            "UPDATE grievances SET status = 'Resolved' WHERE id = ?",
            (grievance_id,),
        )

    response = client.post(
        f"/api/grievances/{reference}/feedback", json=payload, headers=headers
    )
    assert response.status_code == 201
    repeated = client.post(
        f"/api/grievances/{reference}/feedback", json=payload, headers=headers
    )
    assert repeated.status_code == 409
    tracked = client.get(f"/api/grievances/{reference}", headers=headers)
    assert tracked.status_code == 200
    assert tracked.json()["feedback_submitted"] is True


def test_feedback_rejects_non_owner_and_invalid_rating(client):
    token, citizen_id = register_and_login(client)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO grievances (
                reference_number, citizen_id, district, category, subject,
                description, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'Resolved')
            """,
            (
                "GMK-2026-ABCD1234",
                citizen_id,
                "Kollam",
                "Other",
                "Another issue",
                "A sufficiently detailed fictional grievance description.",
            ),
        )

    outsider, _ = register_and_login(client, "other@example.test")
    response = client.post(
        "/api/grievances/GMK-2026-ABCD1234/feedback",
        json={"rating": 4},
        headers={"Authorization": f"Bearer {outsider}"},
    )
    assert response.status_code == 404

    invalid = client.post(
        "/api/grievances/GMK-2026-ABCD1234/feedback",
        json={"rating": 6},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert invalid.status_code == 422
