"""Service de control quirúrgico.

Estados: PLANNED → IN_PROGRESS → COMPLETED | CANCELLED.
Oracle impide cambios si la consulta está SEALED. Permiso: SURGERY_MANAGE.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

import oracledb

from database.connection import connection_scope
from models.surgery import Surgery, SurgeryMedication
from repositories import (
    consultation_repository,
    medication_repository,
    surgery_repository,
    user_repository,
)
from services import permission_service
from utils import validators
from utils.validators import ValidationError

logger = logging.getLogger(__name__)

_TRANSITIONS = {
    "PLANNED": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


@dataclass(frozen=True)
class SurgeryFormData:
    consultation_id: int | None
    veterinarian_id: int | None
    procedure_name: str
    scheduled_at: datetime | None
    weight_kg: float | None
    preoperative_notes: str
    postoperative_notes: str = ""
    recovery_recommendations: str = ""
    medication_id: int | None = None
    medication_dose_text: str = ""
    medication_route: str = ""


def list_surgeries(consultation_id: int) -> list[Surgery]:
    permission_service.require_permission("SURGERY_MANAGE")
    with connection_scope() as conn:
        return surgery_repository.list_by_consultation(conn, consultation_id)


def list_medications(surgery_id: int) -> list[SurgeryMedication]:
    permission_service.require_permission("SURGERY_MANAGE")
    with connection_scope() as conn:
        return surgery_repository.list_medications(conn, surgery_id)


def create_surgery(data: SurgeryFormData) -> int:
    permission_service.require_permission("SURGERY_MANAGE")
    with connection_scope(commit=True) as conn:
        return _create_surgery(conn, data)


def update_surgery(surgery_id: int, data: SurgeryFormData) -> None:
    permission_service.require_permission("SURGERY_MANAGE")
    with connection_scope(commit=True) as conn:
        _update_surgery(conn, surgery_id, data)


def change_status(surgery_id: int, new_status: str) -> None:
    permission_service.require_permission("SURGERY_MANAGE")
    with connection_scope(commit=True) as conn:
        _change_status(conn, surgery_id, new_status)


def _create_surgery(conn: oracledb.Connection, data: SurgeryFormData) -> int:
    consultation = _require_open_consultation(conn, data.consultation_id)
    vet = _require_veterinarian(conn, data.veterinarian_id)
    name = validators.validate_required_text(
        data.procedure_name, "El procedimiento", 180
    )
    weight = _validate_weight(data.weight_kg)
    surgery_id = surgery_repository.insert_surgery(
        conn,
        consultation_id=consultation.id,
        pet_id=consultation.pet_id,
        veterinarian_id=vet.id,
        procedure_name=name,
        scheduled_at=data.scheduled_at,
        weight_kg=weight,
        preoperative_notes=validators.validate_optional_text(
            data.preoperative_notes, "Las notas preoperatorias", 4000
        ),
    )
    _maybe_add_medication(conn, surgery_id, data)
    logger.info("Cirugía planificada: id=%s", surgery_id)
    return surgery_id


def _update_surgery(
    conn: oracledb.Connection, surgery_id: int, data: SurgeryFormData
) -> None:
    surgery = surgery_repository.get_by_id(conn, surgery_id)
    if surgery is None:
        raise ValidationError("El procedimiento quirúrgico no existe.")
    if surgery.status in {"COMPLETED", "CANCELLED"}:
        raise ValidationError("Este procedimiento ya no puede editarse.")
    _require_open_consultation(conn, surgery.consultation_id)
    surgery_repository.update_surgery(
        conn,
        surgery_id,
        procedure_name=validators.validate_required_text(
            data.procedure_name, "El procedimiento", 180
        ),
        scheduled_at=data.scheduled_at,
        weight_kg=_validate_weight(data.weight_kg),
        preoperative_notes=validators.validate_optional_text(
            data.preoperative_notes, "Las notas preoperatorias", 4000
        ),
        postoperative_notes=validators.validate_optional_text(
            data.postoperative_notes, "Las notas posteriores", 4000
        ),
        recovery_recommendations=validators.validate_optional_text(
            data.recovery_recommendations, "Las recomendaciones", 4000
        ),
    )
    _maybe_add_medication(conn, surgery_id, data)
    logger.info("Cirugía %s actualizada", surgery_id)


def _change_status(
    conn: oracledb.Connection, surgery_id: int, new_status: str
) -> None:
    surgery = surgery_repository.get_by_id(conn, surgery_id)
    if surgery is None:
        raise ValidationError("El procedimiento quirúrgico no existe.")
    _require_open_consultation(conn, surgery.consultation_id)
    allowed = _TRANSITIONS.get(surgery.status, set())
    if new_status not in allowed:
        raise ValidationError(
            f"No se puede pasar de {surgery.status} a {new_status}."
        )
    surgery_repository.set_status(conn, surgery_id, new_status)
    logger.info("Cirugía %s → %s", surgery_id, new_status)


def _require_open_consultation(conn, consultation_id: int | None):
    if consultation_id is None:
        raise ValidationError("La cirugía debe vincularse a una consulta.")
    consultation = consultation_repository.get_by_id(conn, consultation_id)
    if consultation is None:
        raise ValidationError("La consulta no existe.")
    if consultation.status == "SEALED":
        raise ValidationError(
            "La consulta está sellada; no se pueden alterar procedimientos."
        )
    return consultation


def _require_veterinarian(conn, veterinarian_id: int | None):
    if veterinarian_id is None:
        raise ValidationError("Seleccione el veterinario responsable.")
    vet = user_repository.get_by_id(conn, veterinarian_id)
    if vet is None or not vet.is_active or vet.role_name not in (
        "VETERINARIAN",
        "ADMIN",
    ):
        raise ValidationError("El veterinario seleccionado no es válido.")
    return vet


def _validate_weight(weight_kg: float | None) -> float | None:
    if weight_kg is None:
        return None
    if weight_kg <= 0:
        raise ValidationError("El peso debe ser mayor que cero.")
    return weight_kg


def _maybe_add_medication(
    conn: oracledb.Connection, surgery_id: int, data: SurgeryFormData
) -> None:
    if data.medication_id is None:
        return
    medication = medication_repository.get_medication(conn, data.medication_id)
    if medication is None:
        raise ValidationError("El medicamento quirúrgico no existe.")
    surgery_repository.insert_medication(
        conn,
        surgical_procedure_id=surgery_id,
        medication_id=medication.id,
        dose_text=validators.validate_optional_text(
            data.medication_dose_text, "La dosis", 150
        ),
        route=validators.validate_optional_text(
            data.medication_route or medication.default_route or "",
            "La vía",
            50,
        ),
        notes=None,
    )
