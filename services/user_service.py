"""Service de gestión de usuarios funcionales (módulo Usuarios).

Todas las operaciones exigen el permiso USERS_MANAGE y aplican reglas
de protección:

- Un usuario no puede desactivarse a sí mismo.
- La clínica nunca puede quedar sin un ADMIN activo (ni desactivando
  al último ni cambiándole el rol).
- El nombre de usuario es inmutable después de la creación.
"""

import logging
from dataclasses import dataclass

import oracledb

from database.connection import connection_scope
from models.user import User
from repositories import user_repository
from services import permission_service, session
from utils import validators
from utils.security import hash_password
from utils.validators import ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserFormData:
    """Datos del formulario de creación/edición de usuarios."""

    full_name: str
    username: str
    email: str
    phone: str
    role_id: int
    is_active: bool = True
    password: str = ""
    password_confirmation: str = ""


def list_users() -> list[User]:
    permission_service.require_permission("USERS_MANAGE")
    with connection_scope() as conn:
        return user_repository.list_users(conn)


def list_roles() -> list[tuple[int, str]]:
    permission_service.require_permission("USERS_MANAGE")
    from repositories import role_repository

    with connection_scope() as conn:
        return role_repository.list_roles(conn)


def create_user(data: UserFormData) -> int:
    permission_service.require_permission("USERS_MANAGE")
    with connection_scope(commit=True) as conn:
        return _create_user(conn, data)


def update_user(user_id: int, data: UserFormData) -> None:
    permission_service.require_permission("USERS_MANAGE")
    with connection_scope(commit=True) as conn:
        _update_user(conn, user_id, data)


def set_user_active(user_id: int, active: bool) -> None:
    permission_service.require_permission("USERS_MANAGE")
    with connection_scope(commit=True) as conn:
        _set_user_active(conn, user_id, active)


def reset_password(user_id: int, password: str, confirmation: str) -> None:
    permission_service.require_permission("USERS_MANAGE")
    validated = validators.validate_password(password, confirmation)
    with connection_scope(commit=True) as conn:
        if user_repository.get_by_id(conn, user_id) is None:
            raise ValidationError("El usuario no existe.")
        user_repository.update_password(conn, user_id, hash_password(validated))
        logger.info("Contraseña restablecida para el usuario %s", user_id)


# ------------------------------------------------------------------ interno
# Funciones sobre una conexión dada: testeables y transaccionales.


def _create_user(conn: oracledb.Connection, data: UserFormData) -> int:
    full_name = validators.validate_full_name(data.full_name)
    username = validators.validate_username(data.username)
    email = validators.validate_email_optional(data.email)
    phone = validators.validate_phone_optional(data.phone)
    password = validators.validate_password(data.password, data.password_confirmation)

    if user_repository.username_exists(conn, username):
        raise ValidationError("El nombre de usuario ya está en uso.")
    if email and user_repository.email_exists(conn, email):
        raise ValidationError("El correo electrónico ya está registrado.")

    user_id = user_repository.insert_user(
        conn,
        role_id=data.role_id,
        username=username,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        phone=phone,
        is_active=data.is_active,
    )
    logger.info("Usuario creado: %s (id=%s)", username, user_id)
    return user_id


def _update_user(conn: oracledb.Connection, user_id: int, data: UserFormData) -> None:
    existing = user_repository.get_by_id(conn, user_id)
    if existing is None:
        raise ValidationError("El usuario no existe.")

    full_name = validators.validate_full_name(data.full_name)
    email = validators.validate_email_optional(data.email)
    phone = validators.validate_phone_optional(data.phone)

    if email and user_repository.email_exists(conn, email, exclude_user_id=user_id):
        raise ValidationError("El correo electrónico ya está registrado.")

    _guard_last_active_admin(conn, existing, new_role_id=data.role_id,
                             new_active=data.is_active)
    _guard_self_deactivation(existing, data.is_active)

    user_repository.update_user(
        conn,
        user_id,
        role_id=data.role_id,
        email=email,
        full_name=full_name,
        phone=phone,
        is_active=data.is_active,
    )
    logger.info("Usuario actualizado: %s (id=%s)", existing.username, user_id)


def _set_user_active(conn: oracledb.Connection, user_id: int, active: bool) -> None:
    existing = user_repository.get_by_id(conn, user_id)
    if existing is None:
        raise ValidationError("El usuario no existe.")

    _guard_last_active_admin(conn, existing, new_role_id=existing.role_id,
                             new_active=active)
    _guard_self_deactivation(existing, active)

    user_repository.set_active(conn, user_id, active)
    logger.info(
        "Usuario %s: %s", "activado" if active else "desactivado", existing.username
    )


def _guard_self_deactivation(existing: User, new_active: bool) -> None:
    current = session.get_current_user()
    if current and current.id == existing.id and not new_active:
        raise ValidationError("No puede desactivar su propio usuario.")


def _guard_last_active_admin(
    conn: oracledb.Connection, existing: User, *, new_role_id: int, new_active: bool
) -> None:
    """Impide dejar la clínica sin ningún ADMIN activo."""
    was_active_admin = existing.role_name == "ADMIN" and existing.is_active
    if not was_active_admin:
        return
    remains_active_admin = new_active and new_role_id == existing.role_id
    if remains_active_admin:
        return
    if user_repository.count_active_admins(conn, exclude_user_id=existing.id) == 0:
        raise ValidationError(
            "No es posible: la clínica quedaría sin ningún administrador activo."
        )
