"""Pruebas del Objetivo 8: mascotas.

Validaciones + CRUD con INSERT + ROLLBACK (no persiste nada) +
razas creadas al vuelo + permisos.

    python -m tests.pets_test
"""

import sys
from datetime import date, timedelta


def _fake_session(codes: frozenset[str]) -> None:
    from models.user import User
    from services import session

    session.set_current_user(
        User(
            id=991,
            role_id=1,
            username="fake_pet_test",
            email=None,
            full_name="Fake Pets",
            phone=None,
            is_active=True,
            role_name="TEST",
        ),
        codes,
    )


def run() -> int:
    from database.connection import connection_scope
    from repositories import owner_repository, pet_repository, species_repository
    from services import pet_service, session
    from services.permission_service import PermissionDeniedError
    from services.pet_service import PetFormData
    from utils.validators import ValidationError

    results: dict[str, bool] = {}

    def base_data(default_owner_id: int, default_species_id: int,
                  **overrides) -> PetFormData:
        values = dict(
            owner_id=default_owner_id,
            species_id=default_species_id,
            breed_name="Golden Retriever",
            name="Max",
            sex="MALE",
            birth_date=date.today() - timedelta(days=730),
            approximate_age_months=None,
            color="Dorado",
            distinctive_features="",
            microchip_number="__CHIP-01__",
            blood_type="",
            allergies="Polen",
            chronic_conditions="",
        )
        values.update(overrides)
        return PetFormData(**values)

    try:
        _fake_session(frozenset({"PETS_READ"}))
        try:
            pet_service.create_pet(
                base_data(1, 1)
            )
            results["Sin PETS_WRITE no puede crear"] = False
        except PermissionDeniedError:
            results["Sin PETS_WRITE no puede crear"] = True

        _fake_session(frozenset({"PETS_READ", "PETS_WRITE"}))

        with connection_scope() as conn:  # sin commit → ROLLBACK
            owner_id = owner_repository.insert_owner(
                conn,
                identification=None,
                first_name="Prueba",
                last_name="Mascotas",
                phone="6000-0001",
                secondary_phone=None,
                email=None,
                address=None,
                notes=None,
            )
            species = species_repository.list_species(conn)
            canine_id = species[0][0]

            def expect_error(check_name: str, **overrides) -> None:
                try:
                    pet_service._create_pet(
                        conn, base_data(owner_id, canine_id, **overrides)
                    )
                    results[check_name] = False
                except ValidationError:
                    results[check_name] = True

            expect_error("Nombre vacío rechazado", name="  ", microchip_number="")
            expect_error("Sexo inválido rechazado", sex="OTRO", microchip_number="")
            expect_error(
                "Fecha futura rechazada",
                birth_date=date.today() + timedelta(days=1),
                microchip_number="",
            )
            expect_error(
                "Propietario inexistente rechazado",
                owner_id=99999999,
                microchip_number="",
            )

            pet_id = pet_service._create_pet(conn, base_data(owner_id, canine_id))
            results["Crear mascota"] = pet_id > 0

            created = pet_repository.get_by_id(conn, pet_id)
            results["Raza creada al vuelo"] = created.breed_name == "Golden Retriever"

            # Reutilización de raza (no duplica el catálogo).
            breed_id_1 = created.breed_id
            pet2_id = pet_service._create_pet(
                conn,
                base_data(
                    owner_id, canine_id, name="Luna", sex="FEMALE",
                    microchip_number="",
                ),
            )
            pet2 = pet_repository.get_by_id(conn, pet2_id)
            results["Raza reutilizada"] = pet2.breed_id == breed_id_1
            results["Propietario con múltiples mascotas"] = (
                pet2.owner_id == created.owner_id
            )

            expect_error("Microchip duplicado rechazado", name="Rocky")

            pet_service._update_pet(
                conn,
                pet_id,
                base_data(
                    owner_id, canine_id, color="Café", status="ACTIVE",
                ),
            )
            results["Editar mascota"] = (
                pet_repository.get_by_id(conn, pet_id).color == "Café"
            )

            pet_repository.set_status(conn, pet_id, "DECEASED")
            results["Cambio de estado"] = (
                pet_repository.get_by_id(conn, pet_id).status == "DECEASED"
            )

            results["Edad calculada"] = created.age_text() == "2 años"
            # Salida sin commit → ROLLBACK automático.

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not pet_repository.microchip_exists(
                conn, "__CHIP-01__"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de mascotas: {exc}")
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
