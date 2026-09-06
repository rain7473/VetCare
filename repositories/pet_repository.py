"""Repository de la tabla PETS."""

import oracledb

from models.pet import Pet

_PET_SELECT = """
    SELECT p.id, p.owner_id, p.species_id, p.breed_id, p.name, p.sex,
           p.birth_date, p.approximate_age_months, p.color,
           p.distinctive_features, p.microchip_number, p.photo_url,
           p.blood_type, p.allergies, p.chronic_conditions, p.status,
           p.created_at, p.updated_at,
           o.first_name || ' ' || o.last_name AS owner_name,
           s.name AS species_name,
           b.name AS breed_name
    FROM pets p
    JOIN owners o ON o.id = p.owner_id
    JOIN species s ON s.id = p.species_id
    LEFT JOIN breeds b ON b.id = p.breed_id
"""


def _row_to_pet(row: tuple) -> Pet:
    return Pet(
        id=row[0],
        owner_id=row[1],
        species_id=row[2],
        breed_id=row[3],
        name=row[4],
        sex=row[5],
        birth_date=row[6],
        approximate_age_months=row[7],
        color=row[8],
        distinctive_features=row[9],
        microchip_number=row[10],
        photo_url=row[11],
        blood_type=row[12],
        allergies=row[13],
        chronic_conditions=row[14],
        status=row[15],
        created_at=row[16],
        updated_at=row[17],
        owner_name=row[18],
        species_name=row[19],
        breed_name=row[20],
    )


def list_pets(conn: oracledb.Connection) -> list[Pet]:
    """Todas las mascotas con propietario, especie y raza."""
    with conn.cursor() as cur:
        cur.execute(_PET_SELECT + " ORDER BY p.name")
        return [_row_to_pet(row) for row in cur.fetchall()]


def get_by_id(conn: oracledb.Connection, pet_id: int) -> Pet | None:
    with conn.cursor() as cur:
        cur.execute(_PET_SELECT + " WHERE p.id = :id", {"id": pet_id})
        row = cur.fetchone()
    return _row_to_pet(row) if row else None


def microchip_exists(
    conn: oracledb.Connection, microchip: str, exclude_pet_id: int | None = None
) -> bool:
    sql = "SELECT COUNT(*) FROM pets WHERE LOWER(microchip_number) = :chip"
    params: dict = {"chip": microchip.lower()}
    if exclude_pet_id is not None:
        sql += " AND id != :exclude_id"
        params["exclude_id"] = exclude_pet_id
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0] > 0


def insert_pet(conn: oracledb.Connection, **fields) -> int:
    """Inserta una mascota y devuelve su ID. No hace COMMIT.

    ``fields`` debe contener: owner_id, species_id, breed_id, name, sex,
    birth_date, approximate_age_months, color, distinctive_features,
    microchip_number, photo_url, blood_type, allergies, chronic_conditions.
    """
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO pets (
                owner_id, species_id, breed_id, name, sex, birth_date,
                approximate_age_months, color, distinctive_features,
                microchip_number, photo_url, blood_type, allergies,
                chronic_conditions, status, created_at, updated_at
            ) VALUES (
                :owner_id, :species_id, :breed_id, :name, :sex, :birth_date,
                :approximate_age_months, :color, :distinctive_features,
                :microchip_number, :photo_url, :blood_type, :allergies,
                :chronic_conditions, 'ACTIVE', SYSTIMESTAMP, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {**fields, "new_id": new_id},
        )
        return int(new_id.getvalue()[0])


def update_pet(conn: oracledb.Connection, pet_id: int, **fields) -> None:
    """Actualiza una mascota (mismos campos que insert_pet + status)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE pets
            SET owner_id = :owner_id,
                species_id = :species_id,
                breed_id = :breed_id,
                name = :name,
                sex = :sex,
                birth_date = :birth_date,
                approximate_age_months = :approximate_age_months,
                color = :color,
                distinctive_features = :distinctive_features,
                microchip_number = :microchip_number,
                photo_url = :photo_url,
                blood_type = :blood_type,
                allergies = :allergies,
                chronic_conditions = :chronic_conditions,
                status = :status
            WHERE id = :pet_id
            """,
            {**fields, "pet_id": pet_id},
        )


def set_status(conn: oracledb.Connection, pet_id: int, status: str) -> None:
    """Cambia el estado (ACTIVE/DECEASED/INACTIVE). No hace COMMIT."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE pets SET status = :status WHERE id = :id",
            {"status": status, "id": pet_id},
        )
