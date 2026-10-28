"""Repository de PERMISSIONS y ROLE_PERMISSIONS."""

import oracledb


def get_role_name(conn: oracledb.Connection, role_id: int) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM roles WHERE id = :role_id", {"role_id": role_id})
        row = cur.fetchone()
        return row[0] if row else None


def get_codes_for_role(conn: oracledb.Connection, role_id: int) -> list[str]:
    """Códigos de permiso asignados a un rol."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.code
            FROM permissions p
            JOIN role_permissions rp ON rp.permission_id = p.id
            WHERE rp.role_id = :role_id
            ORDER BY p.code
            """,
            {"role_id": role_id},
        )
        return [row[0] for row in cur.fetchall()]
