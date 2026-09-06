"""Pruebas del Objetivo 6: usuarios, roles y permisos.

- Permisos reales por rol (solo lectura de Oracle).
- Guardas centralizadas con sesiones simuladas.
- Reglas de user_service con INSERT + ROLLBACK (no persiste nada).

    python -m tests.permissions_test
"""

import sys


def _fake_user(user_id: int, role_id: int, role_name: str, active: bool = True):
    from models.user import User

    return User(
        id=user_id,
        role_id=role_id,
        username=f"fake{user_id}",
        email=None,
        full_name=f"Fake {user_id}",
        phone=None,
        is_active=active,
        role_name=role_name,
    )


def run() -> int:
    from database.connection import connection_scope
    from repositories import permission_repository, role_repository, user_repository
    from services import permission_service, session, user_service
    from services.permission_service import PermissionDeniedError
    from services.user_service import UserFormData
    from utils.security import hash_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}

    try:
        # ------------------------- Parte 1: permisos reales desde Oracle
        with connection_scope() as conn:
            roles = dict(
                (name, rid) for rid, name in role_repository.list_roles(conn)
            )
            admin_codes = set(
                permission_repository.get_codes_for_role(conn, roles["ADMIN"])
            )
            reception_codes = set(
                permission_repository.get_codes_for_role(conn, roles["RECEPTION"])
            )
            sales_codes = set(
                permission_repository.get_codes_for_role(conn, roles["SALES"])
            )
            vet_codes = set(
                permission_repository.get_codes_for_role(conn, roles["VETERINARIAN"])
            )

        results["ADMIN tiene todos los permisos (20)"] = len(admin_codes) == 20
        results["RECEPTION sin USERS_MANAGE"] = "USERS_MANAGE" not in reception_codes
        results["SALES sin acceso clínico"] = "CONSULTATIONS_READ" not in sales_codes
        results["VETERINARIAN puede sellar consultas"] = "CONSULTATIONS_SEAL" in vet_codes

        # ------------------------- Parte 2: guardas con sesiones simuladas
        session.set_current_user(
            _fake_user(901, roles["SALES"], "SALES"), frozenset(sales_codes)
        )
        results["SALES no accede al módulo usuarios"] = (
            not permission_service.can_access_module("users")
        )
        results["SALES sí accede al módulo ventas"] = (
            permission_service.can_access_module("sales")
        )
        try:
            user_service.list_users()
            results["SALES bloqueado en user_service"] = False
        except PermissionDeniedError:
            results["SALES bloqueado en user_service"] = True

        results["SALES ve solo dashboard, inventario y ventas"] = (
            permission_service.accessible_modules()
            == {"dashboard", "inventory", "sales"}
        )

        session.set_current_user(
            _fake_user(902, roles["ADMIN"], "ADMIN"), frozenset(admin_codes)
        )
        results["ADMIN ve los 12 módulos"] = (
            len(permission_service.accessible_modules()) == 12
        )

        # ------------------- Parte 3: reglas de user_service (ROLLBACK)
        with connection_scope() as conn:  # sin commit → ROLLBACK al salir
            new_id = user_service._create_user(
                conn,
                UserFormData(
                    full_name="Recep Prueba",
                    username="__test_recep__",
                    email="",
                    phone="",
                    role_id=roles["RECEPTION"],
                    password="Prueba123",
                    password_confirmation="Prueba123",
                ),
            )
            results["Crear usuario con email vacío"] = new_id > 0

            try:
                user_service._create_user(
                    conn,
                    UserFormData(
                        full_name="Duplicado",
                        username="__TEST_RECEP__",
                        email="",
                        phone="",
                        role_id=roles["RECEPTION"],
                        password="Prueba123",
                        password_confirmation="Prueba123",
                    ),
                )
                results["Username duplicado rechazado"] = False
            except ValidationError:
                results["Username duplicado rechazado"] = True

            # Único ADMIN activo dentro de esta transacción:
            admin_id = user_repository.insert_user(
                conn,
                role_id=roles["ADMIN"],
                username="__test_admin6__",
                email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Admin Prueba",
                phone=None,
            )
            only_admin = user_repository.count_active_admins(conn) == 1

            if only_admin:
                try:
                    user_service._set_user_active(conn, admin_id, False)
                    results["Último ADMIN activo protegido"] = False
                except ValidationError:
                    results["Último ADMIN activo protegido"] = True
            else:
                results["Último ADMIN activo protegido (omitida: hay más admins)"] = True

            # Autodesactivación: sesión = usuario recién creado.
            session.set_current_user(
                _fake_user(new_id, roles["RECEPTION"], "RECEPTION"),
                frozenset(admin_codes),
            )
            try:
                user_service._set_user_active(conn, new_id, False)
                results["Autodesactivación rechazada"] = False
            except ValidationError:
                results["Autodesactivación rechazada"] = True

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = (
                not user_repository.username_exists(conn, "__test_recep__")
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de permisos: {exc}")
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
