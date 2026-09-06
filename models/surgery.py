"""Modelos del control quirúrgico (SURGICAL_PROCEDURES y SURGERY_MEDICATIONS)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SurgeryMedication:
    id: int
    surgical_procedure_id: int
    medication_id: int
    dose_text: str | None
    route: str | None
    notes: str | None
    medication_name: str | None = None


@dataclass(frozen=True)
class Surgery:
    id: int
    consultation_id: int
    pet_id: int
    veterinarian_id: int
    procedure_name: str
    scheduled_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    weight_kg: float | None
    preoperative_notes: str | None
    postoperative_notes: str | None
    recovery_recommendations: str | None
    status: str  # PLANNED | IN_PROGRESS | COMPLETED | CANCELLED
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pet_name: str | None = None
    veterinarian_name: str | None = None
