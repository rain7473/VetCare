"""Service de monitoreo hospitalario y alertas clínicas.

Las alertas solo se generan cuando existe un rango activo en VITAL_RANGES.
No se inventan umbrales veterinarios.
"""

import logging
from dataclasses import dataclass

import oracledb

from database.connection import connection_scope
from models.monitoring import ClinicalAlert, MonitoringRecord, VitalRange
from repositories import (
    hospitalization_repository,
    monitoring_repository,
    pet_repository,
    species_repository,
)
from services import permission_service, session
from services.hospitalization_service import ACTIVE_STATUSES
from utils import validators
from utils.validators import ValidationError

logger = logging.getLogger(__name__)

PARAMETER_LABELS = {
    "TEMPERATURE_C": "Temperatura",
    "HEART_RATE_BPM": "Frecuencia cardíaca",
    "RESPIRATORY_RATE_RPM": "Frecuencia respiratoria",
    "OXYGEN_SATURATION_PCT": "Saturación de oxígeno",
    "WEIGHT_KG": "Peso",
    "PAIN_LEVEL": "Dolor",
}


@dataclass(frozen=True)
class MonitoringFormData:
    hospitalization_id: int
    temperature_c: float | None
    heart_rate_bpm: int | None
    respiratory_rate_rpm: int | None
    oxygen_saturation_pct: float | None
    weight_kg: float | None
    pain_level: int | None
    feeding_status: str
    hydration_status: str
    observations: str


@dataclass(frozen=True)
class VitalRangeFormData:
    species_id: int | None
    parameter_code: str
    min_value: float | None
    max_value: float | None
    unit: str
    description: str


def list_monitoring(hospitalization_id: int) -> list[MonitoringRecord]:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope() as conn:
        return monitoring_repository.list_monitoring(conn, hospitalization_id)


def list_alerts(
    hospitalization_id: int | None = None, *, open_only: bool = False
) -> list[ClinicalAlert]:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope() as conn:
        return monitoring_repository.list_alerts(
            conn, hospitalization_id=hospitalization_id, open_only=open_only
        )


def list_vital_ranges(species_id: int | None = None) -> list[VitalRange]:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope() as conn:
        return monitoring_repository.list_vital_ranges(conn, species_id)


def list_species() -> list[tuple[int, str]]:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope() as conn:
        return species_repository.list_species(conn)


def save_vital_range(data: VitalRangeFormData) -> int:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope(commit=True) as conn:
        return _save_vital_range(conn, data)


def record_monitoring(data: MonitoringFormData) -> tuple[int, list[int]]:
    """Registra una medición y crea alertas según rangos configurados.

    Returns:
        (monitoring_id, alert_ids)
    """
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope(commit=True) as conn:
        return _record_monitoring(conn, data)


def acknowledge_alert(alert_id: int) -> None:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope(commit=True) as conn:
        _set_alert_status(conn, alert_id, "ACKNOWLEDGED")


def resolve_alert(alert_id: int) -> None:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope(commit=True) as conn:
        current = session.get_current_user()
        if current is None:
            raise ValidationError("No hay una sesión activa.")
        _set_alert_status(conn, alert_id, "RESOLVED", resolved_by=current.id)


# ------------------------------------------------------------------ interno


def _save_vital_range(conn: oracledb.Connection, data: VitalRangeFormData) -> int:
    if data.species_id is None:
        raise ValidationError("Seleccione la especie.")
    if data.parameter_code not in monitoring_repository.PARAMETER_CODES:
        raise ValidationError("El parámetro vital no es válido.")
    if data.min_value is None and data.max_value is None:
        raise ValidationError("Indique al menos un valor mínimo o máximo.")
    if (
        data.min_value is not None
        and data.max_value is not None
        and data.min_value > data.max_value
    ):
        raise ValidationError("El mínimo no puede ser mayor que el máximo.")
    return monitoring_repository.upsert_vital_range(
        conn,
        species_id=data.species_id,
        parameter_code=data.parameter_code,
        min_value=data.min_value,
        max_value=data.max_value,
        unit=validators.validate_optional_text(data.unit, "La unidad", 30),
        description=validators.validate_optional_text(
            data.description, "La descripción", 4000
        ),
    )


def _record_monitoring(
    conn: oracledb.Connection, data: MonitoringFormData
) -> tuple[int, list[int]]:
    current = session.get_current_user()
    if current is None:
        raise ValidationError("No hay una sesión activa.")

    hosp = hospitalization_repository.get_by_id(conn, data.hospitalization_id)
    if hosp is None:
        raise ValidationError("La hospitalización no existe.")
    if hosp.status not in ACTIVE_STATUSES:
        raise ValidationError(
            "Solo se puede monitorear una hospitalización activa."
        )

    _validate_vitals(data)

    monitoring_id = monitoring_repository.insert_monitoring(
        conn,
        hospitalization_id=hosp.id,
        recorded_by=current.id,
        temperature_c=data.temperature_c,
        heart_rate_bpm=data.heart_rate_bpm,
        respiratory_rate_rpm=data.respiratory_rate_rpm,
        oxygen_saturation_pct=data.oxygen_saturation_pct,
        weight_kg=data.weight_kg,
        pain_level=data.pain_level,
        feeding_status=validators.validate_optional_text(
            data.feeding_status, "La alimentación", 100
        ),
        hydration_status=validators.validate_optional_text(
            data.hydration_status, "La hidratación", 100
        ),
        observations=validators.validate_optional_text(
            data.observations, "Las observaciones", 4000
        ),
    )

    pet = pet_repository.get_by_id(conn, hosp.pet_id)
    species_id = pet.species_id if pet else None
    alert_ids = _create_alerts_from_ranges(
        conn,
        pet_id=hosp.pet_id,
        hospitalization_id=hosp.id,
        monitoring_id=monitoring_id,
        species_id=species_id,
        data=data,
    )
    logger.info(
        "Monitoreo %s registrado (%s alerta(s))", monitoring_id, len(alert_ids)
    )
    return monitoring_id, alert_ids


def _validate_vitals(data: MonitoringFormData) -> None:
    has_any = any(
        value is not None
        for value in (
            data.temperature_c,
            data.heart_rate_bpm,
            data.respiratory_rate_rpm,
            data.oxygen_saturation_pct,
            data.weight_kg,
            data.pain_level,
        )
    ) or bool(data.feeding_status.strip()) or bool(data.hydration_status.strip()) or bool(
        data.observations.strip()
    )
    if not has_any:
        raise ValidationError("Registre al menos un signo o una observación.")
    if data.temperature_c is not None and not 20 <= data.temperature_c <= 45:
        raise ValidationError("La temperatura registrada no es fisiológicamente válida.")
    if data.heart_rate_bpm is not None and data.heart_rate_bpm <= 0:
        raise ValidationError("La frecuencia cardíaca debe ser mayor que cero.")
    if data.respiratory_rate_rpm is not None and data.respiratory_rate_rpm <= 0:
        raise ValidationError("La frecuencia respiratoria debe ser mayor que cero.")
    if data.oxygen_saturation_pct is not None and not (
        0 <= data.oxygen_saturation_pct <= 100
    ):
        raise ValidationError("La saturación de oxígeno debe estar entre 0 y 100.")
    if data.weight_kg is not None and data.weight_kg <= 0:
        raise ValidationError("El peso debe ser mayor que cero.")
    if data.pain_level is not None and not 0 <= data.pain_level <= 10:
        raise ValidationError("El nivel de dolor debe estar entre 0 y 10.")


def _create_alerts_from_ranges(
    conn: oracledb.Connection,
    *,
    pet_id: int,
    hospitalization_id: int,
    monitoring_id: int,
    species_id: int | None,
    data: MonitoringFormData,
) -> list[int]:
    if species_id is None:
        return []

    ranges = {
        item.parameter_code: item
        for item in monitoring_repository.list_vital_ranges(conn, species_id)
    }
    measured = {
        "TEMPERATURE_C": data.temperature_c,
        "HEART_RATE_BPM": data.heart_rate_bpm,
        "RESPIRATORY_RATE_RPM": data.respiratory_rate_rpm,
        "OXYGEN_SATURATION_PCT": data.oxygen_saturation_pct,
        "WEIGHT_KG": data.weight_kg,
        "PAIN_LEVEL": data.pain_level,
    }

    alert_ids: list[int] = []
    for code, value in measured.items():
        if value is None or code not in ranges:
            continue
        vital_range = ranges[code]
        out_of_range = False
        if vital_range.min_value is not None and value < float(vital_range.min_value):
            out_of_range = True
        if vital_range.max_value is not None and value > float(vital_range.max_value):
            out_of_range = True
        if not out_of_range:
            continue

        label = PARAMETER_LABELS.get(code, code)
        unit = vital_range.unit or ""
        message = (
            f"{label} fuera de rango configurado: {value} {unit}".strip()
            + f" (rango {vital_range.min_value}–{vital_range.max_value})"
        )
        severity = _severity_for(code, value, vital_range)
        alert_ids.append(
            monitoring_repository.insert_alert(
                conn,
                pet_id=pet_id,
                hospitalization_id=hospitalization_id,
                monitoring_id=monitoring_id,
                alert_type=code,
                severity=severity,
                message=message,
            )
        )
    return alert_ids


def _severity_for(code: str, value: float, vital_range: VitalRange) -> str:
    """Severidad relativa al rango configurado (sin inventar umbrales clínicos)."""
    if code == "OXYGEN_SATURATION_PCT" and vital_range.min_value is not None:
        if value < float(vital_range.min_value) - 5:
            return "CRITICAL"
        return "HIGH"
    if code == "TEMPERATURE_C":
        return "HIGH"
    if code == "PAIN_LEVEL" and value >= 8:
        return "HIGH"
    return "MEDIUM"


def _set_alert_status(
    conn: oracledb.Connection,
    alert_id: int,
    status: str,
    resolved_by: int | None = None,
) -> None:
    alerts = monitoring_repository.list_alerts(conn)
    current = next((item for item in alerts if item.id == alert_id), None)
    if current is None:
        raise ValidationError("La alerta no existe.")
    if current.status == "RESOLVED":
        raise ValidationError("La alerta ya está resuelta.")
    if status == "ACKNOWLEDGED" and current.status != "OPEN":
        raise ValidationError("Solo se pueden acusar alertas abiertas.")
    monitoring_repository.set_alert_status(
        conn, alert_id, status=status, resolved_by=resolved_by
    )
