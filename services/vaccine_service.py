"""Service de vacunas: catálogo, aplicación e historial.

No inventa calendarios veterinarios: la próxima fecha la indica el
usuario. Las alertas se calculan a partir de NEXT_DUE_DATE.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import oracledb

from database.connection import connection_scope
from models.pet import Pet
from models.vaccine import PetVaccination, Vaccine
from repositories import (
    consultation_repository,
    pet_repository,
    vaccine_repository,
)
from services import permission_service, session
from utils import validators
from utils.validators import ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VaccineCatalogData:
    name: str
    manufacturer: str
    description: str


@dataclass(frozen=True)
class VaccinationFormData:
    pet_id: int | None
    vaccine_id: int | None
    consultation_id: int | None
    applied_at: datetime
    lot_number: str
    expiry_date: date | None
    next_due_date: date | None
    notes: str


def list_catalog() -> list[Vaccine]:
    permission_service.require_permission("VACCINES_MANAGE")
    with connection_scope() as conn:
        return vaccine_repository.list_vaccines(conn)


def add_to_catalog(data: VaccineCatalogData) -> int:
    permission_service.require_permission("VACCINES_MANAGE")
    name = validators.validate_required_text(data.name, "El nombre de la vacuna", 150)
    with connection_scope(commit=True) as conn:
        return vaccine_repository.insert_vaccine(
            conn,
            name=name,
            manufacturer=validators.validate_optional_text(
                data.manufacturer, "El fabricante", 150
            ),
            description=validators.validate_optional_text(
                data.description, "La descripción", 4000
            ),
        )


def list_applications(pet_id: int | None = None) -> list[PetVaccination]:
    permission_service.require_permission("VACCINES_MANAGE")
    with connection_scope() as conn:
        return vaccine_repository.list_applications(conn, pet_id)


def list_due_alerts(days: int = 30) -> list[PetVaccination]:
    permission_service.require_permission("VACCINES_MANAGE")
    until = date.today() + timedelta(days=days)
    with connection_scope() as conn:
        return vaccine_repository.list_due_soon(conn, until)


def list_active_pets() -> list[Pet]:
    permission_service.require_permission("VACCINES_MANAGE")
    with connection_scope() as conn:
        return [p for p in pet_repository.list_pets(conn) if p.status == "ACTIVE"]


def apply_vaccination(data: VaccinationFormData) -> int:
    permission_service.require_permission("VACCINES_MANAGE")
    with connection_scope(commit=True) as conn:
        return _apply_vaccination(conn, data)


def _apply_vaccination(conn: oracledb.Connection, data: VaccinationFormData) -> int:
    current = session.get_current_user()
    if current is None:
        raise ValidationError("No hay una sesión activa.")
    if data.pet_id is None:
        raise ValidationError("Seleccione la mascota.")
    if pet_repository.get_by_id(conn, data.pet_id) is None:
        raise ValidationError("La mascota seleccionada no existe.")
    if data.vaccine_id is None:
        raise ValidationError("Seleccione una vacuna del catálogo.")

    consultation_id = None
    if data.consultation_id is not None:
        consultation = consultation_repository.get_by_id(conn, data.consultation_id)
        if consultation is None or consultation.pet_id != data.pet_id:
            raise ValidationError("La consulta vinculada no corresponde a la mascota.")
        if consultation.status == "SEALED":
            raise ValidationError(
                "No se puede vincular una vacuna a una consulta sellada."
            )
        consultation_id = consultation.id

    if data.expiry_date and data.expiry_date < data.applied_at.date():
        raise ValidationError("El lote está vencido en la fecha de aplicación.")
    if data.next_due_date and data.next_due_date < data.applied_at.date():
        raise ValidationError(
            "La próxima aplicación no puede ser anterior a la fecha de aplicación."
        )

    application_id = vaccine_repository.insert_application(
        conn,
        pet_id=data.pet_id,
        vaccine_id=data.vaccine_id,
        consultation_id=consultation_id,
        applied_by=current.id,
        applied_at=data.applied_at,
        lot_number=validators.validate_optional_text(
            data.lot_number, "El lote", 100
        ),
        expiry_date=data.expiry_date,
        next_due_date=data.next_due_date,
        notes=validators.validate_optional_text(data.notes, "Las notas", 4000),
    )
    logger.info("Vacuna aplicada: id=%s pet=%s", application_id, data.pet_id)
    return application_id


def _add_to_catalog(conn: oracledb.Connection, data: VaccineCatalogData) -> int:
    return vaccine_repository.insert_vaccine(
        conn,
        name=validators.validate_required_text(data.name, "El nombre de la vacuna", 150),
        manufacturer=validators.validate_optional_text(
            data.manufacturer, "El fabricante", 150
        ),
        description=validators.validate_optional_text(
            data.description, "La descripción", 4000
        ),
    )
