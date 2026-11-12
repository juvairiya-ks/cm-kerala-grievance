from app.database import get_connection, initialize_database
from app.demo_seed import seed_demo_accounts


def test_seed_assigns_department_to_existing_demo_officer(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.sqlite"))
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    initialize_database()

    with get_connection() as connection:
        department_id = connection.execute(
            "SELECT id FROM departments ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO users (name, email, mobile, password_hash, role)
            VALUES ('Demo Officer', 'officer.demo@example.com', '9000000002',
                    'existing-hash', 'officer')
            """
        )

    seed_demo_accounts()

    with get_connection() as connection:
        officer_department_id = connection.execute(
            "SELECT department_id FROM users WHERE email = ?",
            ("officer.demo@example.com",),
        ).fetchone()["department_id"]

    assert officer_department_id == department_id
