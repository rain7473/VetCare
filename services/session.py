"""Sesión actual de VetCare.

Mantiene el usuario funcional autenticado y sus permisos (cargados
desde Oracle al iniciar sesión) durante la vida de la aplicación.
"""

from models.user import User

_current_user: User | None = None
_permissions: frozenset[str] = frozenset()


def set_current_user(user: User, permissions: frozenset[str] = frozenset()) -> None:
    global _current_user, _permissions
    _current_user = user
    _permissions = permissions


def get_current_user() -> User | None:
    return _current_user


def get_permissions() -> frozenset[str]:
    return _permissions


def clear() -> None:
    global _current_user, _permissions
    _current_user = None
    _permissions = frozenset()
