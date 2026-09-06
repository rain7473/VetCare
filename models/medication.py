"""Modelos del catálogo farmacológico (MEDICATIONS y MEDICATION_GUIDELINES)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Medication:
    id: int
    product_id: int | None
    name: str
    active_ingredient: str | None
    presentation: str | None
    concentration_value: float | None
    concentration_unit: str | None
    default_route: str | None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class MedicationGuideline:
    id: int
    medication_id: int
    species_id: int | None
    min_dose_per_kg: float | None
    max_dose_per_kg: float | None
    dose_unit: str
    frequency_text: str | None
    notes: str | None
    approved_by: int | None
    is_active: bool
    species_name: str | None = None
