"""Repository del catálogo MEDICATIONS y MEDICATION_GUIDELINES."""

import oracledb

from models.medication import Medication, MedicationGuideline


def list_active_medications(conn: oracledb.Connection) -> list[Medication]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, product_id, name, active_ingredient, presentation,
                   concentration_value, concentration_unit, default_route,
                   is_active, created_at, updated_at
            FROM medications
            WHERE is_active = 1
            ORDER BY name
            """
        )
        return [_row_to_medication(row) for row in cur.fetchall()]


def get_medication(conn: oracledb.Connection, medication_id: int) -> Medication | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, product_id, name, active_ingredient, presentation,
                   concentration_value, concentration_unit, default_route,
                   is_active, created_at, updated_at
            FROM medications
            WHERE id = :id
            """,
            {"id": medication_id},
        )
        row = cur.fetchone()
    return _row_to_medication(row) if row else None


def list_guidelines(
    conn: oracledb.Connection,
    medication_id: int,
    species_id: int | None = None,
) -> list[MedicationGuideline]:
    """Guías activas del medicamento; si hay especie, prioriza las compatibles."""
    sql = """
        SELECT g.id, g.medication_id, g.species_id, g.min_dose_per_kg,
               g.max_dose_per_kg, g.dose_unit, g.frequency_text, g.notes,
               g.approved_by, g.is_active, s.name AS species_name
        FROM medication_guidelines g
        LEFT JOIN species s ON s.id = g.species_id
        WHERE g.medication_id = :mid AND g.is_active = 1
    """
    params: dict = {"mid": medication_id}
    if species_id is not None:
        sql += " AND (g.species_id IS NULL OR g.species_id = :sid)"
        params["sid"] = species_id
    sql += " ORDER BY g.species_id NULLS LAST, g.id"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_guideline(row) for row in cur.fetchall()]


def insert_medication(
    conn: oracledb.Connection,
    *,
    name: str,
    active_ingredient: str | None,
    presentation: str | None,
    concentration_value: float | None,
    concentration_unit: str | None,
    default_route: str | None,
) -> int:
    """Inserta un medicamento de catálogo. No hace COMMIT."""
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO medications (
                name, active_ingredient, presentation, concentration_value,
                concentration_unit, default_route, is_active,
                created_at, updated_at
            ) VALUES (
                :name, :active_ingredient, :presentation, :concentration_value,
                :concentration_unit, :default_route, 1,
                SYSTIMESTAMP, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "name": name,
                "active_ingredient": active_ingredient,
                "presentation": presentation,
                "concentration_value": concentration_value,
                "concentration_unit": concentration_unit,
                "default_route": default_route,
                "new_id": new_id,
            },
        )
        return int(new_id.getvalue()[0])


def insert_guideline(
    conn: oracledb.Connection,
    *,
    medication_id: int,
    species_id: int | None,
    min_dose_per_kg: float | None,
    max_dose_per_kg: float | None,
    dose_unit: str,
    frequency_text: str | None,
    notes: str | None = None,
) -> int:
    """Inserta una guía de dosificación. No hace COMMIT."""
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO medication_guidelines (
                medication_id, species_id, min_dose_per_kg, max_dose_per_kg,
                dose_unit, frequency_text, notes, is_active,
                created_at, updated_at
            ) VALUES (
                :medication_id, :species_id, :min_dose_per_kg, :max_dose_per_kg,
                :dose_unit, :frequency_text, :notes, 1,
                SYSTIMESTAMP, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "medication_id": medication_id,
                "species_id": species_id,
                "min_dose_per_kg": min_dose_per_kg,
                "max_dose_per_kg": max_dose_per_kg,
                "dose_unit": dose_unit,
                "frequency_text": frequency_text,
                "notes": notes,
                "new_id": new_id,
            },
        )
        return int(new_id.getvalue()[0])


def _row_to_medication(row: tuple) -> Medication:
    return Medication(
        id=row[0],
        product_id=row[1],
        name=row[2],
        active_ingredient=row[3],
        presentation=row[4],
        concentration_value=row[5],
        concentration_unit=row[6],
        default_route=row[7],
        is_active=bool(row[8]),
        created_at=row[9],
        updated_at=row[10],
    )


def _row_to_guideline(row: tuple) -> MedicationGuideline:
    return MedicationGuideline(
        id=row[0],
        medication_id=row[1],
        species_id=row[2],
        min_dose_per_kg=row[3],
        max_dose_per_kg=row[4],
        dose_unit=row[5],
        frequency_text=row[6],
        notes=row[7],
        approved_by=row[8],
        is_active=bool(row[9]),
        species_name=row[10],
    )
