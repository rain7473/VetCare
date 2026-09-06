"""Pruebas del Objetivo 3: configuración inicial / primer ADMIN.

Parte 1 — Validaciones (sin base de datos).
Parte 2 — bcrypt (hash y verificación).
Parte 3 — Integración con Oracle usando INSERT + ROLLBACK: se ejecuta el
SQL real dentro de una transacción que NUNCA se confirma, así la base
queda exactamente igual que antes de la prueba.

    python -m tests.bootstrap_test
"""

import sys


def run() -> int:
    from repositories import role_repository, settings_repository, user_repository
    from services.bootstrap_service import FirstAdminData, create_first_admin
    from utils.security import hash_password, verify_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}

    # ---------------------------------------------- Parte 1: validaciones
    def expect_validation_error(name: str, data: FirstAdminData) -> None:
        try:
            create_first_admin(data)
            results[name] = False  # no lanzó error: mal
        except ValidationError:
            results[name] = True
        except Exception:
            results[name] = False

    base = dict(
        full_name="Laura Méndez",
        username="lmendez",
        email="laura@clinica.com",
        phone="",
        password="Segura123",
        password_confirmation="Segura123",
    )

    expect_validation_error(
        "Contraseña vacía rechazada",
        FirstAdminData(**{**base, "password": "", "password_confirmation": ""}),
    )
    expect_validation_error(
        "Confirmación incorrecta rechazada",
        FirstAdminData(**{**base, "password_confirmation": "Otra999x"}),
    )
    expect_validation_error(
        "Email inválido rechazado",
        FirstAdminData(**{**base, "email": "no-es-un-email"}),
    )
    expect_validation_error(
        "Nombre vacío rechazado",
        FirstAdminData(**{**base, "full_name": "   "}),
    )
    expect_validation_error(
        "Username inválido rechazado",
        FirstAdminData(**{**base, "username": "ab"}),
    )
    expect_validation_error(
        "Contraseña débil rechazada (sin número)",
        FirstAdminData(**{**base, "password": "SoloLetras", "password_confirmation": "SoloLetras"}),
    )

    # ---------------------------------------------------- Parte 2: bcrypt
    h = hash_password("Segura123")
    results["bcrypt genera hash no plano"] = h != "Segura123" and h.startswith("$2")
    results["bcrypt verifica contraseña correcta"] = verify_password("Segura123", h)
    results["bcrypt rechaza contraseña incorrecta"] = not verify_password("Mala456x", h)

    # ------------------------------- Parte 3: Oracle (INSERT + ROLLBACK)
    from database.connection import connection_scope

    initial_count = None
    try:
        with connection_scope() as conn:  # sin commit=True → ROLLBACK al salir
            initial_count = user_repository.count_users(conn)

            role_id = role_repository.get_role_id_by_name(conn, "ADMIN")
            results["Rol ADMIN existe en ROLES"] = role_id is not None

            new_id = user_repository.insert_user(
                conn,
                role_id=role_id,
                username="__test_admin__",
                email="__test__@vetcare.local",
                password_hash=h,
                full_name="Usuario De Prueba",
                phone=None,
            )
            results["INSERT USERS devuelve ID"] = new_id > 0
            results["Detección de usuario repetido"] = user_repository.username_exists(
                conn, "__TEST_ADMIN__"
            )
            results["Conteo dentro de la transacción"] = (
                user_repository.count_users(conn) == initial_count + 1
            )

            settings_repository.set_setting(
                conn,
                key="__TEST_SETTING__",
                value="valor de prueba",
                updated_by=new_id,
            )
            results["INSERT SYSTEM_SETTINGS funciona"] = True
            # Salida del scope sin commit → ROLLBACK automático.

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = (
                user_repository.count_users(conn) == initial_count
            )
    except Exception as exc:  # noqa: BLE001 - reportar cualquier fallo de integración
        print(f"ERROR en pruebas de integración: {exc}")
        results["Integración Oracle sin errores"] = False

    # ------------------------------------------------------------ Reporte
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
