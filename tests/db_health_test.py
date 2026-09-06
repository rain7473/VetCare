"""Prueba de integración del Objetivo 2: conexión Python → Oracle.

Solo ejecuta lecturas (dual y user_tables). Requiere que .env tenga
DB_PASSWORD configurado y que Oracle XE esté en ejecución.

    python -m tests.db_health_test
"""

import sys


def run() -> int:
    from database.connection import DatabaseConnectionError
    from database.health_check import run_health_check

    try:
        result = run_health_check()
    except DatabaseConnectionError as exc:
        print(f"FALLO DE CONEXION: {exc}")
        return 1

    print(f"DSN: {result.dsn}")
    print(f"Usuario conectado: {result.connected_user}")
    print(f"Tablas en el esquema: {result.table_count}")
    print()

    checks = {
        "SELECT USER FROM dual devuelve VETCARE": result.connected_user == "VETCARE",
        "El esquema contiene tablas (esperado: ~38)": result.table_count > 0,
    }

    failures = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  [{'OK' if ok else 'FALLO'}] {name}")

    if failures:
        print(f"\nPrueba FALLIDA: {len(failures)} comprobación(es) fallaron.")
        return 1

    print("\nPrueba superada: Python se comunica correctamente con Oracle.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
