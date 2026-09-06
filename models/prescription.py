"""Modelo lógico de una prescripción (tabla PRESCRIPTIONS)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Prescription:
    id: int
    consultation_id: int
    medication_id: int
    prescribed_by: int
    weight_used_kg: float
    dose_per_kg: float | None
    dose_unit: str | None
    calculated_total_dose: float | None
    concentration_value: float | None
    concentration_unit: str | None
    calculated_volume: float | None
    volume_unit: str | None
    route: str | None
    frequency_text: str | None
    duration_days: int | None
    instructions: str | None
    created_at: datetime | None = None
    medication_name: str | None = None
    prescribed_by_name: str | None = None
