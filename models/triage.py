"""Modelo lógico de un triaje (tabla TRIAGES, registro inmutable)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Triage:
    id: int
    pet_id: int
    appointment_id: int | None
    recorded_by: int
    reason: str
    consciousness_status: str | None
    respiratory_distress: bool
    active_bleeding: bool
    can_walk: bool | None
    seizures: bool
    pain_level: int | None
    temperature_c: float | None
    heart_rate_bpm: int | None
    respiratory_rate_rpm: int | None
    oxygen_saturation_pct: int | None
    priority_level: int
    priority_reason: str | None
    observations: str | None
    created_at: datetime | None = None
    # Solo lectura (JOIN)
    pet_name: str | None = None
    owner_name: str | None = None
    recorded_by_name: str | None = None
