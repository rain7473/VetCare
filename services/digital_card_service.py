"""Service del carné digital / QR.

El QR contiene únicamente el token público (sin datos clínicos).
"""

import logging
from dataclasses import dataclass

from database.connection import connection_scope
from models.digital_card import PetDigitalCard
from models.pet import Pet
from models.vaccine import PetVaccination
from repositories import (
    digital_card_repository,
    pet_repository,
    vaccine_repository,
)
from services import permission_service, session
from utils.qr import card_payload
from utils.validators import ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DigitalCardView:
    pet: Pet
    card: PetDigitalCard
    qr_payload: str
    vaccines: list[PetVaccination]


def get_or_issue_card(pet_id: int) -> DigitalCardView:
    """Devuelve el carné activo o emite uno nuevo."""
    permission_service.require_permission("PETS_READ")
    with connection_scope(commit=True) as conn:
        pet = pet_repository.get_by_id(conn, pet_id)
        if pet is None:
            raise ValidationError("La mascota no existe.")

        card = digital_card_repository.get_active_for_pet(conn, pet_id)
        if card is None:
            current = session.get_current_user()
            card = digital_card_repository.insert_card(
                conn,
                pet_id=pet_id,
                created_by=current.id if current else None,
            )
            logger.info("Carné digital emitido: pet=%s card=%s", pet_id, card.id)

        vaccines = vaccine_repository.list_applications(conn, pet_id)[:8]
        return DigitalCardView(
            pet=pet,
            card=card,
            qr_payload=card_payload(card.public_token_hex),
            vaccines=vaccines,
        )


def reissue_card(pet_id: int) -> DigitalCardView:
    """Desactiva el carné actual y emite uno nuevo."""
    permission_service.require_permission("PETS_WRITE")
    with connection_scope(commit=True) as conn:
        pet = pet_repository.get_by_id(conn, pet_id)
        if pet is None:
            raise ValidationError("La mascota no existe.")
        digital_card_repository.deactivate_for_pet(conn, pet_id)
        current = session.get_current_user()
        card = digital_card_repository.insert_card(
            conn,
            pet_id=pet_id,
            created_by=current.id if current else None,
        )
        vaccines = vaccine_repository.list_applications(conn, pet_id)[:8]
        logger.info("Carné digital reemitido: pet=%s card=%s", pet_id, card.id)
        return DigitalCardView(
            pet=pet,
            card=card,
            qr_payload=card_payload(card.public_token_hex),
            vaccines=vaccines,
        )
