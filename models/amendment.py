"""Modelo de corrección clínica (CLINICAL_AMENDMENTS)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ClinicalAmendment:
    id: int
    consultation_id: int
    created_by: int
    reason: str
    amendment_text: str
    amendment_hash: str | None
    created_at: datetime
    created_by_name: str | None = None
