"""Repository de la tabla USERS.

Todas las funciones reciben la conexión abierta por el service, de modo
que varias operaciones puedan participar en una misma transacción
(COMMIT/ROLLBACK los decide la capa de servicio).
"""

import oracledb


def count_users(conn: oracledb.Connection) -> int:
    """Total de usuarios registrados (activos e inactivos)."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]


def username_exists(conn: oracledb.Connection, username: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM users WHERE LOWER(username) = :username",
            {"username": username.lower()},
        )
        return cur.fetchone()[0] > 0


def email_exists(conn: oracledb.Connection, email: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM users WHERE LOWER(email) = :email",
            {"email": email.lower()},
        )
        return cur.fetchone()[0] > 0


def insert_user(
    conn: oracledb.Connection,
    *,
    role_id: int,
    username: str,
    email: str | None,
    password_hash: str,
    full_name: str,
    phone: str | None,
    is_active: bool = True,
) -> int:
    """Inserta un usuario y devuelve su ID generado. No hace COMMIT."""
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO users (
                role_id, username, email, password_hash,
                full_name, phone, is_active, created_at, updated_at
            ) VALUES (
                :role_id, :username, :email, :password_hash,
                :full_name, :phone, :is_active, SYSTIMESTAMP, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "role_id": role_id,
                "username": username,
                "email": email,
                "password_hash": password_hash,
                "full_name": full_name,
                "phone": phone,
                "is_active": 1 if is_active else 0,
                "new_id": new_id,
            },
        )
        return int(new_id.getvalue()[0])
