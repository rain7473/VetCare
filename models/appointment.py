"""Modelo lógico de una cita (tabla APPOINTMENTS)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Appointment:
    id: int
    pet_id: int
    veterinarian_id: int | None
    created_by: int
    appointment_at: datetime
    reason: str
    status: str
    notes: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Solo lectura (JOIN)
    pet_name: str | None = None
    owner_name: str | None = None
    veterinarian_name: str | None = None
