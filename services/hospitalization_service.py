"""Service de hospitalización.

Estados oficiales Oracle:
ADMITTED | OBSERVATION | CRITICAL | DISCHARGED | TRANSFERRED

Al ingresar se ocupa el espacio; al egresar o transferir se libera.
El monitoreo clínico detallado pertenece al Objetivo 16.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

import oracledb

from database.connection import connection_scope
from models.hospitalization import HospitalArea, HospitalSpace, Hospitalization
from models.pet import Pet
from models.user import User
from repositories import (
    consultation_repository,
    hospitalization_repository,
    pet_repository,
    user_repository,
)
from services import permission_service
from utils import validators
from utils.validators import ValidationError

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({"ADMITTED", "OBSERVATION", "CRITICAL"})
CLOSED_STATUSES = frozenset({"DISCHARGED", "TRANSFERRED"})

_TRANSITIONS = {
    "ADMITTED": {"OBSERVATION", "CRITICAL", "DISCHARGED", "TRANSFERRED"},
    "OBSERVATION": {"ADMITTED", "CRITICAL", "DISCHARGED", "TRANSFERRED"},
    "CRITICAL": {"OBSERVATION", "ADMITTED", "DISCHARGED", "TRANSFERRED"},
    "DISCHARGED": set(),
    "TRANSFERRED": set(),
}


@dataclass(frozen=True)
class AreaFormData:
    name: str
    description: str


@dataclass(frozen=True)
class SpaceFormData:
    area_id: int | None
    code: str
    description: str


@dataclass(frozen=True)
class HospitalizationFormData:
    pet_id: int | None
    veterinarian_id: int | None
    space_id: int | None
    consultation_id: int | None
    admitted_at: datetime
    reason: str
    treatment_plan: str
    status: str = "ADMITTED"


def list_active() -> list[Hospitalization]:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope() as conn:
        return hospitalization_repository.list_hospitalizations(conn, active_only=True)


def list_all() -> list[Hospitalization]:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope() as conn:
        return hospitalization_repository.list_hospitalizations(conn)


def list_areas() -> list[HospitalArea]:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope() as conn:
        return hospitalization_repository.list_areas(conn)


def list_spaces(only_available: bool = False) -> list[HospitalSpace]:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope() as conn:
        return hospitalization_repository.list_spaces(
            conn, only_available=only_available
        )


def list_active_pets() -> list[Pet]:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope() as conn:
        return [p for p in pet_repository.list_pets(conn) if p.status == "ACTIVE"]


def list_veterinarians() -> list[User]:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope() as conn:
        vets = user_repository.list_active_by_role(conn, "VETERINARIAN")
        admins = user_repository.list_active_by_role(conn, "ADMIN")
        seen = {u.id for u in vets}
        return vets + [a for a in admins if a.id not in seen]


def create_area(data: AreaFormData) -> int:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope(commit=True) as conn:
        return _create_area(conn, data)


def create_space(data: SpaceFormData) -> int:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope(commit=True) as conn:
        return _create_space(conn, data)


def admit(data: HospitalizationFormData) -> int:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope(commit=True) as conn:
        return _admit(conn, data)


def update_admissionization(hosp_id: int, data: HospitalizationFormData) -> None:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope(commit=True) as conn:
        _update(conn, hosp_id, data)


def change_status(
    hosp_id: int, new_status: str, discharge_notes: str = ""
) -> None:
    permission_service.require_permission("HOSPITAL_MANAGE")
    with connection_scope(commit=True) as conn:
        _change_status(conn, hosp_id, new_status, discharge_notes)


# ------------------------------------------------------------------ interno


def _create_area(conn: oracledb.Connection, data: AreaFormData) -> int:
    name = validators.validate_required_text(data.name, "El nombre del área", 100)
    return hospitalization_repository.insert_area(
        conn,
        name=name,
        description=validators.validate_optional_text(
            data.description, "La descripción", 4000
        ),
    )


def _create_space(conn: oracledb.Connection, data: SpaceFormData) -> int:
    if data.area_id is None:
        raise ValidationError("Seleccione el área del espacio.")
    code = validators.validate_required_text(data.code, "El código del espacio", 50)
    return hospitalization_repository.insert_space(
        conn,
        area_id=data.area_id,
        code=code,
        description=validators.validate_optional_text(
            data.description, "La descripción", 4000
        ),
    )


def _admit(conn: oracledb.Connection, data: HospitalizationFormData) -> int:
    if data.pet_id is None:
        raise ValidationError("Seleccione la mascota.")
    if pet_repository.get_by_id(conn, data.pet_id) is None:
        raise ValidationError("La mascota seleccionada no existe.")
    if hospitalization_repository.count_active_for_pet(conn, data.pet_id) > 0:
        raise ValidationError(
            "La mascota ya tiene una hospitalización activa."
        )

    vet = _require_vet(conn, data.veterinarian_id)
    reason = validators.validate_required_text(data.reason, "El motivo", 4000)
    status = data.status if data.status in ACTIVE_STATUSES else "ADMITTED"

    consultation_id = None
    if data.consultation_id is not None:
        consultation = consultation_repository.get_by_id(conn, data.consultation_id)
        if consultation is None or consultation.pet_id != data.pet_id:
            raise ValidationError("La consulta vinculada no corresponde a la mascota.")
        consultation_id = consultation.id

    space_id = _occupy_space(conn, data.space_id, previous_space_id=None)

    hosp_id = hospitalization_repository.insert_hospitalization(
        conn,
        pet_id=data.pet_id,
        consultation_id=consultation_id,
        veterinarian_id=vet.id,
        space_id=space_id,
        admitted_at=data.admitted_at,
        reason=reason,
        treatment_plan=validators.validate_optional_text(
            data.treatment_plan, "El plan de tratamiento", 4000
        ),
        status=status,
    )
    logger.info("Hospitalización creada: id=%s pet=%s", hosp_id, data.pet_id)
    return hosp_id


def _update(
    conn: oracledb.Connection, hosp_id: int, data: HospitalizationFormData
) -> None:
    current = hospitalization_repository.get_by_id(conn, hosp_id)
    if current is None:
        raise ValidationError("La hospitalización no existe.")
    if current.status in CLOSED_STATUSES:
        raise ValidationError("La hospitalización ya está cerrada.")

    vet = _require_vet(conn, data.veterinarian_id)
    space_id = _occupy_space(
        conn, data.space_id, previous_space_id=current.space_id
    )
    hospitalization_repository.update_hospitalization(
        conn,
        hosp_id,
        space_id=space_id,
        veterinarian_id=vet.id,
        reason=validators.validate_required_text(data.reason, "El motivo", 4000),
        treatment_plan=validators.validate_optional_text(
            data.treatment_plan, "El plan de tratamiento", 4000
        ),
    )


def _change_status(
    conn: oracledb.Connection,
    hosp_id: int,
    new_status: str,
    discharge_notes: str,
) -> None:
    current = hospitalization_repository.get_by_id(conn, hosp_id)
    if current is None:
        raise ValidationError("La hospitalización no existe.")
    allowed = _TRANSITIONS.get(current.status, set())
    if new_status not in allowed:
        raise ValidationError(
            f"No se puede pasar de {current.status} a {new_status}."
        )

    closing = new_status in CLOSED_STATUSES
    notes = None
    if closing:
        notes = validators.validate_optional_text(
            discharge_notes, "Las notas de egreso", 4000
        )

    hospitalization_repository.set_status(
        conn,
        hosp_id,
        status=new_status,
        discharge_notes=notes,
        mark_discharged=closing,
    )
    if closing and current.space_id is not None:
        hospitalization_repository.set_space_status(
            conn, current.space_id, "AVAILABLE"
        )
    logger.info("Hospitalización %s → %s", hosp_id, new_status)


def _require_vet(conn: oracledb.Connection, veterinarian_id: int | None) -> User:
    if veterinarian_id is None:
        raise ValidationError("Seleccione el veterinario responsable.")
    vet = user_repository.get_by_id(conn, veterinarian_id)
    if vet is None or not vet.is_active or vet.role_name not in (
        "VETERINARIAN",
        "ADMIN",
    ):
        raise ValidationError("El veterinario seleccionado no es válido.")
    return vet


def _occupy_space(
    conn: oracledb.Connection,
    space_id: int | None,
    previous_space_id: int | None,
) -> int | None:
    if space_id is None:
        if previous_space_id is not None:
            hospitalization_repository.set_space_status(
                conn, previous_space_id, "AVAILABLE"
            )
        return None

    space = hospitalization_repository.get_space(conn, space_id)
    if space is None or not space.is_active:
        raise ValidationError("El espacio seleccionado no existe.")

    if previous_space_id == space_id:
        return space_id

    if space.status != "AVAILABLE":
        raise ValidationError(
            f"El espacio {space.code} no está disponible ({space.status})."
        )

    if previous_space_id is not None:
        hospitalization_repository.set_space_status(
            conn, previous_space_id, "AVAILABLE"
        )
    hospitalization_repository.set_space_status(conn, space_id, "OCCUPIED")
    return space_id
