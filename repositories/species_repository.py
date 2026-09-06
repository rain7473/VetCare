"""Repository de los catálogos SPECIES y BREEDS."""

import oracledb


def list_species(conn: oracledb.Connection, only_active: bool = True) -> list[tuple[int, str]]:
    sql = "SELECT id, name FROM species"
    if only_active:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY name"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [(row[0], row[1]) for row in cur.fetchall()]


def list_breeds(
    conn: oracledb.Connection, species_id: int, only_active: bool = True
) -> list[tuple[int, str]]:
    sql = "SELECT id, name FROM breeds WHERE species_id = :species_id"
    if only_active:
        sql += " AND is_active = 1"
    sql += " ORDER BY name"
    with conn.cursor() as cur:
        cur.execute(sql, {"species_id": species_id})
        return [(row[0], row[1]) for row in cur.fetchall()]


def find_breed_by_name(
    conn: oracledb.Connection, species_id: int, name: str
) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM breeds
            WHERE species_id = :species_id AND LOWER(name) = :name
            """,
            {"species_id": species_id, "name": name.lower()},
        )
        row = cur.fetchone()
        return row[0] if row else None


def insert_breed(conn: oracledb.Connection, species_id: int, name: str) -> int:
    """Agrega una raza al catálogo. No hace COMMIT."""
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO breeds (species_id, name, is_active)
            VALUES (:species_id, :name, 1)
            RETURNING id INTO :new_id
            """,
            {"species_id": species_id, "name": name, "new_id": new_id},
        )
        return int(new_id.getvalue()[0])
