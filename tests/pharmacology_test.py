"""Pruebas del Objetivo 12: calculadora farmacológica.

Fórmulas, validaciones y persistencia de prescripciones con
INSERT + ROLLBACK. No se inventan dosis: deben venir de una guía.

    python -m tests.pharmacology_test
"""

import sys


def run() -> int:
    from database.connection import connection_scope
    from models.user import User
    from repositories import (
        consultation_repository,
        medication_repository,
        owner_repository,
        pet_repository,
        prescription_repository,
        role_repository,
        species_repository,
        user_repository,
    )
    from services import consultation_service, pharmacology_service, session
    from services.consultation_service import ConsultationFormData
    from services.pharmacology_service import PrescriptionFormData, calculate_dose
    from services.permission_service import PermissionDeniedError
    from utils.security import hash_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}

    # ------------------------------------------ fórmulas (lógica pura)
    calc = calculate_dose(
        weight_kg=10,
        dose_per_kg=2,
        concentration_value=5,
        concentration_unit="mg/mL",
        dose_unit="mg",
        frequency_text="cada 12 h",
        duration_days=5,
    )
    results["Dosis total = peso × dosis/kg"] = calc.calculated_total_dose == 20
    results["Volumen = dosis total / concentración"] = calc.calculated_volume == 4
    results["Unidad de volumen desde concentración"] = calc.volume_unit == "mL"

    try:
        calculate_dose(
            weight_kg=0,
            dose_per_kg=2,
            concentration_value=5,
            concentration_unit="mg/mL",
            dose_unit="mg",
        )
        results["Peso <= 0 rechazado"] = False
    except ValidationError:
        results["Peso <= 0 rechazado"] = True

    try:
        calculate_dose(
            weight_kg=10,
            dose_per_kg=-1,
            concentration_value=5,
            concentration_unit="mg/mL",
            dose_unit="mg",
        )
        results["Dosis negativa rechazada"] = False
    except ValidationError:
        results["Dosis negativa rechazada"] = True

    try:
        calculate_dose(
            weight_kg=10,
            dose_per_kg=2,
            concentration_value=0,
            concentration_unit="mg/mL",
            dose_unit="mg",
        )
        results["Concentración <= 0 rechazada"] = False
    except ValidationError:
        results["Concentración <= 0 rechazada"] = True

    solid = calculate_dose(
        weight_kg=8,
        dose_per_kg=5,
        concentration_value=None,
        concentration_unit=None,
        dose_unit="mg",
    )
    results["Sólido sin volumen"] = (
        solid.calculated_total_dose == 40 and solid.calculated_volume is None
    )

    try:
        session.set_current_user(
            User(
                id=995,
                role_id=1,
                username="fake_pharma",
                email=None,
                full_name="Fake Pharma",
                phone=None,
                is_active=True,
                role_name="TEST",
            ),
            frozenset(),
        )
        try:
            pharmacology_service.list_medications()
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        with connection_scope() as conn:
            owner_id = owner_repository.insert_owner(
                conn,
                identification=None,
                first_name="Farma",
                last_name="Prueba",
                phone="6000-0012",
                secondary_phone=None,
                email=None,
                address=None,
                notes=None,
            )
            species_id = species_repository.list_species(conn)[0][0]
            pet_id = pet_repository.insert_pet(
                conn,
                owner_id=owner_id,
                species_id=species_id,
                breed_id=None,
                name="FarmaPet",
                sex="MALE",
                birth_date=None,
                approximate_age_months=20,
                color=None,
                distinctive_features=None,
                microchip_number=None,
                photo_url=None,
                blood_type=None,
                allergies=None,
                chronic_conditions=None,
            )
            vet_role = role_repository.get_role_id_by_name(conn, "VETERINARIAN")
            vet_id = user_repository.insert_user(
                conn,
                role_id=vet_role,
                username="__test_vet12__",
                email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Vet Farma",
                phone=None,
            )
            session.set_current_user(
                User(
                    id=vet_id,
                    role_id=vet_role,
                    username="__test_vet12__",
                    email=None,
                    full_name="Vet Farma",
                    phone=None,
                    is_active=True,
                    role_name="VETERINARIAN",
                ),
                frozenset({"CONSULTATIONS_READ", "CONSULTATIONS_WRITE"}),
            )
            cid = consultation_service._create_consultation(
                conn,
                ConsultationFormData(
                    pet_id=pet_id,
                    veterinarian_id=vet_id,
                    appointment_id=None,
                    triage_id=None,
                    reason="Infección",
                    symptoms="",
                    observations="",
                ),
            )
            med_id = medication_repository.insert_medication(
                conn,
                name="Amoxicilina prueba",
                active_ingredient="Amoxicilina",
                presentation="Suspensión",
                concentration_value=50,
                concentration_unit="mg/mL",
                default_route="ORAL",
            )
            guide_id = medication_repository.insert_guideline(
                conn,
                medication_id=med_id,
                species_id=species_id,
                min_dose_per_kg=10,
                max_dose_per_kg=20,
                dose_unit="mg",
                frequency_text="cada 12 h",
            )

            def presc(**overrides) -> PrescriptionFormData:
                values = dict(
                    consultation_id=cid,
                    medication_id=med_id,
                    guideline_id=guide_id,
                    weight_kg=10,
                    dose_per_kg=15,
                    duration_days=7,
                    instructions="Con comida",
                )
                values.update(overrides)
                return PrescriptionFormData(**values)

            try:
                pharmacology_service._create_prescription(
                    conn, presc(dose_per_kg=30)
                )
                results["Dosis fuera de guía rechazada"] = False
            except ValidationError:
                results["Dosis fuera de guía rechazada"] = True

            med_sin_guia = medication_repository.insert_medication(
                conn,
                name="Sin guía",
                active_ingredient=None,
                presentation=None,
                concentration_value=None,
                concentration_unit=None,
                default_route=None,
            )
            try:
                pharmacology_service._create_prescription(
                    conn, presc(medication_id=med_sin_guia, guideline_id=None)
                )
                results["Sin guía rechazada"] = False
            except ValidationError:
                results["Sin guía rechazada"] = True

            pid = pharmacology_service._create_prescription(conn, presc())
            saved = prescription_repository.list_by_consultation(conn, cid)
            results["Prescripción persistida"] = (
                len(saved) == 1 and saved[0].id == pid
            )
            results["Cálculo persistido"] = (
                float(saved[0].calculated_total_dose) == 150
                and float(saved[0].calculated_volume) == 3
            )

            consultation_repository.finalize(conn, cid)
            try:
                pharmacology_service._create_prescription(conn, presc())
                results["No prescribir FINALIZED"] = False
            except ValidationError:
                results["No prescribir FINALIZED"] = True

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not (
                user_repository.username_exists(conn, "__test_vet12__")
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de farmacología: {exc}")
        results["Pruebas sin errores inesperados"] = False
    finally:
        session.clear()

    failures = [name for name, ok in results.items() if not ok]
    for name, ok in results.items():
        print(f"  [{'OK' if ok else 'FALLO'}] {name}")

    if failures:
        print(f"\nPruebas FALLIDAS: {len(failures)} de {len(results)}.")
        return 1

    print(f"\nTodas las pruebas superadas ({len(results)}).")
    return 0


if __name__ == "__main__":
    sys.exit(run())
