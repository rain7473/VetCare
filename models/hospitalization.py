"""Modelos de hospitalización (áreas, espacios e ingresos)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HospitalArea:
    id: int
    name: str
    description: str | None
    is_active: bool


@dataclass(frozen=True)
class HospitalSpace:
    id: int
    area_id: int
    code: str
    description: str | None
    status: str  # AVAILABLE | OCCUPIED | MAINTENANCE | INACTIVE
    is_active: bool
    area_name: str | None = None


@dataclass(frozen=True)
class Hospitalization:
    id: int
    pet_id: int
    consultation_id: int | None
    veterinarian_id: int
    space_id: int | None
    admitted_at: datetime
    discharged_at: datetime | None
    reason: str
    treatment_plan: str | None
    status: str  # ADMITTED | OBSERVATION | CRITICAL | DISCHARGED | TRANSFERRED
    discharge_notes: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pet_name: str | None = None
    owner_name: str | None = None
    veterinarian_name: str | None = None
    space_code: str | None = None
    area_name: str | None = None
