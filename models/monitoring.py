"""Modelos de monitoreo hospitalario, rangos vitales y alertas clínicas."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MonitoringRecord:
    id: int
    hospitalization_id: int
    recorded_by: int
    temperature_c: float | None
    heart_rate_bpm: int | None
    respiratory_rate_rpm: int | None
    oxygen_saturation_pct: float | None
    weight_kg: float | None
    pain_level: int | None
    feeding_status: str | None
    hydration_status: str | None
    observations: str | None
    recorded_at: datetime
    recorded_by_name: str | None = None


@dataclass(frozen=True)
class VitalRange:
    id: int
    species_id: int
    parameter_code: str
    min_value: float | None
    max_value: float | None
    unit: str | None
    description: str | None
    is_active: bool
    species_name: str | None = None


@dataclass(frozen=True)
class ClinicalAlert:
    id: int
    pet_id: int
    hospitalization_id: int | None
    monitoring_id: int | None
    alert_type: str
    severity: str  # LOW | MEDIUM | HIGH | CRITICAL
    message: str
    status: str  # OPEN | ACKNOWLEDGED | RESOLVED
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: int | None = None
    pet_name: str | None = None
    resolved_by_name: str | None = None
