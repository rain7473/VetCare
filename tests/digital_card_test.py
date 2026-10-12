"""Pruebas del Objetivo 18: carné digital / QR.

    python -m tests.digital_card_test
"""

import sys


def run() -> int:
    from database.connection import connection_scope
    from models.user import User
    from repositories import (
        digital_card_repository,
        owner_repository,
        pet_repository,
        role_repository,
        species_repository,
        user_repository,
    )
    from services import digital_card_service, session
    from services.permission_service import PermissionDeniedError
    from utils.qr import card_payload
    from utils.security import hash_password

    results: dict[str, bool] = {}

    try:
        session.set_current_user(
            User(
                id=1002,
                role_id=1,
                username="fake_card",
                email=None,
                full_name="Fake Card",
                phone=None,
                is_active=True,
                role_name="TEST",
            ),
            frozenset(),
        )
        try:
            digital_card_service.get_or_issue_card(1)
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        payload = card_payload("AABBCCDDEEFF00112233445566778899")
        results["QR payload sin datos clínicos"] = payload.startswith("vetcare:pet:")
        results["QR payload solo token"] = "aabb" in payload and "diagnos" not in payload.lower()

        with connection_scope() as conn:
            owner_id = owner_repository.insert_owner(
                conn,
                identification=None,
                first_name="Card",
                last_name="Prueba",
                phone="6000-0018",
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
                name="CardPet",
                sex="FEMALE",
                birth_date=None,
                approximate_age_months=8,
                color=None,
                distinctive_features=None,
                microchip_number="CHIP-18",
                photo_url=None,
                blood_type=None,
                allergies=None,
                chronic_conditions=None,
            )
            role_id = role_repository.get_role_id_by_name(conn, "RECEPTION")
            user_id = user_repository.insert_user(
                conn,
                role_id=role_id,
                username="__test_card18__",
                email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Recep Card",
                phone=None,
            )
            session.set_current_user(
                User(
                    id=user_id,
                    role_id=role_id,
                    username="__test_card18__",
                    email=None,
                    full_name="Recep Card",
                    phone=None,
                    is_active=True,
                    role_name="RECEPTION",
                ),
                frozenset({"PETS_READ", "PETS_WRITE"}),
            )

            card = digital_card_repository.insert_card(
                conn, pet_id=pet_id, created_by=user_id
            )
            results["Emitir carné"] = card.id > 0 and len(card.public_token_hex) == 32
            active = digital_card_repository.get_active_for_pet(conn, pet_id)
            results["Carné activo"] = active is not None and active.id == card.id

            digital_card_repository.deactivate_for_pet(conn, pet_id)
            card2 = digital_card_repository.insert_card(
                conn, pet_id=pet_id, created_by=user_id
            )
            active2 = digital_card_repository.get_active_for_pet(conn, pet_id)
            results["Reemitir carné"] = (
                active2 is not None
                and active2.id == card2.id
                and active2.public_token_hex != card.public_token_hex
            )

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not (
                user_repository.username_exists(conn, "__test_card18__")
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de carné: {exc}")
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
