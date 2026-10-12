"""Verificación general de integridad del esquema usado por VetCare (solo lectura)."""

import sys


REQUIRED_TABLES = {
    "APPOINTMENTS",
    "AUDIT_LOG",
    "CLINICAL_ALERTS",
    "CONSULTATIONS",
    "HOSPITALIZATIONS",
    "INVENTORY_LOTS",
    "PETS",
    "PRODUCTS",
    "SALES",
    "TRIAGES",
    "USERS",
}
OFFICIAL_ROLES = {"ADMIN", "RECEPTION", "VETERINARIAN", "SALES"}


def run() -> int:
    from database.connection import connection_scope

    results: dict[str, bool] = {}
    try:
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT USER FROM dual")
                results["Conexión usa esquema VETCARE"] = cur.fetchone()[0] == "VETCARE"

                cur.execute("SELECT table_name FROM user_tables")
                tables = {row[0] for row in cur.fetchall()}
                results["Tablas críticas disponibles"] = REQUIRED_TABLES <= tables

                cur.execute("SELECT name FROM roles")
                roles = {row[0] for row in cur.fetchall()}
                results["Roles oficiales disponibles"] = OFFICIAL_ROLES <= roles
                results["No existe rol OWNER"] = "OWNER" not in roles

                cur.execute("""
                    SELECT COUNT(*) FROM user_objects
                    WHERE status = 'INVALID'
                      AND object_type IN (
                          'FUNCTION', 'PROCEDURE', 'TRIGGER', 'VIEW', 'PACKAGE',
                          'PACKAGE BODY'
                      )
                """)
                results["Objetos Oracle relevantes válidos"] = cur.fetchone()[0] == 0

                cur.execute("""
                    SELECT COUNT(*) FROM user_triggers
                    WHERE trigger_name = 'TRG_AUDIT_APPEND_ONLY'
                      AND status = 'ENABLED'
                """)
                results["Auditoría append-only protegida"] = cur.fetchone()[0] == 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas generales: {exc}")
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

