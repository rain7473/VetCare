"""Service del módulo de propietarios.

Lectura con OWNERS_READ; escritura con OWNERS_WRITE. Los propietarios
nunca se borran físicamente: se desactivan.
"""

import logging
from dataclasses import dataclass

import oracledb

from database.connection import connection_scope
from models.owner import Owner
from repositories import owner_repository
from services import permission_service
from utils import validators
from utils.validators import ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OwnerFormData:
    """Datos del formulario de propietario."""

    identification: str
    first_name: str
    last_name: str
    phone: str
    secondary_phone: str
    email: str
    address: str
    notes: str
    is_active: bool = True


def list_owners() -> list[Owner]:
    permission_service.require_permission("OWNERS_READ")
    with connection_scope() as conn:
        return owner_repository.list_owners(conn)


def create_owner(data: OwnerFormData) -> int:
    permission_service.require_permission("OWNERS_WRITE")
    with connection_scope(commit=True) as conn:
        return _create_owner(conn, data)


def update_owner(owner_id: int, data: OwnerFormData) -> None:
    permission_service.require_permission("OWNERS_WRITE")
    with connection_scope(commit=True) as conn:
        _update_owner(conn, owner_id, data)


def set_owner_active(owner_id: int, active: bool) -> None:
    permission_service.require_permission("OWNERS_WRITE")
    with connection_scope(commit=True) as conn:
        if owner_repository.get_by_id(conn, owner_id) is None:
            raise ValidationError("El propietario no existe.")
        owner_repository.set_active(conn, owner_id, active)
        logger.info(
            "Propietario %s: %s", owner_id, "activado" if active else "desactivado"
        )


# ------------------------------------------------------------------ interno


def _validate(conn: oracledb.Connection, data: OwnerFormData,
              exclude_owner_id: int | None = None) -> dict:
    fields = {
        "identification": validators.validate_optional_text(
            data.identification, "La identificación", 50
        ),
        "first_name": validators.validate_required_text(
            data.first_name, "El nombre", 100
        ),
        "last_name": validators.validate_required_text(
            data.last_name, "El apellido", 100
        ),
        "phone": validators.validate_phone_required(data.phone),
        "secondary_phone": validators.validate_phone_optional(data.secondary_phone),
        "email": validators.validate_email_optional(data.email),
        "address": validators.validate_optional_text(data.address, "La dirección", 4000),
        "notes": validators.validate_optional_text(data.notes, "Las notas", 4000),
    }
    if fields["identification"] and owner_repository.identification_exists(
        conn, fields["identification"], exclude_owner_id=exclude_owner_id
    ):
        raise ValidationError("Ya existe un propietario con esa identificación.")
    return fields


def _create_owner(conn: oracledb.Connection, data: OwnerFormData) -> int:
    fields = _validate(conn, data)
    owner_id = owner_repository.insert_owner(conn, **fields)
    logger.info("Propietario creado: %s (id=%s)", fields["first_name"], owner_id)
    return owner_id


def _update_owner(conn: oracledb.Connection, owner_id: int, data: OwnerFormData) -> None:
    if owner_repository.get_by_id(conn, owner_id) is None:
        raise ValidationError("El propietario no existe.")
    fields = _validate(conn, data, exclude_owner_id=owner_id)
    owner_repository.update_owner(conn, owner_id, is_active=data.is_active, **fields)
    logger.info("Propietario actualizado: id=%s", owner_id)
