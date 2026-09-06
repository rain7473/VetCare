"""Health check de la conexión a Oracle.

Verifica que la aplicación puede comunicarse con el esquema VETCARE:
usuario con el que se conecta y cantidad de tablas visibles. Solo
ejecuta lecturas; no modifica nada.
"""

from dataclasses import dataclass

from database.connection import build_dsn, connection_scope


@dataclass(frozen=True)
class HealthCheckResult:
    dsn: str
    connected_user: str
    table_count: int


def run_health_check() -> HealthCheckResult:
    """Conecta a Oracle y recopila los datos de verificación.

    Raises:
        DatabaseConnectionError: si la conexión no es posible.
    """
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT USER FROM dual")
            connected_user = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM user_tables")
            table_count = cur.fetchone()[0]

    return HealthCheckResult(
        dsn=build_dsn(),
        connected_user=connected_user,
        table_count=table_count,
    )
