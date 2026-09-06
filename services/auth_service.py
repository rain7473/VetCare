"""Service de autenticación de usuarios funcionales de VetCare.

Autentica contra la tabla USERS (bcrypt + is_active = 1). Nunca contra
cuentas Oracle: el usuario técnico VETCARE es solo la conexión.
"""

import logging

import oracledb

from database.connection import connection_scope
from models.user import User
from repositories import user_repository
from utils.security import verify_password

logger = logging.getLogger(__name__)

_GENERIC_MESSAGE = "Usuario o contraseña incorrectos."


class AuthenticationError(Exception):
    """Credenciales inválidas o usuario no autorizado; mensaje apto para UI."""


def authenticate(username: str, password: str) -> User:
    """Valida credenciales y devuelve el usuario autenticado.

    Actualiza LAST_LOGIN_AT en la misma transacción.

    Raises:
        AuthenticationError: credenciales inválidas o usuario desactivado.
        DatabaseConnectionError: si Oracle no está disponible.
    """
    with connection_scope(commit=True) as conn:
        return _authenticate(conn, username, password)


def _authenticate(conn: oracledb.Connection, username: str, password: str) -> User:
    """Lógica de autenticación sobre una conexión dada (testeable)."""
    normalized = username.strip().lower()
    if not normalized or not password:
        raise AuthenticationError("Ingrese usuario y contraseña.")

    result = user_repository.find_auth_by_username(conn, normalized)
    if result is None:
        logger.info("Login fallido: usuario inexistente (%s)", normalized)
        raise AuthenticationError(_GENERIC_MESSAGE)

    user, password_hash = result
    if not verify_password(password, password_hash):
        logger.info("Login fallido: contraseña incorrecta (%s)", normalized)
        raise AuthenticationError(_GENERIC_MESSAGE)

    if not user.is_active:
        logger.info("Login bloqueado: usuario desactivado (%s)", normalized)
        raise AuthenticationError(
            "El usuario está desactivado. Contacte al administrador."
        )

    user_repository.update_last_login(conn, user.id)
    logger.info("Login exitoso: %s (rol %s)", user.username, user.role_name)
    return user
