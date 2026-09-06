"""Service del módulo de citas.

Permiso: APPOINTMENTS_MANAGE. Aplica la máquina de estados de la cita;
IN_ATTENTION y COMPLETED se activan desde Triaje/Consultas en sus
objetivos, pero las transiciones ya están definidas aquí.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import oracledb

from database.connection import connection_scope
from models.appointment import Appointment
from models.pet import Pet
from models.user import User
from repositories import appointment_repository, pet_repository, user_repository
from services import permission_service, session
from utils import validators
from utils.validators import ValidationError

logger = logging.getLogger(__name__)

# Estado actual → estados destino permitidos.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "SCHEDULED": {"CONFIRMED", "IN_ATTENTION", "CANCELLED", "NO_SHOW"},
    "CONFIRMED": {"IN_ATTENTION", "CANCELLED", "NO_SHOW"},
    "IN_ATTENTION": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
    "NO_SHOW": set(),
}

EDITABLE_STATUSES = {"SCHEDULED", "CONFIRMED"}


@dataclass(frozen=True)
class AppointmentFormData:
    """Datos del formulario de cita."""

    pet_id: int | None
    veterinarian_id: int | None
    appointment_at: datetime
    reason: str
    notes: str


def list_appointments(day: date | None = None) -> list[Appointment]:
    permission_service.require_permission("APPOINTMENTS_MANAGE")
    with connection_scope() as conn:
        return appointment_repository.list_appointments(conn, day)


def list_active_pets() -> list[Pet]:
    permission_service.require_permission("APPOINTMENTS_MANAGE")
    with connection_scope() as conn:
        return [p for p in pet_repository.list_pets(conn) if p.status == "ACTIVE"]


def list_veterinarians() -> list[User]:
    permission_service.require_permission("APPOINTMENTS_MANAGE")
    with connection_scope() as conn:
        return user_repository.list_active_by_role(conn, "VETERINARIAN")


def create_appointment(data: AppointmentFormData) -> int:
    permission_service.require_permission("APPOINTMENTS_MANAGE")
    with connection_scope(commit=True) as conn:
        return _create_appointment(conn, data)


def update_appointment(appointment_id: int, data: AppointmentFormData) -> None:
    permission_service.require_permission("APPOINTMENTS_MANAGE")
    with connection_scope(commit=True) as conn:
        _update_appointment(conn, appointment_id, data)


def change_status(appointment_id: int, new_status: str) -> None:
    permission_service.require_permission("APPOINTMENTS_MANAGE")
    with connection_scope(commit=True) as conn:
        _change_status(conn, appointment_id, new_status)


# ------------------------------------------------------------------ interno


def _validate(
    conn: oracledb.Connection, data: AppointmentFormData, *, is_new: bool
) -> dict:
    if data.pet_id is None:
        raise ValidationError("Seleccione la mascota de la cita.")
    pet = pet_repository.get_by_id(conn, data.pet_id)
    if pet is None:
        raise ValidationError("La mascota seleccionada no existe.")

    if data.appointment_at is None:
        raise ValidationError("Indique la fecha y hora de la cita.")
    if is_new and data.appointment_at < datetime.now() - timedelta(minutes=5):
        raise ValidationError("La cita no puede programarse en el pasado.")

    reason = validators.validate_required_text(data.reason, "El motivo", 4000)
    notes = validators.validate_optional_text(data.notes, "Las notas", 4000)

    if data.veterinarian_id is not None:
        vet = user_repository.get_by_id(conn, data.veterinarian_id)
        if vet is None or not vet.is_active or vet.role_name != "VETERINARIAN":
            raise ValidationError("El veterinario seleccionado no es válido.")

    return {
        "pet_id": data.pet_id,
        "veterinarian_id": data.veterinarian_id,
        "appointment_at": data.appointment_at,
        "reason": reason,
        "notes": notes,
    }


def _create_appointment(conn: oracledb.Connection, data: AppointmentFormData) -> int:
    current = session.get_current_user()
    if current is None:
        raise ValidationError("No hay una sesión activa.")
    fields = _validate(conn, data, is_new=True)
    appointment_id = appointment_repository.insert_appointment(
        conn, created_by=current.id, **fields
    )
    logger.info("Cita creada: id=%s", appointment_id)
    return appointment_id


def _update_appointment(
    conn: oracledb.Connection, appointment_id: int, data: AppointmentFormData
) -> None:
    existing = appointment_repository.get_by_id(conn, appointment_id)
    if existing is None:
        raise ValidationError("La cita no existe.")
    if existing.status not in EDITABLE_STATUSES:
        raise ValidationError(
            "Solo se pueden editar citas programadas o confirmadas."
        )
    fields = _validate(conn, data, is_new=False)
    appointment_repository.update_appointment(conn, appointment_id, **fields)
    logger.info("Cita actualizada: id=%s", appointment_id)


def _change_status(
    conn: oracledb.Connection, appointment_id: int, new_status: str
) -> None:
    existing = appointment_repository.get_by_id(conn, appointment_id)
    if existing is None:
        raise ValidationError("La cita no existe.")
    allowed = ALLOWED_TRANSITIONS.get(existing.status, set())
    if new_status not in allowed:
        raise ValidationError(
            f"No es posible pasar la cita de «{existing.status}» a «{new_status}»."
        )
    appointment_repository.set_status(conn, appointment_id, new_status)
    logger.info("Cita %s: %s → %s", appointment_id, existing.status, new_status)
