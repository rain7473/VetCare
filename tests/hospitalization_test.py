"""Pruebas del Objetivo 15: hospitalización.

Áreas, espacios, ingreso, ocupación de jaula y máquina de estados.
Todo con INSERT + ROLLBACK.

    python -m tests.hospitalization_test
"""

import sys
from datetime import datetime


def run() -> int:
    from database.connection import connection_scope
    from models.user import User
    from repositories import (
        hospitalization_repository,
        owner_repository,
        pet_repository,
        role_repository,
        species_repository,
        user_repository,
    )
    from services import hospitalization_service, session
    from services.hospitalization_service import (
        AreaFormData,
        HospitalizationFormData,
        SpaceFormData,
    )
    from services.permission_service import PermissionDeniedError
    from utils.security import hash_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}
    now = datetime.now()

    try:
        session.set_current_user(
            User(
                id=998,
                role_id=1,
                username="fake_hosp",
                email=None,
                full_name="Fake Hosp",
                phone=None,
                is_active=True,
                role_name="TEST",
            ),
            frozenset(),
        )
        try:
            hospitalization_service.list_active()
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        with connection_scope() as conn:
            owner_id = owner_repository.insert_owner(
                conn,
                identification=None,
                first_name="Hosp",
                last_name="Prueba",
                phone="6000-0015",
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
                name="HospPet",
                sex="MALE",
                birth_date=None,
                approximate_age_months=24,
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
                username="__test_vet15__",
                email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Vet Hosp",
                phone=None,
            )
            session.set_current_user(
                User(
                    id=vet_id,
                    role_id=vet_role,
                    username="__test_vet15__",
                    email=None,
                    full_name="Vet Hosp",
                    phone=None,
                    is_active=True,
                    role_name="VETERINARIAN",
                ),
                frozenset({"HOSPITAL_MANAGE"}),
            )

            try:
                hospitalization_service._create_area(
                    conn, AreaFormData(name=" ", description="")
                )
                results["Área vacía rechazada"] = False
            except ValidationError:
                results["Área vacía rechazada"] = True

            area_id = hospitalization_service._create_area(
                conn, AreaFormData(name="UCI prueba", description="Área crítica")
            )
            space_id = hospitalization_service._create_space(
                conn,
                SpaceFormData(area_id=area_id, code="J-15", description="Jaula 15"),
            )
            results["Crear área y espacio"] = space_id > 0

            try:
                hospitalization_service._admit(
                    conn,
                    HospitalizationFormData(
                        pet_id=pet_id,
                        veterinarian_id=vet_id,
                        space_id=space_id,
                        consultation_id=None,
                        admitted_at=now,
                        reason=" ",
                        treatment_plan="",
                    ),
                )
                results["Motivo vacío rechazado"] = False
            except ValidationError:
                results["Motivo vacío rechazado"] = True

            hosp_id = hospitalization_service._admit(
                conn,
                HospitalizationFormData(
                    pet_id=pet_id,
                    veterinarian_id=vet_id,
                    space_id=space_id,
                    consultation_id=None,
                    admitted_at=now,
                    reason="Postoperatorio",
                    treatment_plan="Fluidoterapia",
                ),
            )
            created = hospitalization_repository.get_by_id(conn, hosp_id)
            results["Ingreso ADMITTED"] = (
                created is not None and created.status == "ADMITTED"
            )
            space = hospitalization_repository.get_space(conn, space_id)
            results["Espacio ocupado al ingresar"] = space.status == "OCCUPIED"

            try:
                hospitalization_service._admit(
                    conn,
                    HospitalizationFormData(
                        pet_id=pet_id,
                        veterinarian_id=vet_id,
                        space_id=None,
                        consultation_id=None,
                        admitted_at=now,
                        reason="Duplicado",
                        treatment_plan="",
                    ),
                )
                results["Doble ingreso activo rechazado"] = False
            except ValidationError:
                results["Doble ingreso activo rechazado"] = True

            hospitalization_service._change_status(conn, hosp_id, "CRITICAL", "")
            results["Pasar a CRITICAL"] = (
                hospitalization_repository.get_by_id(conn, hosp_id).status == "CRITICAL"
            )

            hospitalization_service._change_status(
                conn, hosp_id, "DISCHARGED", "Recuperado"
            )
            closed = hospitalization_repository.get_by_id(conn, hosp_id)
            results["Dar de alta"] = (
                closed.status == "DISCHARGED" and closed.discharged_at is not None
            )
            freed = hospitalization_repository.get_space(conn, space_id)
            results["Espacio liberado al alta"] = freed.status == "AVAILABLE"

            try:
                hospitalization_service._change_status(conn, hosp_id, "ADMITTED", "")
                results["No reabrir desde DISCHARGED"] = False
            except ValidationError:
                results["No reabrir desde DISCHARGED"] = True

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not (
                user_repository.username_exists(conn, "__test_vet15__")
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de hospitalización: {exc}")
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
