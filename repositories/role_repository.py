"""Repository de la tabla ROLES."""

import oracledb


def list_roles(conn: oracledb.Connection) -> list[tuple[int, str]]:
    """Todos los roles como (id, nombre)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM roles ORDER BY id")
        return [(row[0], row[1]) for row in cur.fetchall()]


def get_role_id_by_name(conn: oracledb.Connection, name: str) -> int | None:
    """Devuelve el ID del rol con el nombre dado (ADMIN, RECEPTION...)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM roles WHERE name = :name",
            {"name": name},
        )
        row = cur.fetchone()
        return row[0] if row else None
