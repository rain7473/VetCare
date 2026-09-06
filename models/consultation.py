"""Modelos lógicos del historial clínico (CONSULTATIONS y tablas hijas)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Consultation:
    id: int
    pet_id: int
    appointment_id: int | None
    triage_id: int | None
    veterinarian_id: int
    reason: str
    symptoms: str | None
    observations: str | None
    diagnosis_summary: str | None
    treatment_summary: str | None
    status: str  # DRAFT | FINALIZED | SEALED
    started_at: datetime
    ended_at: datetime | None
    sealed_at: datetime | None
    sealed_by: int | None
    sealed_hash: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Solo lectura (JOIN)
    pet_name: str | None = None
    owner_name: str | None = None
    veterinarian_name: str | None = None


@dataclass(frozen=True)
class ConsultationVital:
    id: int
    consultation_id: int
    recorded_by: int
    weight_kg: float | None
    temperature_c: float | None
    heart_rate_bpm: int | None
    respiratory_rate_rpm: int | None
    oxygen_saturation_pct: float | None
    pain_level: int | None
    notes: str | None
    recorded_at: datetime | None = None
    recorded_by_name: str | None = None


@dataclass(frozen=True)
class Diagnosis:
    id: int
    consultation_id: int
    diagnostic_code: str | None
    description: str
    is_primary: bool
    created_at: datetime | None = None
