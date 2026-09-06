"""Repository de la tabla USERS.

Todas las funciones reciben la conexión abierta por el service, de modo
que varias operaciones puedan participar en una misma transacción
(COMMIT/ROLLBACK los decide la capa de servicio).
"""

import oracledb

from models.user import User

_USER_SELECT = """
    SELECT u.id, u.role_id, u.username, u.email, u.full_name, u.phone,
           u.is_active, u.last_login_at, u.created_at, u.updated_at,
           r.name AS role_name
    FROM users u
    JOIN roles r ON r.id = u.role_id
"""


def _row_to_user(row: tuple) -> User:
    return User(
        id=row[0],
        role_id=row[1],
        username=row[2],
        email=row[3],
        full_name=row[4],
        phone=row[5],
        is_active=bool(row[6]),
        last_login_at=row[7],
        created_at=row[8],
        updated_at=row[9],
        role_name=row[10],
    )


def find_auth_by_username(
    conn: oracledb.Connection, username: str
) -> tuple[User, str] | None:
    """Busca un usuario por nombre (con su rol) para autenticación.

    Devuelve ``(User, password_hash)`` o ``None`` si no existe.
    """
    with conn.cursor() as cur:
        cur.execute(
            _USER_SELECT + " WHERE LOWER(u.username) = :username",
            {"username": username.lower()},
        )
        row = cur.fetchone()
        if row is None:
            return None
        cur.execute(
            "SELECT password_hash FROM users WHERE id = :id", {"id": row[0]}
        )
        password_hash = cur.fetchone()[0]
    return _row_to_user(row), password_hash


def get_by_id(conn: oracledb.Connection, user_id: int) -> User | None:
    with conn.cursor() as cur:
        cur.execute(_USER_SELECT + " WHERE u.id = :id", {"id": user_id})
        row = cur.fetchone()
    return _row_to_user(row) if row else None


def list_users(conn: oracledb.Connection) -> list[User]:
    """Todos los usuarios con su rol, ordenados por nombre."""
    with conn.cursor() as cur:
        cur.execute(_USER_SELECT + " ORDER BY u.full_name")
        return [_row_to_user(row) for row in cur.fetchall()]


def update_last_login(conn: oracledb.Connection, user_id: int) -> None:
    """Registra el momento del último inicio de sesión. No hace COMMIT."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET last_login_at = SYSTIMESTAMP WHERE id = :id",
            {"id": user_id},
        )


def list_active_by_role(conn: oracledb.Connection, role_name: str) -> list[User]:
    """Usuarios activos de un rol dado (p. ej. veterinarios)."""
    with conn.cursor() as cur:
        cur.execute(
            _USER_SELECT
            + " WHERE r.name = :role_name AND u.is_active = 1 ORDER BY u.full_name",
            {"role_name": role_name},
        )
        return [_row_to_user(row) for row in cur.fetchall()]


def count_users(conn: oracledb.Connection) -> int:
    """Total de usuarios registrados (activos e inactivos)."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]


def count_active_admins(
    conn: oracledb.Connection, exclude_user_id: int | None = None
) -> int:
    """Cantidad de administradores activos (opcionalmente excluyendo uno)."""
    sql = """
        SELECT COUNT(*)
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE r.name = 'ADMIN' AND u.is_active = 1
    """
    params: dict = {}
    if exclude_user_id is not None:
        sql += " AND u.id != :exclude_id"
        params["exclude_id"] = exclude_user_id
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def username_exists(conn: oracledb.Connection, username: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM users WHERE LOWER(username) = :username",
            {"username": username.lower()},
        )
        return cur.fetchone()[0] > 0


def email_exists(
    conn: oracledb.Connection, email: str, exclude_user_id: int | None = None
) -> bool:
    sql = "SELECT COUNT(*) FROM users WHERE LOWER(email) = :email"
    params: dict = {"email": email.lower()}
    if exclude_user_id is not None:
        sql += " AND id != :exclude_id"
        params["exclude_id"] = exclude_user_id
    with conn.cursor() as cur:
        cur.execute(sql, params)
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


def update_user(
    conn: oracledb.Connection,
    user_id: int,
    *,
    role_id: int,
    email: str | None,
    full_name: str,
    phone: str | None,
    is_active: bool,
) -> None:
    """Actualiza los datos editables de un usuario. No hace COMMIT."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE users
            SET role_id = :role_id,
                email = :email,
                full_name = :full_name,
                phone = :phone,
                is_active = :is_active
            WHERE id = :id
            """,
            {
                "role_id": role_id,
                "email": email,
                "full_name": full_name,
                "phone": phone,
                "is_active": 1 if is_active else 0,
                "id": user_id,
            },
        )


def update_password(
    conn: oracledb.Connection, user_id: int, password_hash: str
) -> None:
    """Reemplaza el hash de contraseña. No hace COMMIT."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET password_hash = :hash WHERE id = :id",
            {"hash": password_hash, "id": user_id},
        )


def set_active(conn: oracledb.Connection, user_id: int, active: bool) -> None:
    """Activa o desactiva un usuario. No hace COMMIT."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET is_active = :active WHERE id = :id",
            {"active": 1 if active else 0, "id": user_id},
        )
