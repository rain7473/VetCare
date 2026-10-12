"""Datos de solo lectura del perfil de mascota, sujetos a permisos clínicos."""

from dataclasses import dataclass
from datetime import date

from database.connection import connection_scope
from models.consultation import Consultation
from models.vaccine import PetVaccination
from repositories import (
    consultation_repository,
    pet_profile_repository,
    vaccine_repository,
)
from services import permission_service


@dataclass(frozen=True)
class PetProfileData:
    consultations: tuple[Consultation, ...] = ()
    vaccinations: tuple[PetVaccination, ...] = ()
    latest_weight_kg: float | None = None
    clinical_allowed: bool = False
    vaccines_allowed: bool = False

    @property
    def next_vaccination(self) -> PetVaccination | None:
        # Una aplicación posterior del mismo tipo de vacuna reemplaza el
        # recordatorio de la aplicación anterior, incluso si no fijó fecha.
        latest_by_vaccine: dict[int, PetVaccination] = {}
        for application in sorted(
            self.vaccinations, key=lambda item: item.applied_at, reverse=True
        ):
            latest_by_vaccine.setdefault(application.vaccine_id, application)
        dated = [
            item for item in latest_by_vaccine.values()
            if item.next_due_date is not None
        ]
        if not dated:
            return None
        future = [v for v in dated if v.next_due_date >= date.today()]
        return min(future, key=lambda v: v.next_due_date) if future else max(
            dated, key=lambda v: v.next_due_date
        )


def load_profile(pet_id: int) -> PetProfileData:
    permission_service.require_permission("PETS_READ")
    clinical = permission_service.has_permission("CONSULTATIONS_READ")
    vaccines = permission_service.has_permission("VACCINES_MANAGE")
    with connection_scope() as conn:
        consultations = (
            tuple(consultation_repository.list_consultations(conn, pet_id))
            if clinical else ()
        )
        applications = (
            tuple(vaccine_repository.list_applications(conn, pet_id))
            if vaccines else ()
        )
        weight = pet_profile_repository.latest_weight(conn, pet_id) if clinical else None
    return PetProfileData(consultations, applications, weight, clinical, vaccines)
