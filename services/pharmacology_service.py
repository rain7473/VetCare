"""Service de la calculadora farmacológica y prescripciones.

Las dosis no se inventan: deben provenir de una guía activa en
``MEDICATION_GUIDELINES``. Fórmulas:

    dosis total = peso × dosis por kg
    volumen    = dosis total / concentración   (si hay concentración)
"""

import logging
from dataclasses import dataclass

import oracledb

from database.connection import connection_scope
from models.medication import Medication, MedicationGuideline
from models.prescription import Prescription
from repositories import (
    consultation_repository,
    medication_repository,
    pet_repository,
    prescription_repository,
)
from services import permission_service, session
from utils import validators
from utils.validators import ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DoseCalculation:
    weight_used_kg: float
    dose_per_kg: float
    dose_unit: str
    calculated_total_dose: float
    concentration_value: float | None
    concentration_unit: str | None
    calculated_volume: float | None
    volume_unit: str | None
    frequency_text: str | None
    duration_days: int | None


@dataclass(frozen=True)
class PrescriptionFormData:
    consultation_id: int
    medication_id: int | None
    guideline_id: int | None
    weight_kg: float | None
    dose_per_kg: float | None
    duration_days: int | None
    instructions: str


def calculate_dose(
    *,
    weight_kg: float,
    dose_per_kg: float,
    concentration_value: float | None,
    concentration_unit: str | None,
    dose_unit: str,
    frequency_text: str | None = None,
    duration_days: int | None = None,
) -> DoseCalculation:
    """Calcula dosis total y volumen. No toca la base de datos."""
    if weight_kg is None or weight_kg <= 0:
        raise ValidationError("El peso debe ser mayor que cero.")
    if dose_per_kg is None or dose_per_kg < 0:
        raise ValidationError("La dosis por kg no puede ser negativa.")
    if concentration_value is not None and concentration_value <= 0:
        raise ValidationError("La concentración debe ser mayor que cero.")

    total = round(weight_kg * dose_per_kg, 4)
    volume = None
    volume_unit = None
    if concentration_value is not None:
        volume = round(total / concentration_value, 4)
        volume_unit = _volume_unit_from(concentration_unit)

    return DoseCalculation(
        weight_used_kg=weight_kg,
        dose_per_kg=dose_per_kg,
        dose_unit=dose_unit,
        calculated_total_dose=total,
        concentration_value=concentration_value,
        concentration_unit=concentration_unit,
        calculated_volume=volume,
        volume_unit=volume_unit,
        frequency_text=frequency_text,
        duration_days=duration_days,
    )


def list_medications() -> list[Medication]:
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        return medication_repository.list_active_medications(conn)


def list_guidelines(
    medication_id: int, species_id: int | None = None
) -> list[MedicationGuideline]:
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        return medication_repository.list_guidelines(conn, medication_id, species_id)


def list_prescriptions(consultation_id: int) -> list[Prescription]:
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        return prescription_repository.list_by_consultation(conn, consultation_id)


def last_weight_for_consultation(consultation_id: int) -> float | None:
    """Último peso registrado en los vitales de la consulta, si existe."""
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        vitals = consultation_repository.list_vitals(conn, consultation_id)
    for vital in reversed(vitals):
        if vital.weight_kg is not None:
            return float(vital.weight_kg)
    return None


def species_id_for_consultation(consultation_id: int) -> int | None:
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        consultation = consultation_repository.get_by_id(conn, consultation_id)
        if consultation is None:
            return None
        pet = pet_repository.get_by_id(conn, consultation.pet_id)
        return pet.species_id if pet else None


def create_prescription(data: PrescriptionFormData) -> int:
    permission_service.require_permission("CONSULTATIONS_WRITE")
    with connection_scope(commit=True) as conn:
        return _create_prescription(conn, data)


def _create_prescription(
    conn: oracledb.Connection, data: PrescriptionFormData
) -> int:
    current = session.get_current_user()
    if current is None:
        raise ValidationError("No hay una sesión activa.")

    consultation = consultation_repository.get_by_id(conn, data.consultation_id)
    if consultation is None:
        raise ValidationError("La consulta no existe.")
    if consultation.status != "DRAFT":
        raise ValidationError(
            "Solo se pueden agregar prescripciones a una consulta en borrador."
        )

    if data.medication_id is None:
        raise ValidationError("Seleccione un medicamento del catálogo.")
    medication = medication_repository.get_medication(conn, data.medication_id)
    if medication is None or not medication.is_active:
        raise ValidationError("El medicamento seleccionado no está disponible.")

    pet = pet_repository.get_by_id(conn, consultation.pet_id)
    species_id = pet.species_id if pet else None
    guidelines = medication_repository.list_guidelines(conn, medication.id, species_id)
    if not guidelines:
        raise ValidationError(
            "No hay una guía de dosificación configurada para este "
            "medicamento y especie. No se inventan dosis."
        )
    guideline = _pick_guideline(guidelines, data.guideline_id)
    _assert_dose_in_guideline(data.dose_per_kg, guideline)

    calculation = calculate_dose(
        weight_kg=data.weight_kg,
        dose_per_kg=data.dose_per_kg,
        concentration_value=(
            float(medication.concentration_value)
            if medication.concentration_value is not None
            else None
        ),
        concentration_unit=medication.concentration_unit,
        dose_unit=guideline.dose_unit,
        frequency_text=guideline.frequency_text,
        duration_days=data.duration_days,
    )
    if calculation.duration_days is not None and calculation.duration_days <= 0:
        raise ValidationError("La duración debe ser mayor que cero.")

    prescription_id = prescription_repository.insert_prescription(
        conn,
        consultation_id=consultation.id,
        medication_id=medication.id,
        prescribed_by=current.id,
        weight_used_kg=calculation.weight_used_kg,
        dose_per_kg=calculation.dose_per_kg,
        dose_unit=calculation.dose_unit,
        calculated_total_dose=calculation.calculated_total_dose,
        concentration_value=calculation.concentration_value,
        concentration_unit=calculation.concentration_unit,
        calculated_volume=calculation.calculated_volume,
        volume_unit=calculation.volume_unit,
        route=medication.default_route,
        frequency_text=calculation.frequency_text,
        duration_days=calculation.duration_days,
        instructions=validators.validate_optional_text(
            data.instructions, "Las instrucciones", 4000
        ),
    )
    logger.info(
        "Prescripción %s creada en consulta %s", prescription_id, consultation.id
    )
    return prescription_id


def _pick_guideline(
    guidelines: list[MedicationGuideline], guideline_id: int | None
) -> MedicationGuideline:
    if guideline_id is None:
        return guidelines[0]
    for guideline in guidelines:
        if guideline.id == guideline_id:
            return guideline
    raise ValidationError("La guía de dosificación seleccionada no es válida.")


def _assert_dose_in_guideline(
    dose_per_kg: float | None, guideline: MedicationGuideline
) -> None:
    if dose_per_kg is None:
        raise ValidationError("Indique la dosis por kg según la guía configurada.")
    minimum = guideline.min_dose_per_kg
    maximum = guideline.max_dose_per_kg
    if minimum is not None and dose_per_kg < float(minimum):
        raise ValidationError(
            f"La dosis está por debajo de la guía ({minimum} {guideline.dose_unit}/kg)."
        )
    if maximum is not None and dose_per_kg > float(maximum):
        raise ValidationError(
            f"La dosis supera la guía ({maximum} {guideline.dose_unit}/kg)."
        )


def _volume_unit_from(concentration_unit: str | None) -> str | None:
    """Si la concentración es 'mg/mL', el volumen se expresa en mL."""
    if not concentration_unit or "/" not in concentration_unit:
        return None
    return concentration_unit.split("/")[-1].strip() or None
