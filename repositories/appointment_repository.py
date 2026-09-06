"""Repository de la tabla APPOINTMENTS."""

from datetime import date, datetime

import oracledb

from models.appointment import Appointment

_APPT_SELECT = """
    SELECT a.id, a.pet_id, a.veterinarian_id, a.created_by, a.appointment_at,
           a.reason, a.status, a.notes, a.created_at, a.updated_at,
           p.name AS pet_name,
           o.first_name || ' ' || o.last_name AS owner_name,
           v.full_name AS veterinarian_name
    FROM appointments a
    JOIN pets p ON p.id = a.pet_id
    JOIN owners o ON o.id = p.owner_id
    LEFT JOIN users v ON v.id = a.veterinarian_id
"""


def _row_to_appointment(row: tuple) -> Appointment:
    return Appointment(
        id=row[0],
        pet_id=row[1],
        veterinarian_id=row[2],
        created_by=row[3],
        appointment_at=row[4],
        reason=row[5],
        status=row[6],
        notes=row[7],
        created_at=row[8],
        updated_at=row[9],
        pet_name=row[10],
        owner_name=row[11],
        veterinarian_name=row[12],
    )


def list_appointments(
    conn: oracledb.Connection, day: date | None = None
) -> list[Appointment]:
    """Citas de un día concreto, o todas si ``day`` es None."""
    sql = _APPT_SELECT
    params: dict = {}
    if day is not None:
        sql += " WHERE TRUNC(a.appointment_at) = TRUNC(:day)"
        params["day"] = datetime(day.year, day.month, day.day)
    sql += " ORDER BY a.appointment_at"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_appointment(row) for row in cur.fetchall()]


def get_by_id(conn: oracledb.Connection, appointment_id: int) -> Appointment | None:
    with conn.cursor() as cur:
        cur.execute(_APPT_SELECT + " WHERE a.id = :id", {"id": appointment_id})
        row = cur.fetchone()
    return _row_to_appointment(row) if row else None


def insert_appointment(
    conn: oracledb.Connection,
    *,
    pet_id: int,
    veterinarian_id: int | None,
    created_by: int,
    appointment_at: datetime,
    reason: str,
    notes: str | None,
) -> int:
    """Inserta una cita en estado SCHEDULED. No hace COMMIT."""
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO appointments (
                pet_id, veterinarian_id, created_by, appointment_at,
                reason, status, notes, created_at, updated_at
            ) VALUES (
                :pet_id, :veterinarian_id, :created_by, :appointment_at,
                :reason, 'SCHEDULED', :notes, SYSTIMESTAMP, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "pet_id": pet_id,
                "veterinarian_id": veterinarian_id,
                "created_by": created_by,
                "appointment_at": appointment_at,
                "reason": reason,
                "notes": notes,
                "new_id": new_id,
            },
        )
        return int(new_id.getvalue()[0])


def update_appointment(
    conn: oracledb.Connection,
    appointment_id: int,
    *,
    pet_id: int,
    veterinarian_id: int | None,
    appointment_at: datetime,
    reason: str,
    notes: str | None,
) -> None:
    """Actualiza los datos editables de una cita. No hace COMMIT."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE appointments
            SET pet_id = :pet_id,
                veterinarian_id = :veterinarian_id,
                appointment_at = :appointment_at,
                reason = :reason,
                notes = :notes
            WHERE id = :id
            """,
            {
                "pet_id": pet_id,
                "veterinarian_id": veterinarian_id,
                "appointment_at": appointment_at,
                "reason": reason,
                "notes": notes,
                "id": appointment_id,
            },
        )


def set_status(conn: oracledb.Connection, appointment_id: int, status: str) -> None:
    """Cambia el estado de la cita. No hace COMMIT."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE appointments SET status = :status WHERE id = :id",
            {"status": status, "id": appointment_id},
        )
