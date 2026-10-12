"""Consulta segura de la bitácora append-only de VetCare."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from database.connection import connection_scope
from models.audit import AuditEvent
from repositories import audit_repository
from services import permission_service
from utils.validators import ValidationError


AUDIT_PERMISSION = "SETTINGS_MANAGE"


@dataclass(frozen=True)
class AuditFilters:
    entity_type: str | None = None
    action: str | None = None
    user_id: int | None = None
    from_date: date | None = None
    to_date: date | None = None
    limit: int = 200


def list_events(filters: AuditFilters | None = None) -> list[AuditEvent]:
    permission_service.require_permission(AUDIT_PERMISSION)
    selected = filters or AuditFilters()
    if selected.from_date and selected.to_date and selected.from_date > selected.to_date:
        raise ValidationError("La fecha inicial no puede ser posterior a la final.")
    if not 1 <= selected.limit <= 500:
        raise ValidationError("El límite de auditoría debe estar entre 1 y 500.")
    from_at = (
        datetime.combine(selected.from_date, time.min) if selected.from_date else None
    )
    until_at = (
        datetime.combine(selected.to_date + timedelta(days=1), time.min)
        if selected.to_date else None
    )
    with connection_scope() as conn:
        return audit_repository.list_events(
            conn,
            entity_type=selected.entity_type,
            action=selected.action,
            user_id=selected.user_id,
            from_at=from_at,
            until_at=until_at,
            limit=selected.limit,
        )


def list_filter_options() -> tuple[list[str], list[str], list[tuple[int, str]]]:
    permission_service.require_permission(AUDIT_PERMISSION)
    with connection_scope() as conn:
        return audit_repository.list_filter_options(conn)

