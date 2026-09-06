"""Repository de la tabla ROLES."""

import oracledb


def get_role_id_by_name(conn: oracledb.Connection, name: str) -> int | None:
    """Devuelve el ID del rol con el nombre dado (ADMIN, RECEPTION...)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM roles WHERE name = :name",
            {"name": name},
        )
        row = cur.fetchone()
        return row[0] if row else None
