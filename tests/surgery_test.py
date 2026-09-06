"""Pruebas del Objetivo 13: control quirúrgico.

Validaciones, máquina de estados y medicamento asociado, con
INSERT + ROLLBACK.

    python -m tests.surgery_test
"""

import sys
from datetime import datetime, timedelta


def run() -> int:
    from database.connection import connection_scope
    from models.user import User
    from repositories import (
        medication_repository,
        owner_repository,
        pet_repository,
        role_repository,
        species_repository,
        surgery_repository,
        user_repository,
    )
    from services import consultation_service, session, surgery_service
    from services.consultation_service import ConsultationFormData
    from services.permission_service import PermissionDeniedError
    from services.surgery_service import SurgeryFormData
    from utils.security import hash_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}
    when = datetime.now() + timedelta(hours=2)

    def form(consultation_id, vet_id, **overrides) -> SurgeryFormData:
        values = dict(
            consultation_id=consultation_id,
            veterinarian_id=vet_id,
            procedure_name="Ovariohisterectomía",
            scheduled_at=when,
            weight_kg=8.5,
            preoperative_notes="Ayuno 8 h",
        )
        values.update(overrides)
        return SurgeryFormData(**values)

    try:
        session.set_current_user(
            User(
                id=996,
                role_id=1,
                username="fake_surg",
                email=None,
                full_name="Fake Surg",
                phone=None,
                is_active=True,
                role_name="TEST",
            ),
            frozenset(),
        )
        try:
            surgery_service.list_surgeries(1)
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        with connection_scope() as conn:
            owner_id = owner_repository.insert_owner(
                conn,
                identification=None,
                first_name="Cirugia",
                last_name="Prueba",
                phone="6000-0013",
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
                name="SurgPet",
                sex="FEMALE",
                birth_date=None,
                approximate_age_months=18,
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
                username="__test_vet13__",
                email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Vet Cirugia",
                phone=None,
            )
            session.set_current_user(
                User(
                    id=vet_id,
                    role_id=vet_role,
                    username="__test_vet13__",
                    email=None,
                    full_name="Vet Cirugia",
                    phone=None,
                    is_active=True,
                    role_name="VETERINARIAN",
                ),
                frozenset(
                    {
                        "CONSULTATIONS_READ",
                        "CONSULTATIONS_WRITE",
                        "SURGERY_MANAGE",
                    }
                ),
            )
            cid = consultation_service._create_consultation(
                conn,
                ConsultationFormData(
                    pet_id=pet_id,
                    veterinarian_id=vet_id,
                    appointment_id=None,
                    triage_id=None,
                    reason="Esterilización",
                    symptoms="",
                    observations="",
                ),
            )
            med_id = medication_repository.insert_medication(
                conn,
                name="Meloxicam prueba",
                active_ingredient="Meloxicam",
                presentation=None,
                concentration_value=None,
                concentration_unit=None,
                default_route="SC",
            )

            try:
                surgery_service._create_surgery(
                    conn, form(cid, vet_id, procedure_name=" ")
                )
                results["Procedimiento vacío rechazado"] = False
            except ValidationError:
                results["Procedimiento vacío rechazado"] = True

            try:
                surgery_service._create_surgery(
                    conn, form(cid, vet_id, weight_kg=0)
                )
                results["Peso inválido rechazado"] = False
            except ValidationError:
                results["Peso inválido rechazado"] = True

            sid = surgery_service._create_surgery(
                conn,
                form(
                    cid,
                    vet_id,
                    medication_id=med_id,
                    medication_dose_text="0.2 mg/kg",
                    medication_route="SC",
                ),
            )
            created = surgery_repository.get_by_id(conn, sid)
            results["Crear cirugía PLANNED"] = (
                created is not None and created.status == "PLANNED"
            )
            meds = surgery_repository.list_medications(conn, sid)
            results["Medicamento quirúrgico asociado"] = (
                len(meds) == 1 and meds[0].medication_id == med_id
            )

            try:
                surgery_service._change_status(conn, sid, "COMPLETED")
                results["Salto de estado rechazado"] = False
            except ValidationError:
                results["Salto de estado rechazado"] = True

            surgery_service._change_status(conn, sid, "IN_PROGRESS")
            results["Iniciar cirugía"] = (
                surgery_repository.get_by_id(conn, sid).status == "IN_PROGRESS"
            )
            surgery_service._change_status(conn, sid, "COMPLETED")
            results["Completar cirugía"] = (
                surgery_repository.get_by_id(conn, sid).status == "COMPLETED"
            )

            try:
                surgery_service._update_surgery(
                    conn, sid, form(cid, vet_id, procedure_name="Otro")
                )
                results["No editar COMPLETED"] = False
            except ValidationError:
                results["No editar COMPLETED"] = True

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not (
                user_repository.username_exists(conn, "__test_vet13__")
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de cirugía: {exc}")
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
