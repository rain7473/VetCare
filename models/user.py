"""Modelo lógico de un usuario funcional de VetCare (tabla USERS).

Representa a las personas que usan el sistema (administrador,
recepcionista, veterinario, ventas). No confundir con el usuario
técnico Oracle ``VETCARE`` que solo sirve para conectarse a la base.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class User:
    id: int
    role_id: int
    username: str
    email: str | None
    full_name: str
    phone: str | None
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    role_name: str | None = None
