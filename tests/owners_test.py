"""Pruebas del Objetivo 7: propietarios.

Validaciones + CRUD con INSERT + ROLLBACK (no persiste nada) +
verificación de permisos con sesiones simuladas.

    python -m tests.owners_test
"""

import sys


def _fake_session(codes: frozenset[str]) -> None:
    from models.user import User
    from services import session

    session.set_current_user(
        User(
            id=990,
            role_id=1,
            username="fake_owner_test",
            email=None,
            full_name="Fake Owners",
            phone=None,
            is_active=True,
            role_name="TEST",
        ),
        codes,
    )


def run() -> int:
    from database.connection import connection_scope
    from repositories import owner_repository
    from services import owner_service, session
    from services.owner_service import OwnerFormData
    from services.permission_service import PermissionDeniedError
    from utils.validators import ValidationError

    results: dict[str, bool] = {}

    base = dict(
        identification="__T-123__",
        first_name="Carlos",
        last_name="Vega",
        phone="6000-0000",
        secondary_phone="",
        email="",
        address="Calle 1",
        notes="",
    )

    try:
        # ----------------------------------------------------- permisos
        _fake_session(frozenset({"OWNERS_READ"}))
        try:
            owner_service.create_owner(OwnerFormData(**base))
            results["Sin OWNERS_WRITE no puede crear"] = False
        except PermissionDeniedError:
            results["Sin OWNERS_WRITE no puede crear"] = True

        _fake_session(frozenset({"OWNERS_READ", "OWNERS_WRITE"}))

        # -------------------------------------------------- validaciones
        def expect_error(name: str, conn, **overrides) -> None:
            try:
                owner_service._create_owner(
                    conn, OwnerFormData(**{**base, **overrides})
                )
                results[name] = False
            except ValidationError:
                results[name] = True

        with connection_scope() as conn:  # sin commit → ROLLBACK
            expect_error("Nombre vacío rechazado", conn, first_name=" ")
            expect_error("Apellido vacío rechazado", conn, last_name="")
            expect_error("Teléfono vacío rechazado", conn, phone="")
            expect_error("Email inválido rechazado", conn, email="no-es-email")

            owner_id = owner_service._create_owner(conn, OwnerFormData(**base))
            results["Crear propietario"] = owner_id > 0

            expect_error(
                "Identificación duplicada rechazada",
                conn,
                first_name="Otra",
                phone="6111-1111",
            )

            owner_service._update_owner(
                conn,
                owner_id,
                OwnerFormData(**{**base, "phone": "6999-9999", "notes": "VIP"}),
            )
            updated = owner_repository.get_by_id(conn, owner_id)
            results["Editar propietario"] = (
                updated.phone == "6999-9999" and updated.notes == "VIP"
            )

            owner_repository.set_active(conn, owner_id, False)
            results["Desactivar propietario"] = not owner_repository.get_by_id(
                conn, owner_id
            ).is_active
            # Salida sin commit → ROLLBACK automático.

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not (
                owner_repository.identification_exists(conn, "__T-123__")
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de propietarios: {exc}")
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
