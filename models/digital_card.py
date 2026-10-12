"""Modelo del carné digital de mascota (PET_DIGITAL_CARDS)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PetDigitalCard:
    id: int
    pet_id: int
    public_token_hex: str
    issued_at: datetime
    expires_at: datetime | None
    is_active: bool
    created_by: int | None
    pet_name: str | None = None
