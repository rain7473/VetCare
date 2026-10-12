"""Lecturas puntuales para la ficha de mascota; no modifica datos clínicos."""

import oracledb


def latest_weight(conn: oracledb.Connection, pet_id: int) -> float | None:
    """Último peso medido en una consulta de esta mascota."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT v.weight_kg
            FROM consultation_vitals v
            JOIN consultations c ON c.id = v.consultation_id
            WHERE c.pet_id = :pet_id AND v.weight_kg IS NOT NULL
            ORDER BY v.recorded_at DESC, v.id DESC
            FETCH FIRST 1 ROW ONLY
            """,
            {"pet_id": pet_id},
        )
        row = cur.fetchone()
    return float(row[0]) if row else None
