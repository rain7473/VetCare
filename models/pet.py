"""Modelo lógico de una mascota (tabla PETS).

Incluye campos denormalizados de solo lectura (nombre del propietario,
especie y raza) para presentación, obtenidos por JOIN en el repository.
"""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Pet:
    id: int
    owner_id: int
    species_id: int
    breed_id: int | None
    name: str
    sex: str  # MALE | FEMALE | UNKNOWN
    birth_date: date | None
    approximate_age_months: int | None
    color: str | None
    distinctive_features: str | None
    microchip_number: str | None
    photo_url: str | None
    blood_type: str | None
    allergies: str | None
    chronic_conditions: str | None
    status: str  # ACTIVE | DECEASED | INACTIVE
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Solo lectura (JOIN)
    owner_name: str | None = None
    species_name: str | None = None
    breed_name: str | None = None

    def age_text(self, today: date | None = None) -> str:
        """Edad legible a partir de la fecha de nacimiento o edad aproximada."""
        today = today or date.today()
        months: int | None = None
        if self.birth_date:
            born = (
                self.birth_date.date()
                if isinstance(self.birth_date, datetime)
                else self.birth_date
            )
            months = (today.year - born.year) * 12 + (today.month - born.month)
            if today.day < born.day:
                months -= 1
        elif self.approximate_age_months is not None:
            months = self.approximate_age_months

        if months is None or months < 0:
            return "—"
        years, rem = divmod(months, 12)
        if years and rem:
            return f"{years} a {rem} m"
        if years:
            return f"{years} año{'s' if years != 1 else ''}"
        return f"{rem} mes{'es' if rem != 1 else ''}"
