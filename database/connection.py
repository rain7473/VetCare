"""Conexión centralizada a Oracle Database.

Única puerta de entrada a Oracle para toda la aplicación. Usa el modo
*thin* de python-oracledb (no requiere Oracle Client instalado) y las
credenciales definidas en ``.env`` (ver ``config/settings.py``).

Uso típico desde un repository:

    from database.connection import connection_scope

    with connection_scope() as conn:              # solo lectura
        with conn.cursor() as cur:
            cur.execute(sql, params)

    with connection_scope(commit=True) as conn:   # escritura atómica
        ...
"""

import logging
from contextlib import contextmanager
from typing import Any, Iterator

import oracledb

from config import settings

logger = logging.getLogger(__name__)

# Los CLOB/BLOB se devuelven como str/bytes directamente (sin objetos LOB),
# lo que simplifica el trabajo con columnas de texto largo (direcciones,
# notas, descripciones).
oracledb.defaults.fetch_lobs = False


class DatabaseConnectionError(Exception):
    """No fue posible conectar o comunicarse con Oracle.

    Contiene un mensaje apto para mostrar al usuario final; el detalle
    técnico queda registrado en el log.
    """


def build_dsn() -> str:
    """DSN en formato Easy Connect: host:puerto/servicio."""
    return f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_SERVICE}"


def get_connection() -> oracledb.Connection:
    """Abre una conexión nueva al esquema VETCARE.

    Raises:
        DatabaseConnectionError: si faltan credenciales o Oracle no responde.
    """
    if not settings.DB_PASSWORD:
        raise DatabaseConnectionError(
            "Falta la contraseña de la base de datos. "
            "Complete DB_PASSWORD en el archivo .env del proyecto."
        )
    try:
        return oracledb.connect(
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dsn=build_dsn(),
        )
    except oracledb.Error:
        logger.exception("Error al conectar con Oracle (dsn=%s)", build_dsn())
        raise DatabaseConnectionError(
            "No se pudo conectar a la base de datos. Verifique que Oracle "
            "esté en ejecución y que las credenciales de .env sean correctas."
        ) from None


@contextmanager
def connection_scope(commit: bool = False) -> Iterator[oracledb.Connection]:
    """Administra el ciclo completo de una conexión.

    - Abre la conexión.
    - Si ``commit=True`` y no hubo errores, hace COMMIT al salir.
    - Ante cualquier excepción hace ROLLBACK y la propaga.
    - Siempre cierra la conexión.
    """
    conn = get_connection()
    try:
        yield conn
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_one(sql: str, params: dict[str, Any] | None = None) -> tuple | None:
    """Ejecuta un SELECT parametrizado y devuelve la primera fila (o None)."""
    with connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            return cur.fetchone()
