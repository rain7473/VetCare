"""Repository del historial clínico: CONSULTATIONS, CONSULTATION_VITALS
y DIAGNOSES, más las funciones PL/SQL de sellado y verificación."""

import oracledb

from models.consultation import Consultation, ConsultationVital, Diagnosis

_CONSULT_SELECT = """
    SELECT c.id, c.pet_id, c.appointment_id, c.triage_id, c.veterinarian_id,
           c.reason, c.symptoms, c.observations, c.diagnosis_summary,
           c.treatment_summary, c.status, c.started_at, c.ended_at,
           c.sealed_at, c.sealed_by, c.sealed_hash, c.created_at, c.updated_at,
           p.name AS pet_name,
           o.first_name || ' ' || o.last_name AS owner_name,
           v.full_name AS veterinarian_name
    FROM consultations c
    JOIN pets p ON p.id = c.pet_id
    JOIN owners o ON o.id = p.owner_id
    JOIN users v ON v.id = c.veterinarian_id
"""


def _row_to_consultation(row: tuple) -> Consultation:
    return Consultation(
        id=row[0], pet_id=row[1], appointment_id=row[2], triage_id=row[3],
        veterinarian_id=row[4], reason=row[5], symptoms=row[6],
        observations=row[7], diagnosis_summary=row[8], treatment_summary=row[9],
        status=row[10], started_at=row[11], ended_at=row[12], sealed_at=row[13],
        sealed_by=row[14], sealed_hash=row[15], created_at=row[16],
        updated_at=row[17], pet_name=row[18], owner_name=row[19],
        veterinarian_name=row[20],
    )


def list_consultations(
    conn: oracledb.Connection, pet_id: int | None = None
) -> list[Consultation]:
    sql = _CONSULT_SELECT
    params: dict = {}
    if pet_id is not None:
        sql += " WHERE c.pet_id = :pet_id"
        params["pet_id"] = pet_id
    sql += " ORDER BY c.started_at DESC"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_consultation(row) for row in cur.fetchall()]


def get_by_id(conn: oracledb.Connection, consultation_id: int) -> Consultation | None:
    with conn.cursor() as cur:
        cur.execute(_CONSULT_SELECT + " WHERE c.id = :id", {"id": consultation_id})
        row = cur.fetchone()
    return _row_to_consultation(row) if row else None


def insert_consultation(
    conn: oracledb.Connection,
    *,
    pet_id: int,
    appointment_id: int | None,
    triage_id: int | None,
    veterinarian_id: int,
    reason: str,
    symptoms: str | None,
    observations: str | None,
) -> int:
    """Crea una consulta en estado DRAFT. No hace COMMIT."""
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO consultations (
                pet_id, appointment_id, triage_id, veterinarian_id, reason,
                symptoms, observations, status, started_at,
                created_at, updated_at
            ) VALUES (
                :pet_id, :appointment_id, :triage_id, :veterinarian_id,
                :reason, :symptoms, :observations, 'DRAFT', SYSTIMESTAMP,
                SYSTIMESTAMP, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "pet_id": pet_id,
                "appointment_id": appointment_id,
                "triage_id": triage_id,
                "veterinarian_id": veterinarian_id,
                "reason": reason,
                "symptoms": symptoms,
                "observations": observations,
                "new_id": new_id,
            },
        )
        return int(new_id.getvalue()[0])


def update_content(
    conn: oracledb.Connection,
    consultation_id: int,
    *,
    reason: str,
    symptoms: str | None,
    observations: str | None,
    diagnosis_summary: str | None,
    treatment_summary: str | None,
) -> None:
    """Actualiza el contenido clínico (solo mientras esté en DRAFT)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE consultations
            SET reason = :reason,
                symptoms = :symptoms,
                observations = :observations,
                diagnosis_summary = :diagnosis_summary,
                treatment_summary = :treatment_summary
            WHERE id = :id
            """,
            {
                "reason": reason,
                "symptoms": symptoms,
                "observations": observations,
                "diagnosis_summary": diagnosis_summary,
                "treatment_summary": treatment_summary,
                "id": consultation_id,
            },
        )


def finalize(conn: oracledb.Connection, consultation_id: int) -> None:
    """Marca la consulta como FINALIZED con hora de cierre. No hace COMMIT."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE consultations
            SET status = 'FINALIZED', ended_at = SYSTIMESTAMP
            WHERE id = :id
            """,
            {"id": consultation_id},
        )


def seal(conn: oracledb.Connection, consultation_id: int, user_id: int) -> str:
    """Sella la consulta con la función PL/SQL (SHA-256 + auditoría)."""
    with conn.cursor() as cur:
        return cur.callfunc(
            "SEAL_CONSULTATION", oracledb.DB_TYPE_VARCHAR,
            [consultation_id, user_id],
        )


def verify_hash(conn: oracledb.Connection, consultation_id: int) -> bool:
    """Verifica la integridad del sello (1 = íntegra)."""
    with conn.cursor() as cur:
        result = cur.callfunc(
            "VERIFY_CONSULTATION_HASH", oracledb.DB_TYPE_NUMBER,
            [consultation_id],
        )
    return int(result) == 1


# ------------------------------------------------------------------ Vitales


def list_vitals(
    conn: oracledb.Connection, consultation_id: int
) -> list[ConsultationVital]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT v.id, v.consultation_id, v.recorded_by, v.weight_kg,
                   v.temperature_c, v.heart_rate_bpm, v.respiratory_rate_rpm,
                   v.oxygen_saturation_pct, v.pain_level, v.notes,
                   v.recorded_at, u.full_name
            FROM consultation_vitals v
            JOIN users u ON u.id = v.recorded_by
            WHERE v.consultation_id = :cid
            ORDER BY v.recorded_at
            """,
            {"cid": consultation_id},
        )
        return [
            ConsultationVital(
                id=r[0], consultation_id=r[1], recorded_by=r[2], weight_kg=r[3],
                temperature_c=r[4], heart_rate_bpm=r[5],
                respiratory_rate_rpm=r[6], oxygen_saturation_pct=r[7],
                pain_level=r[8], notes=r[9], recorded_at=r[10],
                recorded_by_name=r[11],
            )
            for r in cur.fetchall()
        ]


def insert_vitals(conn: oracledb.Connection, **fields) -> int:
    """Registra una toma de signos vitales. No hace COMMIT.

    ``fields``: consultation_id, recorded_by, weight_kg, temperature_c,
    heart_rate_bpm, respiratory_rate_rpm, oxygen_saturation_pct,
    pain_level, notes.
    """
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO consultation_vitals (
                consultation_id, recorded_by, weight_kg, temperature_c,
                heart_rate_bpm, respiratory_rate_rpm, oxygen_saturation_pct,
                pain_level, notes, recorded_at
            ) VALUES (
                :consultation_id, :recorded_by, :weight_kg, :temperature_c,
                :heart_rate_bpm, :respiratory_rate_rpm, :oxygen_saturation_pct,
                :pain_level, :notes, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {**fields, "new_id": new_id},
        )
        return int(new_id.getvalue()[0])


# -------------------------------------------------------------- Diagnósticos


def list_diagnoses(
    conn: oracledb.Connection, consultation_id: int
) -> list[Diagnosis]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, consultation_id, diagnostic_code, description,
                   is_primary, created_at
            FROM diagnoses
            WHERE consultation_id = :cid
            ORDER BY is_primary DESC, id
            """,
            {"cid": consultation_id},
        )
        return [
            Diagnosis(
                id=r[0], consultation_id=r[1], diagnostic_code=r[2],
                description=r[3], is_primary=bool(r[4]), created_at=r[5],
            )
            for r in cur.fetchall()
        ]


def insert_diagnosis(
    conn: oracledb.Connection,
    *,
    consultation_id: int,
    diagnostic_code: str | None,
    description: str,
    is_primary: bool,
) -> int:
    """Agrega un diagnóstico. No hace COMMIT."""
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO diagnoses (
                consultation_id, diagnostic_code, description, is_primary,
                created_at
            ) VALUES (
                :consultation_id, :diagnostic_code, :description, :is_primary,
                SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "consultation_id": consultation_id,
                "diagnostic_code": diagnostic_code,
                "description": description,
                "is_primary": 1 if is_primary else 0,
                "new_id": new_id,
            },
        )
        return int(new_id.getvalue()[0])


def demote_primary_diagnoses(
    conn: oracledb.Connection, consultation_id: int
) -> None:
    """Quita la marca de primario a los diagnósticos existentes."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE diagnoses SET is_primary = 0 WHERE consultation_id = :cid",
            {"cid": consultation_id},
        )
