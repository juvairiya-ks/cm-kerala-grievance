import getpass
import sqlite3

from app.auth import hash_password
from app.database import get_connection, initialize_database


def main() -> None:
    initialize_database()
    role = input("Account type (admin/officer): ").strip().lower()
    if role not in {"admin", "officer"}:
        raise SystemExit("Account type must be admin or officer.")

    name = input("Full name: ").strip()
    email = input("Email: ").strip().lower()
    mobile = input("Mobile number: ").strip()
    password = getpass.getpass("Password (minimum 8 characters): ")
    if len(password) < 8:
        raise SystemExit("Password must contain at least 8 characters.")
    if getpass.getpass("Confirm password: ") != password:
        raise SystemExit("Passwords do not match.")

    department_id = None
    with get_connection() as connection:
        if role == "officer":
            departments = connection.execute(
                "SELECT id, name FROM departments ORDER BY id"
            ).fetchall()
            for department in departments:
                print(f"Department ID {department['id']}: {department['name']}")
            try:
                department_id = int(input("Department ID: ").strip())
            except ValueError as exc:
                raise SystemExit("Enter a valid department ID.") from exc
            if not any(row["id"] == department_id for row in departments):
                raise SystemExit("Department not found.")

        try:
            connection.execute(
                """
                INSERT INTO users (name, email, mobile, password_hash, role, department_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, email, mobile, hash_password(password), role, department_id),
            )
        except sqlite3.IntegrityError as exc:
            if "users.email" in str(exc):
                raise SystemExit("An account already uses that email address.") from exc
            raise

    print(f"{role.title()} account created for {email}.")


if __name__ == "__main__":
    main()
