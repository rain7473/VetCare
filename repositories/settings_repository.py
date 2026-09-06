"""Repository de la tabla SYSTEM_SETTINGS (almacén clave-valor).

La columna SETTING_VALUE tiene el constraint CHK_SETTING_JSON: debe
contener JSON válido. Por eso los valores se envuelven como objeto
``{"value": <dato>}`` al escribir y se desenvuelven al leer.
"""

import json

import oracledb

CLINIC_NAME_KEY = "CLINIC_NAME"


def _encode(value: str) -> str:
    return json.dumps({"value": value}, ensure_ascii=False)


def set_setting(
    conn: oracledb.Connection,
    *,
    key: str,
    value: str,
    updated_by: int | None,
    description: str | None = None,
) -> None:
    """Crea o actualiza una configuración. No hace COMMIT."""
    json_value = _encode(value)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM system_settings WHERE setting_key = :key",
            {"key": key},
        )
        exists = cur.fetchone()[0] > 0

        if exists:
            cur.execute(
                """
                UPDATE system_settings
                SET setting_value = :value,
                    updated_by = :updated_by,
                    updated_at = SYSTIMESTAMP
                WHERE setting_key = :key
                """,
                {"value": json_value, "updated_by": updated_by, "key": key},
            )
        else:
            cur.execute(
                """
                INSERT INTO system_settings (
                    setting_key, setting_value, description, updated_by, updated_at
                ) VALUES (
                    :key, :value, :description, :updated_by, SYSTIMESTAMP
                )
                """,
                {
                    "key": key,
                    "value": json_value,
                    "description": description,
                    "updated_by": updated_by,
                },
            )
