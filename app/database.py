import os
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_database_path() -> Path:
    configured_path = os.getenv("DATABASE_PATH", "grievances.db")
    path = Path(configured_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def get_connection() -> sqlite3.Connection:
    path = get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _normalize_department_ids(connection: sqlite3.Connection) -> None:
    departments = connection.execute(
        "SELECT id FROM departments ORDER BY id"
    ).fetchall()
    current_ids = [row["id"] for row in departments]
    target_ids = list(range(1, len(current_ids) + 1))

    if current_ids != target_ids:
        connection.execute("PRAGMA defer_foreign_keys = ON")
        temporary_ids = {
            current_id: max(current_ids, default=0) + len(current_ids) + index + 1
            for index, current_id in enumerate(current_ids)
        }
        department_references = (
            ("users", "department_id"),
            ("grievances", "assigned_department_id"),
            ("department_assignments", "department_id"),
        )

        for table, column in department_references:
            for current_id, temporary_id in temporary_ids.items():
                connection.execute(
                    f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                    (temporary_id, current_id),
                )
        for current_id, temporary_id in temporary_ids.items():
            connection.execute(
                "UPDATE departments SET id = ? WHERE id = ?",
                (temporary_id, current_id),
            )

        for index, temporary_id in enumerate(temporary_ids.values(), start=1):
            connection.execute(
                "UPDATE departments SET id = ? WHERE id = ?",
                (index, temporary_id),
            )
            for table, column in department_references:
                connection.execute(
                    f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                    (index, temporary_id),
                )

    connection.execute("DELETE FROM sqlite_sequence WHERE name = 'departments'")
    if departments:
        connection.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES ('departments', ?)",
            (len(departments),),
        )


def initialize_database() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                mobile TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('citizen', 'admin', 'officer')),
                department_id INTEGER REFERENCES departments(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS auth_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS grievances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference_number TEXT NOT NULL UNIQUE,
                citizen_id INTEGER NOT NULL REFERENCES users(id),
                district TEXT NOT NULL,
                category TEXT NOT NULL,
                subject TEXT NOT NULL,
                description TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'Medium'
                    CHECK (priority IN ('Low', 'Medium', 'High')),
                status TEXT NOT NULL DEFAULT 'Submitted'
                    CHECK (status IN (
                        'Submitted', 'Under Review', 'In Progress',
                        'Resolved', 'Reopened'
                    )),
                assigned_department_id INTEGER REFERENCES departments(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS grievance_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grievance_id INTEGER NOT NULL REFERENCES grievances(id),
                previous_status TEXT,
                new_status TEXT NOT NULL,
                changed_by_user_id INTEGER NOT NULL REFERENCES users(id),
                remark TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS department_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grievance_id INTEGER NOT NULL REFERENCES grievances(id),
                department_id INTEGER NOT NULL REFERENCES departments(id),
                assigned_by_user_id INTEGER NOT NULL REFERENCES users(id),
                assigned_to_user_id INTEGER REFERENCES users(id),
                remark TEXT,
                assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS grievance_internal_remarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grievance_id INTEGER NOT NULL REFERENCES grievances(id),
                user_id INTEGER NOT NULL REFERENCES users(id),
                remark TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS grievance_escalations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grievance_id INTEGER NOT NULL REFERENCES grievances(id),
                escalated_by_user_id INTEGER NOT NULL REFERENCES users(id),
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS department_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grievance_id INTEGER NOT NULL REFERENCES grievances(id),
                officer_id INTEGER NOT NULL REFERENCES users(id),
                action_report TEXT NOT NULL,
                resolution_details TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'Pending Review'
                    CHECK (review_status IN ('Pending Review', 'Accepted', 'Returned')),
                reviewed_by_user_id INTEGER REFERENCES users(id),
                review_remark TEXT,
                submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS ai_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                grievance_id INTEGER REFERENCES grievances(id),
                subject TEXT NOT NULL,
                subject_hash TEXT NOT NULL,
                description_hash TEXT NOT NULL,
                suggested_department TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL CHECK (priority IN ('Low', 'Medium', 'High')),
                summary TEXT NOT NULL,
                duplicate_possible INTEGER NOT NULL DEFAULT 0
                    CHECK (duplicate_possible IN (0, 1)),
                source TEXT NOT NULL CHECK (source IN ('llm_api', 'fallback')),
                model TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grievance_id INTEGER NOT NULL REFERENCES grievances(id),
                uploaded_by_user_id INTEGER NOT NULL REFERENCES users(id),
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL UNIQUE,
                content_type TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS citizen_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grievance_id INTEGER NOT NULL UNIQUE REFERENCES grievances(id),
                citizen_id INTEGER NOT NULL REFERENCES users(id),
                rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                comment TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS contact_enquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        department_seeds = [
                (
                    "Public Works Department",
                    "Public roads, bridges, and government buildings.",
                ),
                (
                    "Health and Family Welfare",
                    "Government hospitals, public health initiatives, medical education, and food safety programs.",
                ),
                (
                    "General Education",
                    "School education through Class 12 and related public education services.",
                ),
                (
                    "Higher Education",
                    "Universities, colleges, technical education, and higher-education services.",
                ),
                (
                    "Food, Civil Supplies and Consumer Affairs",
                    "Public Distribution System and ration cards, food security, and consumer protection.",
                ),
                (
                    "Social Justice",
                    "Social welfare services, inclusion programs, and support for eligible communities.",
                ),
                (
                    "Women and Child Development",
                    "Services and welfare programs for women, children, and families.",
                ),
                (
                    "Scheduled Castes and Scheduled Tribes Development",
                    "Development, welfare, and support services for Scheduled Caste and Scheduled Tribe communities.",
                ),
                (
                    "Minority Welfare",
                    "Welfare and development programs for minority communities.",
                ),
                (
                    "Backward Classes Development",
                    "Welfare and development programs for backward classes.",
                ),
                (
                    "Non-Resident Keralites Affairs (NORKA)",
                    "Welfare, grievance support, and rehabilitation services for Keralites working abroad.",
                ),
                (
                    "Local Self Government",
                    "Local civic services and municipal administration.",
                ),
                (
                    "Water Resources",
                    "Irrigation projects, water management, and drinking-water infrastructure.",
                ),
                (
                    "Transport",
                    "Road and water transport administration, vehicle registration, and licensing services.",
                ),
                (
                    "Power",
                    "Electricity generation, transmission, distribution, and public power services.",
                ),
                (
                    "Agriculture, Fisheries and Animal Husbandry",
                    "Services supporting farmers, fisheries, animal husbandry, dairy development, and coastal communities.",
                ),
                (
                    "Industries, Commerce and Information Technology",
                    "Industrial growth, commerce, MSMEs, startups, and information technology initiatives.",
                ),
                (
                    "Forests, Wildlife and Environment",
                    "Forest conservation, wildlife protection, and environmental programs.",
                ),
            ]
        existing_names = {
            row["name"]
            for row in connection.execute("SELECT name FROM departments").fetchall()
        }
        connection.executemany(
            "INSERT INTO departments (name, description) VALUES (?, ?)",
            [department for department in department_seeds if department[0] not in existing_names],
        )
        _normalize_department_ids(connection)
