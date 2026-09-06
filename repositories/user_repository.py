"""Repository de la tabla USERS.

Todas las funciones reciben la conexión abierta por el service, de modo
que varias operaciones puedan participar en una misma transacción
(COMMIT/ROLLBACK los decide la capa de servicio).
"""

import oracledb

from models.user import User


def find_auth_by_username(
    conn: oracledb.Connection, username: str
) -> tuple[User, str] | None:
    """Busca un usuario por nombre (con su rol) para autenticación.

    Devuelve ``(User, password_hash)`` o ``None`` si no existe.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.role_id, u.username, u.email, u.password_hash,
                   u.full_name, u.phone, u.is_active, u.last_login_at,
                   u.created_at, u.updated_at, r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE LOWER(u.username) = :username
            """,
            {"username": username.lower()},
        )
        row = cur.fetchone()

    if row is None:
        return None

    user = User(
        id=row[0],
        role_id=row[1],
        username=row[2],
        email=row[3],
        full_name=row[5],
        phone=row[6],
        is_active=bool(row[7]),
        last_login_at=row[8],
        created_at=row[9],
        updated_at=row[10],
        role_name=row[11],
    )
    return user, row[4]


def update_last_login(conn: oracledb.Connection, user_id: int) -> None:
    """Registra el momento del último inicio de sesión. No hace COMMIT."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET last_login_at = SYSTIMESTAMP WHERE id = :id",
            {"id": user_id},
        )


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
