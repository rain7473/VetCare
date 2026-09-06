"""Validadores de datos de entrada de VetCare.

Cada validador lanza :class:`ValidationError` con un mensaje apto para
mostrar directamente al usuario. Los services son quienes invocan estas
validaciones antes de tocar la base de datos.
"""

import re

from utils.security import BCRYPT_MAX_BYTES

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{3,60}$")
_PHONE_RE = re.compile(r"^[0-9+\-() ]{6,30}$")


class ValidationError(Exception):
    """Dato de entrada inválido; el mensaje es apto para el usuario final."""


def validate_full_name(full_name: str) -> str:
    value = full_name.strip()
    if not value:
        raise ValidationError("El nombre completo es obligatorio.")
    if len(value) > 150:
        raise ValidationError("El nombre completo no puede superar 150 caracteres.")
    return value


def validate_username(username: str) -> str:
    value = username.strip().lower()
    if not value:
        raise ValidationError("El nombre de usuario es obligatorio.")
    if not _USERNAME_RE.match(value):
        raise ValidationError(
            "El nombre de usuario debe tener entre 3 y 60 caracteres "
            "(letras, números, punto, guion o guion bajo)."
        )
    return value


def validate_email(email: str) -> str:
    value = email.strip().lower()
    if not value:
        raise ValidationError("El correo electrónico es obligatorio.")
    if len(value) > 150 or not _EMAIL_RE.match(value):
        raise ValidationError("El correo electrónico no es válido.")
    return value


def validate_phone_optional(phone: str) -> str | None:
    value = phone.strip()
    if not value:
        return None
    if not _PHONE_RE.match(value):
        raise ValidationError(
            "El teléfono no es válido (use dígitos, espacios, +, -, paréntesis)."
        )
    return value


def validate_password(password: str, confirmation: str) -> str:
    if not password:
        raise ValidationError("La contraseña es obligatoria.")
    if len(password) < 8:
        raise ValidationError("La contraseña debe tener al menos 8 caracteres.")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValidationError("La contraseña es demasiado larga (máximo 72 bytes).")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValidationError("La contraseña debe incluir al menos una letra y un número.")
    if password != confirmation:
        raise ValidationError("La contraseña y su confirmación no coinciden.")
    return password


def validate_clinic_name_optional(clinic_name: str) -> str | None:
    value = clinic_name.strip()
    if not value:
        return None
    if len(value) > 150:
        raise ValidationError("El nombre de la clínica no puede superar 150 caracteres.")
    return value
