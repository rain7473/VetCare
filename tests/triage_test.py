"""Pruebas del Objetivo 10: triaje.

Calculadora de prioridad (lógica pura), validaciones y creación con
INSERT + ROLLBACK, incluida la transición de la cita vinculada.

    python -m tests.triage_test
"""

import sys
from datetime import datetime, timedelta


def run() -> int:
    from database.connection import connection_scope
    from models.user import User
    from repositories import (
        appointment_repository,
        owner_repository,
        pet_repository,
        role_repository,
        species_repository,
        triage_repository,
        user_repository,
    )
    from services import session, triage_service
    from services.permission_service import PermissionDeniedError
    from services.triage_service import TriageFormData, suggest_priority
    from utils.security import hash_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}

    # ------------------------------------------ calculadora (lógica pura)
    no_signs = dict(
        consciousness_status=None,
        respiratory_distress=False,
        active_bleeding=False,
        can_walk=None,
        seizures=False,
        pain_level=None,
        temperature_c=None,
        oxygen_saturation_pct=None,
    )
    level, _ = suggest_priority(**no_signs)
    results["Sin signos: P4"] = level == 4

    level, reason = suggest_priority(**{**no_signs, "active_bleeding": True})
    results["Sangrado activo: P1"] = level == 1 and "sangrado" in reason

    level, _ = suggest_priority(
        **{**no_signs, "consciousness_status": "UNCONSCIOUS"}
    )
    results["Inconsciente: P1"] = level == 1

    level, _ = suggest_priority(**{**no_signs, "oxygen_saturation_pct": 85})
    results["SpO2 85: P1"] = level == 1

    level, _ = suggest_priority(**{**no_signs, "pain_level": 8})
    results["Dolor 8: P2"] = level == 2

    level, _ = suggest_priority(**{**no_signs, "can_walk": False})
    results["No camina: P2"] = level == 2

    level, _ = suggest_priority(**{**no_signs, "pain_level": 5})
    results["Dolor 5: P3"] = level == 3

    level, _ = suggest_priority(
        **{**no_signs, "consciousness_status": "DEPRESSED"}
    )
    results["Deprimido: P3"] = level == 3

    def form(pet_id, **overrides) -> TriageFormData:
        values = dict(
            pet_id=pet_id,
            appointment_id=None,
            reason="Chequeo urgente",
            consciousness_status="ALERT",
            respiratory_distress=False,
            active_bleeding=False,
            can_walk=True,
            seizures=False,
            pain_level=2,
            temperature_c=38.5,
            heart_rate_bpm=90,
            respiratory_rate_rpm=25,
            oxygen_saturation_pct=98,
            priority_level=4,
            priority_reason="Sin signos de alarma",
            observations="",
        )
        values.update(overrides)
        return TriageFormData(**values)

    try:
        session.set_current_user(
            User(id=993, role_id=1, username="fake_triage", email=None,
                 full_name="Fake Triage", phone=None, is_active=True,
                 role_name="TEST"),
            frozenset(),
        )
        try:
            triage_service.list_triages()
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        with connection_scope() as conn:  # sin commit → ROLLBACK
            owner_id = owner_repository.insert_owner(
                conn, identification=None, first_name="Triaje", last_name="Prueba",
                phone="6000-0003", secondary_phone=None, email=None,
                address=None, notes=None,
            )
            species_id = species_repository.list_species(conn)[0][0]
            pet_id = pet_repository.insert_pet(
                conn, owner_id=owner_id, species_id=species_id, breed_id=None,
                name="TriagePet", sex="FEMALE", birth_date=None,
                approximate_age_months=24, color=None,
                distinctive_features=None, microchip_number=None,
                photo_url=None, blood_type=None, allergies=None,
                chronic_conditions=None,
            )
            role_id = role_repository.get_role_id_by_name(conn, "RECEPTION")
            rec_id = user_repository.insert_user(
                conn, role_id=role_id, username="__test_triage10__", email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Recep Triage", phone=None,
            )
            session.set_current_user(
                User(id=rec_id, role_id=role_id, username="__test_triage10__",
                     email=None, full_name="Recep Triage", phone=None,
                     is_active=True, role_name="RECEPTION"),
                frozenset({"TRIAGE_CREATE", "APPOINTMENTS_MANAGE"}),
            )

            def expect_error(check_name: str, **overrides) -> None:
                try:
                    triage_service._create_triage(conn, form(pet_id, **overrides))
                    results[check_name] = False
                except ValidationError:
                    results[check_name] = True

            expect_error("Motivo vacío rechazado", reason=" ")
            expect_error("Dolor fuera de rango rechazado", pain_level=15)
            expect_error("SpO2 fuera de rango rechazado", oxygen_saturation_pct=150)
            expect_error("Prioridad inválida rechazada", priority_level=7)
            expect_error("Temperatura absurda rechazada", temperature_c=80.0)

            triage_id = triage_service._create_triage(conn, form(pet_id))
            created = triage_repository.get_by_id(conn, triage_id)
            results["Crear triaje"] = created is not None and created.priority_level == 4
            results["Registrado por correcto"] = (
                created.recorded_by_name == "Recep Triage"
            )

            # Con cita vinculada: la cita pasa a IN_ATTENTION.
            appt_id = appointment_repository.insert_appointment(
                conn, pet_id=pet_id, veterinarian_id=None, created_by=rec_id,
                appointment_at=datetime.now() + timedelta(hours=1),
                reason="Consulta", notes=None,
            )
            triage_service._create_triage(
                conn,
                form(
                    pet_id,
                    appointment_id=appt_id,
                    priority_level=1,
                    active_bleeding=True,
                ),
            )
            results["Cita vinculada pasa a IN_ATTENTION"] = (
                appointment_repository.get_by_id(conn, appt_id).status
                == "IN_ATTENTION"
            )

            listed = triage_repository.list_triages(conn)
            first_two = [t for t in listed if t.pet_id == pet_id]
            results["Orden por prioridad"] = (
                len(first_two) == 2 and first_two[0].priority_level == 1
            )
            # Salida sin commit → ROLLBACK automático.

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not (
                user_repository.username_exists(conn, "__test_triage10__")
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de triaje: {exc}")
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
