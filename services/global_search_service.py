import unicodedata

from database.connection import connection_scope
from repositories import global_search_repository
from services import permission_service, session

REQUIRED = {"owners": "OWNERS_READ", "pets": "PETS_READ",
            "appointments": "APPOINTMENTS_MANAGE", "consultations": "CONSULTATIONS_READ"}


def search(user, text):
    if session.get_current_user() != user:
        return []
    text = "".join(
        char for char in unicodedata.normalize("NFD", text.strip().lower())
        if unicodedata.category(char) != "Mn"
    )
    if not 1 <= len(text) <= 100:
        return []
    modules = [k for k, p in REQUIRED.items() if permission_service.has_permission(p)]
    if not modules:
        return []
    with connection_scope() as conn:
        return global_search_repository.search(conn, text, modules)
