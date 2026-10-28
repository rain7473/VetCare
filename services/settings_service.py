"""Configuración general autorizada y auditada."""
from database.connection import connection_scope
from repositories import settings_repository, audit_repository
from services import permission_service, session
from utils.validators import ValidationError

FIELDS = {"CLINIC_NAME": "Nombre de la clínica", "CLINIC_PHONE": "Teléfono",
          "CLINIC_EMAIL": "Correo electrónico", "CLINIC_ADDRESS": "Dirección"}


def load():
    permission_service.require_permission("SETTINGS_MANAGE")
    with connection_scope() as conn:
        return settings_repository.read_settings(conn)


def save(values):
    permission_service.require_permission("SETTINGS_MANAGE")
    if set(values) != set(FIELDS):
        raise ValidationError("Configuración no válida.")
    values = {k: v.strip() for k, v in values.items()}
    if not values["CLINIC_NAME"] or any(len(v) > 250 for v in values.values()):
        raise ValidationError("Indique el nombre y use como máximo 250 caracteres por campo.")
    email = values["CLINIC_EMAIL"]
    if email:
        import re
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValidationError("Correo electrónico inválido.")
    user = session.get_current_user()
    with connection_scope(commit=True) as conn:
        old = settings_repository.read_settings(conn)
        for key, value in values.items():
            settings_repository.set_setting(conn, key=key, value=value,
                                            updated_by=user.id, description=FIELDS[key])
        audit_repository.insert_event(conn, user_id=user.id, entity_type="SYSTEM_SETTINGS",
                                      entity_id=None, action="UPDATE",
                                      old_data={k: old.get(k) for k in FIELDS}, new_data=values)
