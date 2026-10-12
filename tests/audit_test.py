"""Pruebas del Objetivo 23: auditoría append-only (INSERT + ROLLBACK)."""

import os
import sys

import oracledb

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _user(user_id: int):
    from models.user import User

    return User(
        id=user_id,
        role_id=1,
        username="audit_test",
        email=None,
        full_name="Audit Test",
        phone=None,
        is_active=True,
        role_name="ADMIN",
    )


def run() -> int:
    from database.connection import connection_scope
    from main import create_app
    from repositories import audit_repository
    from services import audit_service, session
    from services.permission_service import PermissionDeniedError
    from views.audit.audit_page import AuditPage, _pretty_json

    results: dict[str, bool] = {}
    try:
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users ORDER BY id FETCH FIRST 1 ROW ONLY")
                row = cur.fetchone()
            if row is None:
                raise RuntimeError("Se requiere al menos un usuario para la prueba.")
            user_id = int(row[0])

            event_id = audit_repository.insert_event(
                conn,
                user_id=user_id,
                entity_type="TEST_ENTITY",
                entity_id=23001,
                action="TEST_ACTION",
                old_data={"status": "OLD"},
                new_data={"status": "NEW"},
            )
            events = audit_repository.list_events(
                conn, entity_type="TEST_ENTITY", action="TEST_ACTION", limit=10
            )
            results["Evento insertado y filtrado"] = (
                len(events) == 1 and events[0].id == event_id
            )
            results["JSON válido almacenado"] = (
                '"status": "NEW"' in _pretty_json(events[0].new_data)
            )
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE audit_log SET action = 'ALTERED' WHERE id = :id",
                        {"id": event_id},
                    )
                results["Trigger append-only bloquea UPDATE"] = False
            except oracledb.Error:
                results["Trigger append-only bloquea UPDATE"] = True

        session.set_current_user(_user(user_id), frozenset())
        try:
            audit_service.list_events()
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        session.set_current_user(_user(user_id), frozenset({"SETTINGS_MANAGE"}))
        results["Consulta autorizada funciona"] = isinstance(
            audit_service.list_events(audit_service.AuditFilters(limit=5)), list
        )

        app = create_app([])
        page = AuditPage()
        results["Página offscreen construida"] = (
            app is not None and page.table.model() is page.proxy
        )

        with connection_scope() as conn:
            events = audit_repository.list_events(
                conn, entity_type="TEST_ENTITY", action="TEST_ACTION", limit=10
            )
            results["ROLLBACK dejó la base intacta"] = not events
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de auditoría: {exc}")
        results["Pruebas sin errores inesperados"] = False
    finally:
        session.clear()

    failures = [name for name, ok in results.items() if not ok]
    for name, ok in results.items():
        print(f"  [{'OK' if ok else 'FALLO'}] {name}")
    if failures:
        print(f"\nPruebas FALLIDAS: {len(failures)} de {len(results)}.")
        return 1
    print(f"\nTodas las pruebas superadas ({len(results)}).")
    return 0


if __name__ == "__main__":
    sys.exit(run())

