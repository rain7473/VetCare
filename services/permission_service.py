"""Sistema centralizado de permisos de VetCare.

Los permisos viven en Oracle (PERMISSIONS / ROLE_PERMISSIONS) y se
cargan una vez al iniciar sesión. Toda verificación de acceso pasa por
este módulo: las vistas ocultan lo no permitido y los services vuelven
a verificar (defensa en la lógica, no solo en la interfaz).
"""

import logging

from database.connection import connection_scope
from repositories import permission_repository
from services import session

logger = logging.getLogger(__name__)


class PermissionDeniedError(Exception):
    """El usuario actual no tiene el permiso requerido."""

    def __init__(self, code: str) -> None:
        super().__init__(
            "Permiso denegado: no tiene autorización para realizar esta acción."
        )
        self.code = code


# Módulo de la sidebar → códigos de permiso que dan acceso (basta uno).
# Dashboard es accesible para todos los usuarios autenticados.
MODULE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "dashboard": (),
    "owners": ("OWNERS_READ", "OWNERS_WRITE"),
    "pets": ("PETS_READ", "PETS_WRITE"),
    "appointments": ("APPOINTMENTS_MANAGE",),
    "triage": ("TRIAGE_CREATE",),
    "consultations": ("CONSULTATIONS_READ", "CONSULTATIONS_WRITE"),
    "vaccines": ("VACCINES_MANAGE",),
    "hospitalization": ("HOSPITAL_MANAGE",),
    "inventory": ("INVENTORY_READ", "INVENTORY_MANAGE"),
    "sales": ("SALES_READ", "SALES_CREATE"),
    "users": ("USERS_MANAGE",),
    "settings": ("SETTINGS_MANAGE",),
}


def load_role_permissions(role_id: int) -> frozenset[str]:
    """Carga desde Oracle los códigos de permiso de un rol."""
    with connection_scope() as conn:
        return frozenset(permission_repository.get_codes_for_role(conn, role_id))


def has_permission(code: str) -> bool:
    return code in session.get_permissions()


def has_any(codes: tuple[str, ...]) -> bool:
    """True si no se exige ningún permiso o el usuario tiene alguno."""
    return not codes or any(code in session.get_permissions() for code in codes)


def require_permission(code: str) -> None:
    """Verificación obligatoria en la capa de servicios.

    Raises:
        PermissionDeniedError: si el usuario actual no tiene el permiso.
    """
    if not has_permission(code):
        user = session.get_current_user()
        logger.warning(
            "Permiso denegado: %s requiere %s",
            user.username if user else "(sin sesión)",
            code,
        )
        raise PermissionDeniedError(code)


def can_access_module(key: str) -> bool:
    return has_any(MODULE_PERMISSIONS.get(key, ()))


def accessible_modules() -> set[str]:
    """Claves de módulos visibles para el usuario actual."""
    return {key for key in MODULE_PERMISSIONS if can_access_module(key)}
