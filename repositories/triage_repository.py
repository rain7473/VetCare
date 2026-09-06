"""Repository de la tabla TRIAGES (solo lectura e inserción: inmutable)."""

from datetime import date, datetime

import oracledb

from models.triage import Triage

_TRIAGE_SELECT = """
    SELECT t.id, t.pet_id, t.appointment_id, t.recorded_by, t.reason,
           t.consciousness_status, t.respiratory_distress, t.active_bleeding,
           t.can_walk, t.seizures, t.pain_level, t.temperature_c,
           t.heart_rate_bpm, t.respiratory_rate_rpm, t.oxygen_saturation_pct,
           t.priority_level, t.priority_reason, t.observations, t.created_at,
           p.name AS pet_name,
           o.first_name || ' ' || o.last_name AS owner_name,
           u.full_name AS recorded_by_name
    FROM triages t
    JOIN pets p ON p.id = t.pet_id
    JOIN owners o ON o.id = p.owner_id
    JOIN users u ON u.id = t.recorded_by
"""


def _row_to_triage(row: tuple) -> Triage:
    return Triage(
        id=row[0],
        pet_id=row[1],
        appointment_id=row[2],
        recorded_by=row[3],
        reason=row[4],
        consciousness_status=row[5],
        respiratory_distress=bool(row[6]),
        active_bleeding=bool(row[7]),
        can_walk=None if row[8] is None else bool(row[8]),
        seizures=bool(row[9]),
        pain_level=row[10],
        temperature_c=row[11],
        heart_rate_bpm=row[12],
        respiratory_rate_rpm=row[13],
        oxygen_saturation_pct=row[14],
        priority_level=row[15],
        priority_reason=row[16],
        observations=row[17],
        created_at=row[18],
        pet_name=row[19],
        owner_name=row[20],
        recorded_by_name=row[21],
    )


def list_triages(conn: oracledb.Connection, day: date | None = None) -> list[Triage]:
    """Triajes de un día (o todos), ordenados por prioridad y hora."""
    sql = _TRIAGE_SELECT
    params: dict = {}
    if day is not None:
        sql += " WHERE TRUNC(t.created_at) = TRUNC(:day)"
        params["day"] = datetime(day.year, day.month, day.day)
    sql += " ORDER BY t.priority_level, t.created_at"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_triage(row) for row in cur.fetchall()]


def get_by_id(conn: oracledb.Connection, triage_id: int) -> Triage | None:
    with conn.cursor() as cur:
        cur.execute(_TRIAGE_SELECT + " WHERE t.id = :id", {"id": triage_id})
        row = cur.fetchone()
    return _row_to_triage(row) if row else None


def insert_triage(conn: oracledb.Connection, **fields) -> int:
    """Inserta un triaje. No hace COMMIT.

    ``fields``: pet_id, appointment_id, recorded_by, reason,
    consciousness_status, respiratory_distress, active_bleeding, can_walk,
    seizures, pain_level, temperature_c, heart_rate_bpm,
    respiratory_rate_rpm, oxygen_saturation_pct, priority_level,
    priority_reason, observations.
    """
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO triages (
                pet_id, appointment_id, recorded_by, reason,
                consciousness_status, respiratory_distress, active_bleeding,
                can_walk, seizures, pain_level, temperature_c,
                heart_rate_bpm, respiratory_rate_rpm, oxygen_saturation_pct,
                priority_level, priority_reason, observations, created_at
            ) VALUES (
                :pet_id, :appointment_id, :recorded_by, :reason,
                :consciousness_status, :respiratory_distress, :active_bleeding,
                :can_walk, :seizures, :pain_level, :temperature_c,
                :heart_rate_bpm, :respiratory_rate_rpm, :oxygen_saturation_pct,
                :priority_level, :priority_reason, :observations, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {**fields, "new_id": new_id},
        )
        return int(new_id.getvalue()[0])
