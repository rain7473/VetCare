"""Service del módulo de triaje.

Permiso: TRIAGE_CREATE. Los triajes son registros clínicos inmutables:
solo se crean y se consultan. Incluye la calculadora de prioridad
(semáforo 1–4) con razones trazables; el nivel sugerido puede ser
ajustado manualmente por quien registra.
"""

import logging
from dataclasses import dataclass
from datetime import date

import oracledb

from database.connection import connection_scope
from models.pet import Pet
from models.triage import Triage
from repositories import (
    appointment_repository,
    pet_repository,
    triage_repository,
)
from services import appointment_service, permission_service, session
from utils import validators
from utils.validators import ValidationError

logger = logging.getLogger(__name__)

VALID_CONSCIOUSNESS = ("ALERT", "DEPRESSED", "UNCONSCIOUS")


@dataclass(frozen=True)
class TriageFormData:
    """Datos del formulario de triaje."""

    pet_id: int | None
    appointment_id: int | None
    reason: str
    consciousness_status: str | None
    respiratory_distress: bool
    active_bleeding: bool
    can_walk: bool | None
    seizures: bool
    pain_level: int | None
    temperature_c: float | None
    heart_rate_bpm: int | None
    respiratory_rate_rpm: int | None
    oxygen_saturation_pct: int | None
    priority_level: int
    priority_reason: str
    observations: str


def suggest_priority(
    *,
    consciousness_status: str | None,
    respiratory_distress: bool,
    active_bleeding: bool,
    can_walk: bool | None,
    seizures: bool,
    pain_level: int | None,
    temperature_c: float | None,
    oxygen_saturation_pct: int | None,
) -> tuple[int, str]:
    """Sugiere el nivel de prioridad (1–4) y la razón, según los signos."""
    critical: list[str] = []
    urgent: list[str] = []
    priority3: list[str] = []

    if consciousness_status == "UNCONSCIOUS":
        critical.append("inconsciente")
    if respiratory_distress:
        critical.append("dificultad respiratoria")
    if active_bleeding:
        critical.append("sangrado activo")
    if seizures:
        critical.append("convulsiones")
    if oxygen_saturation_pct is not None and oxygen_saturation_pct < 90:
        critical.append(f"SpO2 {oxygen_saturation_pct}%")
    if temperature_c is not None and (temperature_c >= 41 or temperature_c <= 35):
        critical.append(f"temperatura extrema ({temperature_c} °C)")

    if pain_level is not None and pain_level >= 7:
        urgent.append(f"dolor severo ({pain_level}/10)")
    if can_walk is False:
        urgent.append("no puede caminar")
    if temperature_c is not None and 35 < temperature_c <= 36:
        urgent.append(f"hipotermia leve ({temperature_c} °C)")
    if temperature_c is not None and 39.5 <= temperature_c < 41:
        urgent.append(f"fiebre alta ({temperature_c} °C)")
    if oxygen_saturation_pct is not None and 90 <= oxygen_saturation_pct < 95:
        urgent.append(f"SpO2 baja ({oxygen_saturation_pct}%)")

    if pain_level is not None and 4 <= pain_level < 7:
        priority3.append(f"dolor moderado ({pain_level}/10)")
    if consciousness_status == "DEPRESSED":
        priority3.append("estado deprimido/letárgico")

    if critical:
        return 1, "Crítico: " + ", ".join(critical) + "."
    if urgent:
        return 2, "Urgente: " + ", ".join(urgent) + "."
    if priority3:
        return 3, "Prioritario: " + ", ".join(priority3) + "."
    return 4, "Sin signos de alarma en el triaje."


def list_triages(day: date | None = None) -> list[Triage]:
    permission_service.require_permission("TRIAGE_CREATE")
    with connection_scope() as conn:
        return triage_repository.list_triages(conn, day)


def list_active_pets() -> list[Pet]:
    permission_service.require_permission("TRIAGE_CREATE")
    with connection_scope() as conn:
        return [p for p in pet_repository.list_pets(conn) if p.status == "ACTIVE"]


def list_open_appointments(pet_id: int) -> list:
    """Citas abiertas (programadas/confirmadas) de una mascota."""
    permission_service.require_permission("TRIAGE_CREATE")
    with connection_scope() as conn:
        return [
            a
            for a in appointment_repository.list_appointments(conn)
            if a.pet_id == pet_id and a.status in ("SCHEDULED", "CONFIRMED")
        ]


def create_triage(data: TriageFormData) -> int:
    permission_service.require_permission("TRIAGE_CREATE")
    with connection_scope(commit=True) as conn:
        return _create_triage(conn, data)


# ------------------------------------------------------------------ interno


def _create_triage(conn: oracledb.Connection, data: TriageFormData) -> int:
    current = session.get_current_user()
    if current is None:
        raise ValidationError("No hay una sesión activa.")

    if data.pet_id is None:
        raise ValidationError("Seleccione la mascota.")
    if pet_repository.get_by_id(conn, data.pet_id) is None:
        raise ValidationError("La mascota seleccionada no existe.")

    reason = validators.validate_required_text(data.reason, "El motivo", 4000)

    if data.consciousness_status is not None and (
        data.consciousness_status not in VALID_CONSCIOUSNESS
    ):
        raise ValidationError("Estado de consciencia no válido.")
    if not 1 <= data.priority_level <= 4:
        raise ValidationError("La prioridad debe estar entre 1 y 4.")
    if data.pain_level is not None and not 0 <= data.pain_level <= 10:
        raise ValidationError("El nivel de dolor debe estar entre 0 y 10.")
    if data.oxygen_saturation_pct is not None and not (
        0 <= data.oxygen_saturation_pct <= 100
    ):
        raise ValidationError("La saturación de oxígeno debe estar entre 0 y 100.")
    if data.heart_rate_bpm is not None and data.heart_rate_bpm <= 0:
        raise ValidationError("La frecuencia cardíaca debe ser mayor que cero.")
    if data.respiratory_rate_rpm is not None and data.respiratory_rate_rpm <= 0:
        raise ValidationError("La frecuencia respiratoria debe ser mayor que cero.")
    if data.temperature_c is not None and not 20 <= data.temperature_c <= 45:
        raise ValidationError("La temperatura registrada no es fisiológicamente válida.")

    appointment_id = None
    if data.appointment_id is not None:
        appointment = appointment_repository.get_by_id(conn, data.appointment_id)
        if appointment is None or appointment.pet_id != data.pet_id:
            raise ValidationError("La cita vinculada no corresponde a la mascota.")
        if appointment.status not in ("SCHEDULED", "CONFIRMED"):
            raise ValidationError("La cita vinculada no está abierta.")
        appointment_id = appointment.id

    triage_id = triage_repository.insert_triage(
        conn,
        pet_id=data.pet_id,
        appointment_id=appointment_id,
        recorded_by=current.id,
        reason=reason,
        consciousness_status=data.consciousness_status,
        respiratory_distress=1 if data.respiratory_distress else 0,
        active_bleeding=1 if data.active_bleeding else 0,
        can_walk=None if data.can_walk is None else (1 if data.can_walk else 0),
        seizures=1 if data.seizures else 0,
        pain_level=data.pain_level,
        temperature_c=data.temperature_c,
        heart_rate_bpm=data.heart_rate_bpm,
        respiratory_rate_rpm=data.respiratory_rate_rpm,
        oxygen_saturation_pct=data.oxygen_saturation_pct,
        priority_level=data.priority_level,
        priority_reason=validators.validate_optional_text(
            data.priority_reason, "La razón de prioridad", 4000
        ),
        observations=validators.validate_optional_text(
            data.observations, "Las observaciones", 4000
        ),
    )

    # La cita vinculada pasa a atención en la misma transacción.
    if appointment_id is not None:
        appointment_service._change_status(conn, appointment_id, "IN_ATTENTION")

    logger.info(
        "Triaje creado: id=%s (prioridad %s)", triage_id, data.priority_level
    )
    return triage_id
