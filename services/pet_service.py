"""Service del módulo de mascotas.

Lectura con PETS_READ; escritura con PETS_WRITE. Las mascotas no se
borran: cambian de estado (ACTIVE / DECEASED / INACTIVE). Si la raza
escrita no existe para la especie, se crea en la misma transacción.
"""

import logging
from dataclasses import dataclass
from datetime import date

import oracledb

from database.connection import connection_scope
from models.owner import Owner
from models.pet import Pet
from repositories import owner_repository, pet_repository, species_repository
from services import permission_service
from utils import validators
from utils.images import save_pet_photo
from utils.validators import ValidationError

logger = logging.getLogger(__name__)

VALID_SEX = ("MALE", "FEMALE", "UNKNOWN")
VALID_STATUS = ("ACTIVE", "DECEASED", "INACTIVE")


@dataclass(frozen=True)
class PetFormData:
    """Datos del formulario de mascota."""

    owner_id: int | None
    species_id: int | None
    breed_name: str
    name: str
    sex: str
    birth_date: date | None
    approximate_age_months: int | None
    color: str
    distinctive_features: str
    microchip_number: str
    blood_type: str
    allergies: str
    chronic_conditions: str
    photo_source: str = ""  # ruta de archivo elegida por el usuario (opcional)
    status: str = "ACTIVE"


def list_pets() -> list[Pet]:
    permission_service.require_permission("PETS_READ")
    with connection_scope() as conn:
        return pet_repository.list_pets(conn)


def list_species() -> list[tuple[int, str]]:
    permission_service.require_permission("PETS_READ")
    with connection_scope() as conn:
        return species_repository.list_species(conn)


def list_breeds(species_id: int) -> list[tuple[int, str]]:
    permission_service.require_permission("PETS_READ")
    with connection_scope() as conn:
        return species_repository.list_breeds(conn, species_id)


def list_active_owners() -> list[Owner]:
    permission_service.require_permission("PETS_READ")
    with connection_scope() as conn:
        return [o for o in owner_repository.list_owners(conn) if o.is_active]


def create_pet(data: PetFormData) -> int:
    permission_service.require_permission("PETS_WRITE")
    with connection_scope(commit=True) as conn:
        return _create_pet(conn, data)


def update_pet(pet_id: int, data: PetFormData) -> None:
    permission_service.require_permission("PETS_WRITE")
    with connection_scope(commit=True) as conn:
        _update_pet(conn, pet_id, data)


def set_pet_status(pet_id: int, status: str) -> None:
    permission_service.require_permission("PETS_WRITE")
    if status not in VALID_STATUS:
        raise ValidationError("Estado de mascota no válido.")
    with connection_scope(commit=True) as conn:
        if pet_repository.get_by_id(conn, pet_id) is None:
            raise ValidationError("La mascota no existe.")
        pet_repository.set_status(conn, pet_id, status)
        logger.info("Mascota %s → estado %s", pet_id, status)


# ------------------------------------------------------------------ interno


def _validate(
    conn: oracledb.Connection, data: PetFormData, exclude_pet_id: int | None = None
) -> dict:
    if data.owner_id is None:
        raise ValidationError("Seleccione el propietario de la mascota.")
    if data.species_id is None:
        raise ValidationError("Seleccione la especie.")
    if data.sex not in VALID_SEX:
        raise ValidationError("Seleccione el sexo de la mascota.")

    owner = owner_repository.get_by_id(conn, data.owner_id)
    if owner is None:
        raise ValidationError("El propietario seleccionado no existe.")

    if data.birth_date and data.birth_date > date.today():
        raise ValidationError("La fecha de nacimiento no puede ser futura.")
    if data.approximate_age_months is not None and data.approximate_age_months < 0:
        raise ValidationError("La edad aproximada no puede ser negativa.")

    microchip = validators.validate_optional_text(
        data.microchip_number, "El microchip", 100
    )
    if microchip and pet_repository.microchip_exists(
        conn, microchip, exclude_pet_id=exclude_pet_id
    ):
        raise ValidationError("Ya existe una mascota con ese número de microchip.")

    breed_id = _resolve_breed(conn, data.species_id, data.breed_name)

    return {
        "owner_id": data.owner_id,
        "species_id": data.species_id,
        "breed_id": breed_id,
        "name": validators.validate_required_text(data.name, "El nombre", 100),
        "sex": data.sex,
        "birth_date": data.birth_date,
        "approximate_age_months": data.approximate_age_months,
        "color": validators.validate_optional_text(data.color, "El color", 100),
        "distinctive_features": validators.validate_optional_text(
            data.distinctive_features, "Las características", 4000
        ),
        "microchip_number": microchip,
        "blood_type": validators.validate_optional_text(
            data.blood_type, "El tipo de sangre", 30
        ),
        "allergies": validators.validate_optional_text(
            data.allergies, "Las alergias", 4000
        ),
        "chronic_conditions": validators.validate_optional_text(
            data.chronic_conditions, "Las condiciones crónicas", 4000
        ),
    }


def _resolve_breed(
    conn: oracledb.Connection, species_id: int, breed_name: str
) -> int | None:
    """Busca la raza por nombre; si no existe la crea (catálogo vivo)."""
    name = validators.validate_optional_text(breed_name, "La raza", 100)
    if name is None:
        return None
    breed_id = species_repository.find_breed_by_name(conn, species_id, name)
    if breed_id is None:
        breed_id = species_repository.insert_breed(conn, species_id, name)
        logger.info("Raza creada en catálogo: %s (id=%s)", name, breed_id)
    return breed_id


def _photo_field(data: PetFormData, key: str, current: str | None) -> str | None:
    if not data.photo_source:
        return current
    return save_pet_photo(data.photo_source, key)


def _create_pet(conn: oracledb.Connection, data: PetFormData) -> int:
    fields = _validate(conn, data)
    fields["photo_url"] = None
    pet_id = pet_repository.insert_pet(conn, **fields)
    if data.photo_source:
        photo = save_pet_photo(data.photo_source, f"pet_{pet_id}")
        pet_repository.update_pet(
            conn, pet_id, **{**fields, "photo_url": photo, "status": "ACTIVE"}
        )
    logger.info("Mascota creada: %s (id=%s)", fields["name"], pet_id)
    return pet_id


def _update_pet(conn: oracledb.Connection, pet_id: int, data: PetFormData) -> None:
    existing = pet_repository.get_by_id(conn, pet_id)
    if existing is None:
        raise ValidationError("La mascota no existe.")
    if data.status not in VALID_STATUS:
        raise ValidationError("Estado de mascota no válido.")

    fields = _validate(conn, data, exclude_pet_id=pet_id)
    fields["photo_url"] = _photo_field(data, f"pet_{pet_id}", existing.photo_url)
    fields["status"] = data.status
    pet_repository.update_pet(conn, pet_id, **fields)
    logger.info("Mascota actualizada: id=%s", pet_id)
