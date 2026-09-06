"""Repository de SURGICAL_PROCEDURES y SURGERY_MEDICATIONS."""

import oracledb

from models.surgery import Surgery, SurgeryMedication

_SURGERY_SELECT = """
    SELECT s.id, s.consultation_id, s.pet_id, s.veterinarian_id,
           s.procedure_name, s.scheduled_at, s.started_at, s.ended_at,
           s.weight_kg, s.preoperative_notes, s.postoperative_notes,
           s.recovery_recommendations, s.status, s.created_at, s.updated_at,
           p.name AS pet_name, v.full_name AS veterinarian_name
    FROM surgical_procedures s
    JOIN pets p ON p.id = s.pet_id
    JOIN users v ON v.id = s.veterinarian_id
"""


def _row_to_surgery(row: tuple) -> Surgery:
    return Surgery(
        id=row[0],
        consultation_id=row[1],
        pet_id=row[2],
        veterinarian_id=row[3],
        procedure_name=row[4],
        scheduled_at=row[5],
        started_at=row[6],
        ended_at=row[7],
        weight_kg=row[8],
        preoperative_notes=row[9],
        postoperative_notes=row[10],
        recovery_recommendations=row[11],
        status=row[12],
        created_at=row[13],
        updated_at=row[14],
        pet_name=row[15],
        veterinarian_name=row[16],
    )


def list_by_consultation(
    conn: oracledb.Connection, consultation_id: int
) -> list[Surgery]:
    with conn.cursor() as cur:
        cur.execute(
            _SURGERY_SELECT
            + " WHERE s.consultation_id = :cid ORDER BY s.created_at",
            {"cid": consultation_id},
        )
        return [_row_to_surgery(row) for row in cur.fetchall()]


def get_by_id(conn: oracledb.Connection, surgery_id: int) -> Surgery | None:
    with conn.cursor() as cur:
        cur.execute(_SURGERY_SELECT + " WHERE s.id = :id", {"id": surgery_id})
        row = cur.fetchone()
    return _row_to_surgery(row) if row else None


def insert_surgery(conn: oracledb.Connection, **fields) -> int:
    """Crea un procedimiento en PLANNED. No hace COMMIT."""
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO surgical_procedures (
                consultation_id, pet_id, veterinarian_id, procedure_name,
                scheduled_at, weight_kg, preoperative_notes, status,
                created_at, updated_at
            ) VALUES (
                :consultation_id, :pet_id, :veterinarian_id, :procedure_name,
                :scheduled_at, :weight_kg, :preoperative_notes, 'PLANNED',
                SYSTIMESTAMP, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {**fields, "new_id": new_id},
        )
        return int(new_id.getvalue()[0])


def update_surgery(conn: oracledb.Connection, surgery_id: int, **fields) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE surgical_procedures
            SET procedure_name = :procedure_name,
                scheduled_at = :scheduled_at,
                weight_kg = :weight_kg,
                preoperative_notes = :preoperative_notes,
                postoperative_notes = :postoperative_notes,
                recovery_recommendations = :recovery_recommendations
            WHERE id = :id
            """,
            {**fields, "id": surgery_id},
        )


def set_status(
    conn: oracledb.Connection, surgery_id: int, status: str
) -> None:
    extra = ""
    if status == "IN_PROGRESS":
        extra = ", started_at = NVL(started_at, SYSTIMESTAMP)"
    elif status == "COMPLETED":
        extra = ", ended_at = SYSTIMESTAMP"
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE surgical_procedures
            SET status = :status {extra}
            WHERE id = :id
            """,  # noqa: S608
            {"status": status, "id": surgery_id},
        )


def list_medications(
    conn: oracledb.Connection, surgery_id: int
) -> list[SurgeryMedication]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sm.id, sm.surgical_procedure_id, sm.medication_id,
                   sm.dose_text, sm.route, sm.notes, m.name
            FROM surgery_medications sm
            JOIN medications m ON m.id = sm.medication_id
            WHERE sm.surgical_procedure_id = :sid
            ORDER BY sm.id
            """,
            {"sid": surgery_id},
        )
        return [
            SurgeryMedication(
                id=row[0],
                surgical_procedure_id=row[1],
                medication_id=row[2],
                dose_text=row[3],
                route=row[4],
                notes=row[5],
                medication_name=row[6],
            )
            for row in cur.fetchall()
        ]


def insert_medication(conn: oracledb.Connection, **fields) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO surgery_medications (
                surgical_procedure_id, medication_id, dose_text, route,
                notes, created_at
            ) VALUES (
                :surgical_procedure_id, :medication_id, :dose_text, :route,
                :notes, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {**fields, "new_id": new_id},
        )
        return int(new_id.getvalue()[0])
