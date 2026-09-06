"""Pruebas del Objetivo 11: consultas e historial clínico.

Validaciones, ciclo DRAFT → FINALIZED → SEALED, vitales, diagnósticos
y funciones Oracle de sellado. Todo con INSERT + ROLLBACK.

    python -m tests.consultations_test
"""

import sys


def run() -> int:
    from database.connection import connection_scope
    from models.user import User
    from repositories import (
        appointment_repository,
        consultation_repository,
        owner_repository,
        pet_repository,
        role_repository,
        species_repository,
        user_repository,
    )
    from services import consultation_service, session
    from services.consultation_service import ConsultationFormData, VitalsFormData
    from services.permission_service import PermissionDeniedError
    from utils.security import hash_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}

    def form(default_pet_id, default_vet_id, **overrides) -> ConsultationFormData:
        values = dict(
            pet_id=default_pet_id,
            veterinarian_id=default_vet_id,
            appointment_id=None,
            triage_id=None,
            reason="Cojera en pata delantera",
            symptoms="Cojea al caminar",
            observations="Sin fiebre aparente",
        )
        values.update(overrides)
        return ConsultationFormData(**values)

    try:
        session.set_current_user(
            User(
                id=994,
                role_id=1,
                username="fake_consult",
                email=None,
                full_name="Fake Consult",
                phone=None,
                is_active=True,
                role_name="TEST",
            ),
            frozenset(),
        )
        try:
            consultation_service.list_consultations()
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        with connection_scope() as conn:  # sin commit → ROLLBACK
            owner_id = owner_repository.insert_owner(
                conn,
                identification=None,
                first_name="Consulta",
                last_name="Prueba",
                phone="6000-0011",
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
                name="ConsultaPet",
                sex="FEMALE",
                birth_date=None,
                approximate_age_months=36,
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
                username="__test_vet11__",
                email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Vet Consulta",
                phone=None,
            )
            session.set_current_user(
                User(
                    id=vet_id,
                    role_id=vet_role,
                    username="__test_vet11__",
                    email=None,
                    full_name="Vet Consulta",
                    phone=None,
                    is_active=True,
                    role_name="VETERINARIAN",
                ),
                frozenset(
                    {
                        "CONSULTATIONS_READ",
                        "CONSULTATIONS_WRITE",
                        "CONSULTATIONS_SEAL",
                    }
                ),
            )

            def expect_error(check_name: str, **overrides) -> None:
                try:
                    consultation_service._create_consultation(
                        conn, form(pet_id, vet_id, **overrides)
                    )
                    results[check_name] = False
                except ValidationError:
                    results[check_name] = True

            expect_error("Motivo vacío rechazado", reason=" ")
            expect_error("Mascota inexistente rechazada", pet_id=999999)

            cid = consultation_service._create_consultation(conn, form(pet_id, vet_id))
            created = consultation_repository.get_by_id(conn, cid)
            results["Crear consulta en DRAFT"] = (
                created is not None and created.status == "DRAFT"
            )

            try:
                consultation_service._add_vitals(
                    conn,
                    cid,
                    VitalsFormData(
                        weight_kg=0,
                        temperature_c=None,
                        heart_rate_bpm=None,
                        respiratory_rate_rpm=None,
                        oxygen_saturation_pct=None,
                        pain_level=None,
                        notes="",
                    ),
                )
                results["Peso inválido rechazado"] = False
            except ValidationError:
                results["Peso inválido rechazado"] = True

            consultation_service._add_vitals(
                conn,
                cid,
                VitalsFormData(
                    weight_kg=12.5,
                    temperature_c=38.4,
                    heart_rate_bpm=110,
                    respiratory_rate_rpm=28,
                    oxygen_saturation_pct=98,
                    pain_level=3,
                    notes="Estable",
                ),
            )
            vitals = consultation_repository.list_vitals(conn, cid)
            results["Registrar signos vitales"] = (
                len(vitals) == 1 and float(vitals[0].weight_kg) == 12.5
            )

            try:
                consultation_service._add_diagnosis(
                    conn, cid, diagnostic_code="", description=" ", is_primary=True
                )
                results["Diagnóstico vacío rechazado"] = False
            except ValidationError:
                results["Diagnóstico vacío rechazado"] = True

            consultation_service._add_diagnosis(
                conn,
                cid,
                diagnostic_code="DX-1",
                description="Otitis externa",
                is_primary=True,
            )
            diagnoses = consultation_repository.list_diagnoses(conn, cid)
            results["Registrar diagnóstico principal"] = (
                len(diagnoses) == 1 and diagnoses[0].is_primary
            )

            consultation_service._update_content(
                conn,
                cid,
                ConsultationFormData(
                    pet_id=pet_id,
                    veterinarian_id=vet_id,
                    appointment_id=None,
                    triage_id=None,
                    reason="Cojera en pata delantera",
                    symptoms="Cojea al caminar",
                    observations="Sin fiebre aparente",
                    diagnosis_summary="Otitis",
                    treatment_summary="Limpieza ótica",
                ),
            )
            updated = consultation_repository.get_by_id(conn, cid)
            results["Guardar borrador"] = (updated.diagnosis_summary or "").find(
                "Otitis"
            ) >= 0

            consultation_service._finalize(conn, cid)
            finalized = consultation_repository.get_by_id(conn, cid)
            results["Finalizar consulta"] = finalized.status == "FINALIZED"

            try:
                consultation_service._update_content(
                    conn, cid, form(pet_id, vet_id, reason="No debería")
                )
                results["No editar FINALIZED"] = False
            except ValidationError:
                results["No editar FINALIZED"] = True

            sealed_hash = consultation_repository.seal(conn, cid, vet_id)
            sealed = consultation_repository.get_by_id(conn, cid)
            results["Sellar consulta"] = (
                sealed.status == "SEALED"
                and isinstance(sealed_hash, str)
                and len(sealed_hash) == 64
            )
            results["Verificar integridad"] = consultation_repository.verify_hash(
                conn, cid
            )

            try:
                consultation_service._add_vitals(
                    conn,
                    cid,
                    VitalsFormData(
                        weight_kg=13.0,
                        temperature_c=None,
                        heart_rate_bpm=None,
                        respiratory_rate_rpm=None,
                        oxygen_saturation_pct=None,
                        pain_level=None,
                        notes="",
                    ),
                )
                results["No alterar consulta sellada"] = False
            except ValidationError:
                results["No alterar consulta sellada"] = True

            listed = consultation_repository.list_consultations(conn, pet_id)
            results["Historial cronológico"] = (
                len(listed) == 1 and listed[0].id == cid
            )

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not (
                user_repository.username_exists(conn, "__test_vet11__")
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de consultas: {exc}")
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
