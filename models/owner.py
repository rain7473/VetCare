"""Modelo lógico de un propietario de mascotas (tabla OWNERS)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Owner:
    id: int
    identification: str | None
    first_name: str
    last_name: str
    phone: str
    secondary_phone: str | None
    email: str | None
    address: str | None
    notes: str | None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
