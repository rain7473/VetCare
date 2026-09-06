"""Sesión actual de VetCare.

Mantiene el usuario funcional autenticado durante la vida de la
aplicación. Los services y vistas consultan aquí quién está conectado;
el Objetivo 6 añade el sistema centralizado de permisos sobre esta base.
"""

from models.user import User

_current_user: User | None = None


def set_current_user(user: User) -> None:
    global _current_user
    _current_user = user


def get_current_user() -> User | None:
    return _current_user


def clear() -> None:
    global _current_user
    _current_user = None
