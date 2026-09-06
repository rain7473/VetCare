"""Service de bootstrap: primer arranque de VetCare.

Decide si la aplicación debe mostrar la configuración inicial
(tabla USERS vacía) y crea el primer administrador de forma atómica.

Regla de seguridad: la comprobación cuenta TODOS los usuarios, no solo
los activos. Si existe al menos un usuario (aunque esté desactivado),
la configuración inicial queda bloqueada para siempre.
"""

import logging
from dataclasses import dataclass

from database.connection import connection_scope
from repositories import role_repository, settings_repository, user_repository
from utils import validators
from utils.security import hash_password
from utils.validators import ValidationError

logger = logging.getLogger(__name__)

ADMIN_ROLE_NAME = "ADMIN"


@dataclass(frozen=True)
class FirstAdminData:
    """Datos del formulario de configuración inicial."""

    full_name: str
    username: str
    email: str
    phone: str
    password: str
    password_confirmation: str
    clinic_name: str = ""


def users_exist() -> bool:
    """True si hay al menos un usuario registrado (activo o no)."""
    with connection_scope() as conn:
        return user_repository.count_users(conn) > 0


def create_first_admin(data: FirstAdminData) -> None:
    """Valida y crea el primer administrador (transacción atómica).

    Raises:
        ValidationError: datos inválidos o estado que impide la creación.
        DatabaseConnectionError: si Oracle no está disponible.
    """
    full_name = validators.validate_full_name(data.full_name)
    username = validators.validate_username(data.username)
    email = validators.validate_email(data.email)
    phone = validators.validate_phone_optional(data.phone)
    password = validators.validate_password(data.password, data.password_confirmation)
    clinic_name = validators.validate_clinic_name_optional(data.clinic_name)

    password_hash = hash_password(password)

    with connection_scope(commit=True) as conn:
        if user_repository.count_users(conn) > 0:
            raise ValidationError(
                "Ya existen usuarios registrados; la configuración inicial está bloqueada."
            )

        role_id = role_repository.get_role_id_by_name(conn, ADMIN_ROLE_NAME)
        if role_id is None:
            raise ValidationError(
                "No se encontró el rol ADMIN en la base de datos. "
                "Contacte al administrador de la base."
            )

        if user_repository.username_exists(conn, username):
            raise ValidationError("El nombre de usuario ya está en uso.")
        if user_repository.email_exists(conn, email):
            raise ValidationError("El correo electrónico ya está registrado.")

        admin_id = user_repository.insert_user(
            conn,
            role_id=role_id,
            username=username,
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            phone=phone,
            is_active=True,
        )

        if clinic_name:
            settings_repository.set_setting(
                conn,
                key=settings_repository.CLINIC_NAME_KEY,
                value=clinic_name,
                updated_by=admin_id,
                description="Nombre de la clínica veterinaria",
            )

        logger.info("Primer administrador creado (id=%s, username=%s)", admin_id, username)
