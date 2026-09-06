"""Modelos del catálogo y de la aplicación de vacunas."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Vaccine:
    id: int
    product_id: int | None
    name: str
    manufacturer: str | None
    description: str | None
    is_active: bool
    created_at: datetime | None = None


@dataclass(frozen=True)
class PetVaccination:
    id: int
    pet_id: int
    vaccine_id: int
    consultation_id: int | None
    inventory_lot_id: int | None
    applied_by: int
    applied_at: datetime
    lot_number: str | None
    expiry_date: date | None
    next_due_date: date | None
    notes: str | None
    created_at: datetime | None = None
    pet_name: str | None = None
    owner_name: str | None = None
    vaccine_name: str | None = None
    applied_by_name: str | None = None
