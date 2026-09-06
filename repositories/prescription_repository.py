"""Repository de la tabla PRESCRIPTIONS."""

import oracledb

from models.prescription import Prescription


def list_by_consultation(
    conn: oracledb.Connection, consultation_id: int
) -> list[Prescription]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.id, p.consultation_id, p.medication_id, p.prescribed_by,
                   p.weight_used_kg, p.dose_per_kg, p.dose_unit,
                   p.calculated_total_dose, p.concentration_value,
                   p.concentration_unit, p.calculated_volume, p.volume_unit,
                   p.route, p.frequency_text, p.duration_days, p.instructions,
                   p.created_at, m.name, u.full_name
            FROM prescriptions p
            JOIN medications m ON m.id = p.medication_id
            JOIN users u ON u.id = p.prescribed_by
            WHERE p.consultation_id = :cid
            ORDER BY p.created_at
            """,
            {"cid": consultation_id},
        )
        return [_row_to_prescription(row) for row in cur.fetchall()]


def insert_prescription(conn: oracledb.Connection, **fields) -> int:
    """Registra una prescripción. No hace COMMIT.

    ``fields``: consultation_id, medication_id, prescribed_by, weight_used_kg,
    dose_per_kg, dose_unit, calculated_total_dose, concentration_value,
    concentration_unit, calculated_volume, volume_unit, route,
    frequency_text, duration_days, instructions.
    """
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO prescriptions (
                consultation_id, medication_id, prescribed_by, weight_used_kg,
                dose_per_kg, dose_unit, calculated_total_dose,
                concentration_value, concentration_unit, calculated_volume,
                volume_unit, route, frequency_text, duration_days,
                instructions, created_at
            ) VALUES (
                :consultation_id, :medication_id, :prescribed_by, :weight_used_kg,
                :dose_per_kg, :dose_unit, :calculated_total_dose,
                :concentration_value, :concentration_unit, :calculated_volume,
                :volume_unit, :route, :frequency_text, :duration_days,
                :instructions, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {**fields, "new_id": new_id},
        )
        return int(new_id.getvalue()[0])


def _row_to_prescription(row: tuple) -> Prescription:
    return Prescription(
        id=row[0],
        consultation_id=row[1],
        medication_id=row[2],
        prescribed_by=row[3],
        weight_used_kg=row[4],
        dose_per_kg=row[5],
        dose_unit=row[6],
        calculated_total_dose=row[7],
        concentration_value=row[8],
        concentration_unit=row[9],
        calculated_volume=row[10],
        volume_unit=row[11],
        route=row[12],
        frequency_text=row[13],
        duration_days=row[14],
        instructions=row[15],
        created_at=row[16],
        medication_name=row[17],
        prescribed_by_name=row[18],
    )
