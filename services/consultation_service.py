"""Service del historial clínico (consultas, vitales, diagnósticos, sellado).

Flujo: DRAFT (editable) → FINALIZED (cerrada) → SEALED (inmutable con
hash SHA-256 calculado por Oracle/DBMS_CRYPTO). Permisos:
CONSULTATIONS_READ para consultar, CONSULTATIONS_WRITE para registrar,
CONSULTATIONS_SEAL para sellar.
"""

import logging
from dataclasses import dataclass

import oracledb

from database.connection import connection_scope
from models.consultation import Consultation, ConsultationVital, Diagnosis
from models.pet import Pet
from models.user import User
from repositories import (
    appointment_repository,
    consultation_repository,
    pet_repository,
    triage_repository,
    user_repository,
)
from services import appointment_service, permission_service, session
from utils import validators
from utils.validators import ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConsultationFormData:
    """Datos de creación/edición de una consulta."""

    pet_id: int | None
    veterinarian_id: int | None
    appointment_id: int | None
    triage_id: int | None
    reason: str
    symptoms: str
    observations: str
    diagnosis_summary: str = ""
    treatment_summary: str = ""


@dataclass(frozen=True)
class VitalsFormData:
    """Datos de una toma de signos vitales."""

    weight_kg: float | None
    temperature_c: float | None
    heart_rate_bpm: int | None
    respiratory_rate_rpm: int | None
    oxygen_saturation_pct: int | None
    pain_level: int | None
    notes: str


# ------------------------------------------------------------------ lectura


def list_consultations(pet_id: int | None = None) -> list[Consultation]:
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        return consultation_repository.list_consultations(conn, pet_id)


def get_detail(
    consultation_id: int,
) -> tuple[Consultation, list[ConsultationVital], list[Diagnosis]]:
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        consultation = consultation_repository.get_by_id(conn, consultation_id)
        if consultation is None:
            raise ValidationError("La consulta no existe.")
        vitals = consultation_repository.list_vitals(conn, consultation_id)
        diagnoses = consultation_repository.list_diagnoses(conn, consultation_id)
        return consultation, vitals, diagnoses


def list_active_pets() -> list[Pet]:
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        return [p for p in pet_repository.list_pets(conn) if p.status == "ACTIVE"]


def list_veterinarians() -> list[User]:
    """Veterinarios activos; también incluye ADMIN (puede atender)."""
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        vets = user_repository.list_active_by_role(conn, "VETERINARIAN")
        admins = user_repository.list_active_by_role(conn, "ADMIN")
        seen = {user.id for user in vets}
        return vets + [admin for admin in admins if admin.id not in seen]


def list_open_appointments(pet_id: int) -> list:
    """Citas de la mascota que pueden vincularse a una consulta."""
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        return [
            a
            for a in appointment_repository.list_appointments(conn)
            if a.pet_id == pet_id
            and a.status in ("SCHEDULED", "CONFIRMED", "IN_ATTENTION")
        ]


def list_recent_triages(pet_id: int) -> list:
    """Triajes de la mascota disponibles para vincular."""
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        return [
            t for t in triage_repository.list_triages(conn) if t.pet_id == pet_id
        ]


def verify_seal(consultation_id: int) -> bool:
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        return consultation_repository.verify_hash(conn, consultation_id)


# ---------------------------------------------------------------- escritura


def create_consultation(data: ConsultationFormData) -> int:
    permission_service.require_permission("CONSULTATIONS_WRITE")
    with connection_scope(commit=True) as conn:
        return _create_consultation(conn, data)


def update_content(consultation_id: int, data: ConsultationFormData) -> None:
    permission_service.require_permission("CONSULTATIONS_WRITE")
    with connection_scope(commit=True) as conn:
        _update_content(conn, consultation_id, data)


def add_vitals(consultation_id: int, data: VitalsFormData) -> int:
    permission_service.require_permission("CONSULTATIONS_WRITE")
    with connection_scope(commit=True) as conn:
        return _add_vitals(conn, consultation_id, data)


def add_diagnosis(
    consultation_id: int, *, diagnostic_code: str, description: str,
    is_primary: bool,
) -> int:
    permission_service.require_permission("CONSULTATIONS_WRITE")
    with connection_scope(commit=True) as conn:
        return _add_diagnosis(
            conn, consultation_id, diagnostic_code=diagnostic_code,
            description=description, is_primary=is_primary,
        )


def finalize(consultation_id: int) -> None:
    permission_service.require_permission("CONSULTATIONS_WRITE")
    with connection_scope(commit=True) as conn:
        _finalize(conn, consultation_id)


def seal(consultation_id: int) -> str:
    """Sella la consulta y devuelve el hash SHA-256."""
    permission_service.require_permission("CONSULTATIONS_SEAL")
    current = session.get_current_user()
    if current is None:
        raise ValidationError("No hay una sesión activa.")
    with connection_scope(commit=True) as conn:
        sealed_hash = consultation_repository.seal(conn, consultation_id, current.id)
        logger.info("Consulta %s sellada: %s", consultation_id, sealed_hash)
        return sealed_hash


# ------------------------------------------------------------------ interno


def _require_draft(conn: oracledb.Connection, consultation_id: int) -> Consultation:
    consultation = consultation_repository.get_by_id(conn, consultation_id)
    if consultation is None:
        raise ValidationError("La consulta no existe.")
    if consultation.status != "DRAFT":
        raise ValidationError(
            "La consulta ya no está en borrador y no puede modificarse."
        )
    return consultation


def _create_consultation(
    conn: oracledb.Connection, data: ConsultationFormData
) -> int:
    if data.pet_id is None:
        raise ValidationError("Seleccione la mascota.")
    if pet_repository.get_by_id(conn, data.pet_id) is None:
        raise ValidationError("La mascota seleccionada no existe.")

    if data.veterinarian_id is None:
        raise ValidationError("Seleccione el veterinario responsable.")
    vet = user_repository.get_by_id(conn, data.veterinarian_id)
    if vet is None or not vet.is_active or vet.role_name not in (
        "VETERINARIAN", "ADMIN",
    ):
        raise ValidationError("El veterinario seleccionado no es válido.")

    reason = validators.validate_required_text(data.reason, "El motivo", 4000)

    appointment_id = None
    if data.appointment_id is not None:
        appointment = appointment_repository.get_by_id(conn, data.appointment_id)
        if appointment is None or appointment.pet_id != data.pet_id:
            raise ValidationError("La cita vinculada no corresponde a la mascota.")
        if appointment.status not in ("SCHEDULED", "CONFIRMED", "IN_ATTENTION"):
            raise ValidationError("La cita vinculada no está abierta.")
        appointment_id = appointment.id

    triage_id = None
    if data.triage_id is not None:
        triage = triage_repository.get_by_id(conn, data.triage_id)
        if triage is None or triage.pet_id != data.pet_id:
            raise ValidationError("El triaje vinculado no corresponde a la mascota.")
        triage_id = triage.id

    consultation_id = consultation_repository.insert_consultation(
        conn,
        pet_id=data.pet_id,
        appointment_id=appointment_id,
        triage_id=triage_id,
        veterinarian_id=data.veterinarian_id,
        reason=reason,
        symptoms=validators.validate_optional_text(data.symptoms, "Los síntomas", 4000),
        observations=validators.validate_optional_text(
            data.observations, "Las observaciones", 4000
        ),
    )

    if appointment_id is not None:
        appointment = appointment_repository.get_by_id(conn, appointment_id)
        if appointment.status != "IN_ATTENTION":
            appointment_service._change_status(conn, appointment_id, "IN_ATTENTION")

    logger.info("Consulta creada en borrador: id=%s", consultation_id)
    return consultation_id


def _update_content(
    conn: oracledb.Connection, consultation_id: int, data: ConsultationFormData
) -> None:
    _require_draft(conn, consultation_id)
    consultation_repository.update_content(
        conn,
        consultation_id,
        reason=validators.validate_required_text(data.reason, "El motivo", 4000),
        symptoms=validators.validate_optional_text(data.symptoms, "Los síntomas", 4000),
        observations=validators.validate_optional_text(
            data.observations, "Las observaciones", 4000
        ),
        diagnosis_summary=validators.validate_optional_text(
            data.diagnosis_summary, "El resumen diagnóstico", 4000
        ),
        treatment_summary=validators.validate_optional_text(
            data.treatment_summary, "El resumen de tratamiento", 4000
        ),
    )
    logger.info("Consulta %s actualizada (borrador)", consultation_id)


def _add_vitals(
    conn: oracledb.Connection, consultation_id: int, data: VitalsFormData
) -> int:
    _require_draft(conn, consultation_id)
    current = session.get_current_user()
    if current is None:
        raise ValidationError("No hay una sesión activa.")

    if data.weight_kg is not None and data.weight_kg <= 0:
        raise ValidationError("El peso debe ser mayor que cero.")
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
    if data.pain_level is not None and not 0 <= data.pain_level <= 10:
        raise ValidationError("El nivel de dolor debe estar entre 0 y 10.")

    vital_id = consultation_repository.insert_vitals(
        conn,
        consultation_id=consultation_id,
        recorded_by=current.id,
        weight_kg=data.weight_kg,
        temperature_c=data.temperature_c,
        heart_rate_bpm=data.heart_rate_bpm,
        respiratory_rate_rpm=data.respiratory_rate_rpm,
        oxygen_saturation_pct=data.oxygen_saturation_pct,
        pain_level=data.pain_level,
        notes=validators.validate_optional_text(data.notes, "Las notas", 4000),
    )
    logger.info("Vitales registrados: consulta=%s", consultation_id)
    return vital_id


def _add_diagnosis(
    conn: oracledb.Connection,
    consultation_id: int,
    *,
    diagnostic_code: str,
    description: str,
    is_primary: bool,
) -> int:
    _require_draft(conn, consultation_id)
    clean_description = validators.validate_required_text(
        description, "La descripción del diagnóstico", 4000
    )
    if is_primary:
        consultation_repository.demote_primary_diagnoses(conn, consultation_id)
    diagnosis_id = consultation_repository.insert_diagnosis(
        conn,
        consultation_id=consultation_id,
        diagnostic_code=validators.validate_optional_text(
            diagnostic_code, "El código diagnóstico", 50
        ),
        description=clean_description,
        is_primary=is_primary,
    )
    logger.info("Diagnóstico agregado: consulta=%s", consultation_id)
    return diagnosis_id


def _finalize(conn: oracledb.Connection, consultation_id: int) -> None:
    _require_draft(conn, consultation_id)
    consultation = consultation_repository.get_by_id(conn, consultation_id)
    consultation_repository.finalize(conn, consultation_id)

    # La cita vinculada se completa en la misma transacción.
    if consultation.appointment_id is not None:
        appointment = appointment_repository.get_by_id(
            conn, consultation.appointment_id
        )
        if appointment and appointment.status == "IN_ATTENTION":
            appointment_service._change_status(
                conn, consultation.appointment_id, "COMPLETED"
            )
    logger.info("Consulta %s finalizada", consultation_id)
