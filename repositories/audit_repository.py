"""Repository de AUDIT_LOG; los eventos son append-only."""

import json
from datetime import datetime
from typing import Any

import oracledb

from models.audit import AuditEvent


_AUDIT_SELECT = """
    SELECT a.id, a.user_id, a.entity_type, a.entity_id, a.action,
           a.old_data, a.new_data, a.ip_address, a.created_at,
           u.full_name, u.username
    FROM audit_log a
    LEFT JOIN users u ON u.id = a.user_id
"""


def list_events(
    conn: oracledb.Connection,
    *,
    entity_type: str | None = None,
    action: str | None = None,
    user_id: int | None = None,
    from_at: datetime | None = None,
    until_at: datetime | None = None,
    limit: int = 200,
) -> list[AuditEvent]:
    sql = _AUDIT_SELECT + " WHERE 1 = 1"
    params: dict[str, Any] = {"limit": limit}
    if entity_type:
        sql += " AND a.entity_type = :entity_type"
        params["entity_type"] = entity_type
    if action:
        sql += " AND a.action = :action"
        params["action"] = action
    if user_id is not None:
        sql += " AND a.user_id = :user_id"
        params["user_id"] = user_id
    if from_at is not None:
        sql += " AND a.created_at >= :from_at"
        params["from_at"] = from_at
    if until_at is not None:
        sql += " AND a.created_at < :until_at"
        params["until_at"] = until_at
    sql += " ORDER BY a.created_at DESC FETCH FIRST :limit ROWS ONLY"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_event(row) for row in cur.fetchall()]


def list_filter_options(
    conn: oracledb.Connection,
) -> tuple[list[str], list[str], list[tuple[int, str]]]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT entity_type FROM audit_log ORDER BY entity_type")
        entities = [row[0] for row in cur.fetchall()]
        cur.execute("SELECT DISTINCT action FROM audit_log ORDER BY action")
        actions = [row[0] for row in cur.fetchall()]
        cur.execute("""
            SELECT DISTINCT u.id, u.full_name
            FROM audit_log a JOIN users u ON u.id = a.user_id
            ORDER BY u.full_name
        """)
        users = [(int(row[0]), row[1]) for row in cur.fetchall()]
    return entities, actions, users


def insert_event(
    conn: oracledb.Connection,
    *,
    user_id: int | None,
    entity_type: str,
    entity_id: int | None,
    action: str,
    old_data: dict[str, Any] | None = None,
    new_data: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> int:
    """Agrega un evento a la bitácora. No hace COMMIT."""
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute("""
            INSERT INTO audit_log (
                user_id, entity_type, entity_id, action,
                old_data, new_data, ip_address, created_at
            ) VALUES (
                :user_id, :entity_type, :entity_id, :action,
                :old_data, :new_data, :ip_address, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
        """, {
            "user_id": user_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "old_data": _json(old_data),
            "new_data": _json(new_data),
            "ip_address": ip_address,
            "new_id": new_id,
        })
        raw = new_id.getvalue()
        return int(raw[0] if isinstance(raw, (list, tuple)) else raw)


def _json(value: dict[str, Any] | None) -> str | None:
    return json.dumps(value, ensure_ascii=False, default=str) if value is not None else None


def _row_to_event(row: tuple) -> AuditEvent:
    return AuditEvent(
        id=row[0],
        user_id=row[1],
        entity_type=row[2],
        entity_id=row[3],
        action=row[4],
        old_data=row[5],
        new_data=row[6],
        ip_address=row[7],
        created_at=row[8],
        user_name=row[9],
        username=row[10],
    )

