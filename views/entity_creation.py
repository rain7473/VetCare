"""Flujos UI reutilizables para creación encadenada de entidades."""

from PySide6.QtWidgets import QWidget

from database.connection import DatabaseConnectionError
from models.pet import Pet
from services import pet_service
from services import user_service
from services.permission_service import PermissionDeniedError
from views.pets.pet_dialog import PetDialog
from views.users.user_dialog import UserDialog


def create_pet_nested(parent: QWidget) -> Pet | None:
    """Abre Mascota; el propio diálogo permite crear Propietario en cadena."""
    owners = pet_service.list_active_owners()
    species = pet_service.list_species()
    dialog = PetDialog(owners, species, parent=parent)
    if not dialog.exec() or dialog.created_id is None:
        return None
    return pet_service.get_pet(dialog.created_id)


def create_veterinarian_nested(parent: QWidget):
    """Crea un usuario con VETERINARIAN preseleccionado y lo devuelve."""
    roles = user_service.list_roles()
    dialog = UserDialog(roles, parent=parent, preferred_role="VETERINARIAN")
    if not dialog.exec() or dialog.created_id is None:
        return None
    return user_service.get_user(dialog.created_id)


__all__ = [
    "create_pet_nested",
    "create_veterinarian_nested",
    "DatabaseConnectionError",
    "PermissionDeniedError",
]
