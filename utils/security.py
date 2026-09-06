"""Utilidades de seguridad: hash y verificación de contraseñas con bcrypt.

Las contraseñas NUNCA se almacenan en texto plano; la tabla USERS guarda
únicamente ``password_hash`` generado aquí.
"""

import bcrypt

# bcrypt solo procesa los primeros 72 bytes de la contraseña.
BCRYPT_MAX_BYTES = 72


def hash_password(plain_password: str) -> str:
    """Genera un hash bcrypt (con salt aleatorio) listo para almacenar."""
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Comprueba una contraseña contra el hash almacenado."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        # Hash almacenado con formato inválido: nunca autenticar.
        return False
