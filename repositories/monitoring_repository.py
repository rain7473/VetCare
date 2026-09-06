"""Repository de HOSPITALIZATION_MONITORING, VITAL_RANGES y CLINICAL_ALERTS."""

import oracledb

from models.monitoring import ClinicalAlert, MonitoringRecord, VitalRange

# Códigos alineados con columnas de HOSPITALIZATION_MONITORING.
PARAMETER_CODES = (
    "TEMPERATURE_C",
    "HEART_RATE_BPM",
    "RESPIRATORY_RATE_RPM",
    "OXYGEN_SATURATION_PCT",
    "WEIGHT_KG",
    "PAIN_LEVEL",
)


def list_monitoring(
    conn: oracledb.Connection, hospitalization_id: int
) -> list[MonitoringRecord]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.hospitalization_id, m.recorded_by, m.temperature_c,
                   m.heart_rate_bpm, m.respiratory_rate_rpm,
                   m.oxygen_saturation_pct, m.weight_kg, m.pain_level,
                   m.feeding_status, m.hydration_status, m.observations,
                   m.recorded_at, u.full_name
            FROM hospitalization_monitoring m
            JOIN users u ON u.id = m.recorded_by
            WHERE m.hospitalization_id = :hid
            ORDER BY m.recorded_at DESC
            """,
            {"hid": hospitalization_id},
        )
        return [_row_to_monitoring(row) for row in cur.fetchall()]


def insert_monitoring(conn: oracledb.Connection, **fields) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO hospitalization_monitoring (
                hospitalization_id, recorded_by, temperature_c, heart_rate_bpm,
                respiratory_rate_rpm, oxygen_saturation_pct, weight_kg,
                pain_level, feeding_status, hydration_status, observations,
                recorded_at
            ) VALUES (
                :hospitalization_id, :recorded_by, :temperature_c, :heart_rate_bpm,
                :respiratory_rate_rpm, :oxygen_saturation_pct, :weight_kg,
                :pain_level, :feeding_status, :hydration_status, :observations,
                SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {**fields, "new_id": new_id},
        )
        return int(new_id.getvalue()[0])


def list_vital_ranges(
    conn: oracledb.Connection, species_id: int | None = None
) -> list[VitalRange]:
    sql = """
        SELECT r.id, r.species_id, r.parameter_code, r.min_value, r.max_value,
               r.unit, r.description, r.is_active, s.name
        FROM vital_ranges r
        JOIN species s ON s.id = r.species_id
        WHERE r.is_active = 1
    """
    params: dict = {}
    if species_id is not None:
        sql += " AND r.species_id = :sid"
        params["sid"] = species_id
    sql += " ORDER BY s.name, r.parameter_code"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_range(row) for row in cur.fetchall()]


def upsert_vital_range(
    conn: oracledb.Connection,
    *,
    species_id: int,
    parameter_code: str,
    min_value: float | None,
    max_value: float | None,
    unit: str | None,
    description: str | None,
) -> int:
    """Crea o actualiza un rango configurado. No inventa valores médicos."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM vital_ranges
            WHERE species_id = :sid AND parameter_code = :code
            """,
            {"sid": species_id, "code": parameter_code},
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE vital_ranges
                SET min_value = :min_value,
                    max_value = :max_value,
                    unit = :unit,
                    description = :description,
                    is_active = 1
                WHERE id = :id
                """,
                {
                    "min_value": min_value,
                    "max_value": max_value,
                    "unit": unit,
                    "description": description,
                    "id": row[0],
                },
            )
            return int(row[0])

        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO vital_ranges (
                species_id, parameter_code, min_value, max_value, unit,
                description, is_active, created_at, updated_at
            ) VALUES (
                :sid, :code, :min_value, :max_value, :unit,
                :description, 1, SYSTIMESTAMP, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "sid": species_id,
                "code": parameter_code,
                "min_value": min_value,
                "max_value": max_value,
                "unit": unit,
                "description": description,
                "new_id": new_id,
            },
        )
        return int(new_id.getvalue()[0])


def list_alerts(
    conn: oracledb.Connection,
    *,
    hospitalization_id: int | None = None,
    open_only: bool = False,
) -> list[ClinicalAlert]:
    sql = """
        SELECT a.id, a.pet_id, a.hospitalization_id, a.monitoring_id,
               a.alert_type, a.severity, a.message, a.status, a.created_at,
               a.resolved_at, a.resolved_by, p.name, u.full_name
        FROM clinical_alerts a
        JOIN pets p ON p.id = a.pet_id
        LEFT JOIN users u ON u.id = a.resolved_by
        WHERE 1 = 1
    """
    params: dict = {}
    if hospitalization_id is not None:
        sql += " AND a.hospitalization_id = :hid"
        params["hid"] = hospitalization_id
    if open_only:
        sql += " AND a.status IN ('OPEN', 'ACKNOWLEDGED')"
    sql += " ORDER BY a.created_at DESC"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_alert(row) for row in cur.fetchall()]


def insert_alert(conn: oracledb.Connection, **fields) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO clinical_alerts (
                pet_id, hospitalization_id, monitoring_id, alert_type,
                severity, message, status, created_at
            ) VALUES (
                :pet_id, :hospitalization_id, :monitoring_id, :alert_type,
                :severity, :message, 'OPEN', SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {**fields, "new_id": new_id},
        )
        return int(new_id.getvalue()[0])


def set_alert_status(
    conn: oracledb.Connection,
    alert_id: int,
    *,
    status: str,
    resolved_by: int | None = None,
) -> None:
    with conn.cursor() as cur:
        if status == "RESOLVED":
            cur.execute(
                """
                UPDATE clinical_alerts
                SET status = :status,
                    resolved_at = SYSTIMESTAMP,
                    resolved_by = :resolved_by
                WHERE id = :id
                """,
                {"status": status, "resolved_by": resolved_by, "id": alert_id},
            )
        else:
            cur.execute(
                """
                UPDATE clinical_alerts
                SET status = :status
                WHERE id = :id
                """,
                {"status": status, "id": alert_id},
            )


def _row_to_monitoring(row: tuple) -> MonitoringRecord:
    return MonitoringRecord(
        id=row[0],
        hospitalization_id=row[1],
        recorded_by=row[2],
        temperature_c=row[3],
        heart_rate_bpm=row[4],
        respiratory_rate_rpm=row[5],
        oxygen_saturation_pct=row[6],
        weight_kg=row[7],
        pain_level=row[8],
        feeding_status=row[9],
        hydration_status=row[10],
        observations=row[11],
        recorded_at=row[12],
        recorded_by_name=row[13],
    )


def _row_to_range(row: tuple) -> VitalRange:
    return VitalRange(
        id=row[0],
        species_id=row[1],
        parameter_code=row[2],
        min_value=row[3],
        max_value=row[4],
        unit=row[5],
        description=row[6],
        is_active=bool(row[7]),
        species_name=row[8],
    )


def _row_to_alert(row: tuple) -> ClinicalAlert:
    return ClinicalAlert(
        id=row[0],
        pet_id=row[1],
        hospitalization_id=row[2],
        monitoring_id=row[3],
        alert_type=row[4],
        severity=row[5],
        message=row[6],
        status=row[7],
        created_at=row[8],
        resolved_at=row[9],
        resolved_by=row[10],
        pet_name=row[11],
        resolved_by_name=row[12],
    )
