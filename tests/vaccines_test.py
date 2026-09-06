"""Pruebas del Objetivo 14: vacunas.

Catálogo, aplicación, validaciones y alertas de próxima fecha.
Todo con INSERT + ROLLBACK.

    python -m tests.vaccines_test
"""

import sys
from datetime import date, datetime, timedelta


def run() -> int:
    from database.connection import connection_scope
    from models.user import User
    from repositories import (
        owner_repository,
        pet_repository,
        role_repository,
        species_repository,
        user_repository,
        vaccine_repository,
    )
    from services import session, vaccine_service
    from services.permission_service import PermissionDeniedError
    from services.vaccine_service import VaccinationFormData, VaccineCatalogData
    from utils.security import hash_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}
    applied = datetime.now()

    def form(default_pet_id, default_vaccine_id, **overrides) -> VaccinationFormData:
        values = dict(
            pet_id=default_pet_id,
            vaccine_id=default_vaccine_id,
            consultation_id=None,
            applied_at=applied,
            lot_number="L-100",
            expiry_date=date.today() + timedelta(days=365),
            next_due_date=date.today() + timedelta(days=10),
            notes="Refuerzo",
        )
        values.update(overrides)
        return VaccinationFormData(**values)

    try:
        session.set_current_user(
            User(
                id=997,
                role_id=1,
                username="fake_vac",
                email=None,
                full_name="Fake Vac",
                phone=None,
                is_active=True,
                role_name="TEST",
            ),
            frozenset(),
        )
        try:
            vaccine_service.list_catalog()
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        with connection_scope() as conn:
            owner_id = owner_repository.insert_owner(
                conn,
                identification=None,
                first_name="Vacuna",
                last_name="Prueba",
                phone="6000-0014",
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
                name="VacPet",
                sex="MALE",
                birth_date=None,
                approximate_age_months=12,
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
                username="__test_vet14__",
                email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Vet Vacuna",
                phone=None,
            )
            session.set_current_user(
                User(
                    id=vet_id,
                    role_id=vet_role,
                    username="__test_vet14__",
                    email=None,
                    full_name="Vet Vacuna",
                    phone=None,
                    is_active=True,
                    role_name="VETERINARIAN",
                ),
                frozenset({"VACCINES_MANAGE"}),
            )

            try:
                vaccine_service._add_to_catalog(
                    conn, VaccineCatalogData(name=" ", manufacturer="", description="")
                )
                results["Nombre de catálogo vacío rechazado"] = False
            except ValidationError:
                results["Nombre de catálogo vacío rechazado"] = True

            vac_id = vaccine_service._add_to_catalog(
                conn,
                VaccineCatalogData(
                    name="Rabia prueba",
                    manufacturer="Lab Test",
                    description="Vacuna de prueba",
                ),
            )
            results["Agregar al catálogo"] = vac_id > 0

            try:
                vaccine_service._apply_vaccination(conn, form(pet_id, vac_id, pet_id=None))
                results["Mascota vacía rechazada"] = False
            except ValidationError:
                results["Mascota vacía rechazada"] = True

            try:
                vaccine_service._apply_vaccination(
                    conn,
                    form(
                        pet_id,
                        vac_id,
                        expiry_date=date.today() - timedelta(days=1),
                    ),
                )
                results["Lote vencido rechazado"] = False
            except ValidationError:
                results["Lote vencido rechazado"] = True

            app_id = vaccine_service._apply_vaccination(conn, form(pet_id, vac_id))
            listed = vaccine_repository.list_applications(conn, pet_id)
            results["Aplicar vacuna"] = (
                len(listed) == 1 and listed[0].id == app_id
            )
            due = vaccine_repository.list_due_soon(
                conn, date.today() + timedelta(days=30)
            )
            results["Alerta de próxima vacuna"] = any(a.id == app_id for a in due)

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not (
                user_repository.username_exists(conn, "__test_vet14__")
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de vacunas: {exc}")
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
