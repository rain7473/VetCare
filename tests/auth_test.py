"""Pruebas del Objetivo 4: login y autenticación.

Usa INSERT + ROLLBACK: los usuarios de prueba se crean dentro de una
transacción que nunca se confirma, así la base queda intacta.

    python -m tests.auth_test
"""

import sys


def run() -> int:
    from database.connection import connection_scope
    from repositories import role_repository, user_repository
    from services.auth_service import AuthenticationError, _authenticate
    from utils.security import hash_password

    results: dict[str, bool] = {}

    def expect_auth_error(name: str, conn, username: str, password: str) -> None:
        try:
            _authenticate(conn, username, password)
            results[name] = False
        except AuthenticationError:
            results[name] = True

    try:
        with connection_scope() as conn:  # sin commit → ROLLBACK al salir
            role_id = role_repository.get_role_id_by_name(conn, "ADMIN")

            user_repository.insert_user(
                conn,
                role_id=role_id,
                username="__test_login__",
                email="__login__@vetcare.local",
                password_hash=hash_password("Prueba123"),
                full_name="Prueba Login",
                phone=None,
                is_active=True,
            )
            user_repository.insert_user(
                conn,
                role_id=role_id,
                username="__test_inactive__",
                email="__inactive__@vetcare.local",
                password_hash=hash_password("Prueba123"),
                full_name="Prueba Inactivo",
                phone=None,
                is_active=False,
            )

            user = _authenticate(conn, "__TEST_LOGIN__", "Prueba123")
            results["Login correcto devuelve usuario"] = user.username == "__test_login__"
            results["Usuario trae su rol"] = user.role_name == "ADMIN"

            refreshed = user_repository.find_auth_by_username(conn, "__test_login__")
            results["last_login_at actualizado"] = refreshed[0].last_login_at is not None

            expect_auth_error(
                "Contraseña incorrecta rechazada", conn, "__test_login__", "Mala456x"
            )
            expect_auth_error(
                "Usuario inexistente rechazado", conn, "__no_existe__", "Prueba123"
            )
            expect_auth_error(
                "Usuario desactivado bloqueado", conn, "__test_inactive__", "Prueba123"
            )
            expect_auth_error("Campos vacíos rechazados", conn, "", "")
            # Salida sin commit → ROLLBACK automático.

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not user_repository.username_exists(
                conn, "__test_login__"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de autenticación: {exc}")
        results["Pruebas sin errores inesperados"] = False

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
