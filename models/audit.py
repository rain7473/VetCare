"""Modelo lógico de un evento append-only de AUDIT_LOG."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AuditEvent:
    id: int
    user_id: int | None
    entity_type: str
    entity_id: int | None
    action: str
    old_data: str | None
    new_data: str | None
    ip_address: str | None
    created_at: datetime
    user_name: str | None = None
    username: str | None = None

