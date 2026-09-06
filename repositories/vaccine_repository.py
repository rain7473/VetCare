"""Repository de VACCINES y PET_VACCINATIONS."""

from datetime import date

import oracledb

from models.vaccine import PetVaccination, Vaccine

_APP_SELECT = """
    SELECT a.id, a.pet_id, a.vaccine_id, a.consultation_id, a.inventory_lot_id,
           a.applied_by, a.applied_at, a.lot_number, a.expiry_date,
           a.next_due_date, a.notes, a.created_at,
           p.name AS pet_name,
           o.first_name || ' ' || o.last_name AS owner_name,
           v.name AS vaccine_name,
           u.full_name AS applied_by_name
    FROM pet_vaccinations a
    JOIN pets p ON p.id = a.pet_id
    JOIN owners o ON o.id = p.owner_id
    JOIN vaccines v ON v.id = a.vaccine_id
    JOIN users u ON u.id = a.applied_by
"""


def list_vaccines(conn: oracledb.Connection, only_active: bool = True) -> list[Vaccine]:
    sql = """
        SELECT id, product_id, name, manufacturer, description, is_active, created_at
        FROM vaccines
    """
    if only_active:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY name"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [_row_to_vaccine(row) for row in cur.fetchall()]


def insert_vaccine(
    conn: oracledb.Connection,
    *,
    name: str,
    manufacturer: str | None,
    description: str | None,
) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO vaccines (name, manufacturer, description, is_active, created_at)
            VALUES (:name, :manufacturer, :description, 1, SYSTIMESTAMP)
            RETURNING id INTO :new_id
            """,
            {
                "name": name,
                "manufacturer": manufacturer,
                "description": description,
                "new_id": new_id,
            },
        )
        return int(new_id.getvalue()[0])


def list_applications(
    conn: oracledb.Connection, pet_id: int | None = None
) -> list[PetVaccination]:
    sql = _APP_SELECT
    params: dict = {}
    if pet_id is not None:
        sql += " WHERE a.pet_id = :pet_id"
        params["pet_id"] = pet_id
    sql += " ORDER BY a.applied_at DESC"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_application(row) for row in cur.fetchall()]


def list_due_soon(
    conn: oracledb.Connection, until: date
) -> list[PetVaccination]:
    """Aplicaciones con próxima fecha hasta ``until`` (alertas)."""
    with conn.cursor() as cur:
        cur.execute(
            _APP_SELECT + " WHERE a.next_due_date IS NOT NULL AND a.next_due_date <= :until"
            " ORDER BY a.next_due_date",
            {"until": until},
        )
        return [_row_to_application(row) for row in cur.fetchall()]


def insert_application(conn: oracledb.Connection, **fields) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO pet_vaccinations (
                pet_id, vaccine_id, consultation_id, applied_by, applied_at,
                lot_number, expiry_date, next_due_date, notes, created_at
            ) VALUES (
                :pet_id, :vaccine_id, :consultation_id, :applied_by, :applied_at,
                :lot_number, :expiry_date, :next_due_date, :notes, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {**fields, "new_id": new_id},
        )
        return int(new_id.getvalue()[0])


def _row_to_vaccine(row: tuple) -> Vaccine:
    return Vaccine(
        id=row[0],
        product_id=row[1],
        name=row[2],
        manufacturer=row[3],
        description=row[4],
        is_active=bool(row[5]),
        created_at=row[6],
    )


def _row_to_application(row: tuple) -> PetVaccination:
    return PetVaccination(
        id=row[0],
        pet_id=row[1],
        vaccine_id=row[2],
        consultation_id=row[3],
        inventory_lot_id=row[4],
        applied_by=row[5],
        applied_at=row[6],
        lot_number=row[7],
        expiry_date=row[8],
        next_due_date=row[9],
        notes=row[10],
        created_at=row[11],
        pet_name=row[12],
        owner_name=row[13],
        vaccine_name=row[14],
        applied_by_name=row[15],
    )
