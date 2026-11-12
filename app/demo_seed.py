import os

from app.auth import hash_password
from app.database import get_connection


def seed_demo_accounts() -> None:
    password = os.getenv("DEMO_PASSWORD")
    if not password or len(password) < 8:
        print("DEMO_PASSWORD not set (min 8 chars); demo accounts skipped.")
        return

    with get_connection() as connection:
        department = connection.execute(
            "SELECT id FROM departments ORDER BY id LIMIT 1"
        ).fetchone()
        department_id = department["id"] if department else None
        pw_hash = hash_password(password)

        accounts = [
            ("Demo CMO Admin", "cmo.demo@example.com", "9000000001", "admin", None),
            ("Demo Officer", "officer.demo@example.com", "9000000002", "officer", department_id),
            ("Demo Citizen", "citizen.demo@example.com", "9000000003", "citizen", None),
        ]
        for name, email, mobile, role, dept in accounts:
            connection.execute(
                """
                INSERT OR IGNORE INTO users
                (name, email, mobile, password_hash, role, department_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, email, mobile, pw_hash, role, dept),
            )
    print("Demo accounts ensured.")