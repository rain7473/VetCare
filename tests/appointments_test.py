"""Pruebas del Objetivo 9: citas.

Validaciones, máquina de estados y consultas por día, todo con
INSERT + ROLLBACK (no persiste nada).

    python -m tests.appointments_test
"""

import sys
from datetime import datetime, timedelta


def run() -> int:
    from database.connection import connection_scope
    from models.user import User
    from repositories import (
        appointment_repository,
        owner_repository,
        role_repository,
        species_repository,
        user_repository,
    )
    from services import appointment_service, session
    from services.appointment_service import AppointmentFormData
    from services.permission_service import PermissionDeniedError
    from utils.security import hash_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}
    tomorrow = datetime.now() + timedelta(days=1)

    def form(default_pet_id, **overrides) -> AppointmentFormData:
        values = dict(
            pet_id=default_pet_id,
            veterinarian_id=None,
            appointment_at=tomorrow,
            reason="Control general",
            notes="",
        )
        values.update(overrides)
        return AppointmentFormData(**values)

    try:
        session.set_current_user(
            User(id=992, role_id=1, username="fake_appt", email=None,
                 full_name="Fake Citas", phone=None, is_active=True,
                 role_name="TEST"),
            frozenset(),
        )
        try:
            appointment_service.list_appointments()
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        with connection_scope() as conn:  # sin commit → ROLLBACK
            # Datos de apoyo dentro de la transacción.
            owner_id = owner_repository.insert_owner(
                conn, identification=None, first_name="Cita", last_name="Prueba",
                phone="6000-0002", secondary_phone=None, email=None,
                address=None, notes=None,
            )
            species_id = species_repository.list_species(conn)[0][0]
            from repositories import pet_repository

            pet_id = pet_repository.insert_pet(
                conn, owner_id=owner_id, species_id=species_id, breed_id=None,
                name="CitaPet", sex="MALE", birth_date=None,
                approximate_age_months=12, color=None,
                distinctive_features=None, microchip_number=None,
                photo_url=None, blood_type=None, allergies=None,
                chronic_conditions=None,
            )
            vet_role = role_repository.get_role_id_by_name(conn, "VETERINARIAN")
            vet_id = user_repository.insert_user(
                conn, role_id=vet_role, username="__test_vet9__", email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Vet Prueba", phone=None,
            )

            # Sesión con el usuario creado en esta transacción.
            session.set_current_user(
                User(id=vet_id, role_id=vet_role, username="__test_vet9__",
                     email=None, full_name="Vet Prueba", phone=None,
                     is_active=True, role_name="VETERINARIAN"),
                frozenset({"APPOINTMENTS_MANAGE"}),
            )

            def expect_error(check_name: str, **overrides) -> None:
                try:
                    appointment_service._create_appointment(
                        conn, form(pet_id, **overrides)
                    )
                    results[check_name] = False
                except ValidationError:
                    results[check_name] = True

            expect_error("Sin mascota rechazada", pet_id=None)
            expect_error("Motivo vacío rechazado", reason="  ")
            expect_error(
                "Cita en el pasado rechazada",
                appointment_at=datetime.now() - timedelta(hours=2),
            )
            expect_error(
                "Veterinario inválido rechazado", veterinarian_id=99999999
            )

            appt_id = appointment_service._create_appointment(
                conn, form(pet_id, veterinarian_id=vet_id)
            )
            created = appointment_repository.get_by_id(conn, appt_id)
            results["Crear cita (SCHEDULED)"] = created.status == "SCHEDULED"
            results["Cita con veterinario asignado"] = (
                created.veterinarian_name == "Vet Prueba"
            )

            todays = appointment_repository.list_appointments(
                conn, tomorrow.date()
            )
            results["Citas del día filtradas"] = any(a.id == appt_id for a in todays)

            appointment_service._change_status(conn, appt_id, "CONFIRMED")
            results["SCHEDULED pasa a CONFIRMED"] = (
                appointment_repository.get_by_id(conn, appt_id).status == "CONFIRMED"
            )

            try:
                appointment_service._change_status(conn, appt_id, "COMPLETED")
                results["CONFIRMED a COMPLETED rechazada"] = False
            except ValidationError:
                results["CONFIRMED a COMPLETED rechazada"] = True

            appointment_service._change_status(conn, appt_id, "CANCELLED")
            try:
                appointment_service._change_status(conn, appt_id, "CONFIRMED")
                results["Cita cancelada es terminal"] = False
            except ValidationError:
                results["Cita cancelada es terminal"] = True

            try:
                appointment_service._update_appointment(
                    conn, appt_id, form(pet_id, reason="Cambio")
                )
                results["Cancelada no editable"] = False
            except ValidationError:
                results["Cancelada no editable"] = True
            # Salida sin commit → ROLLBACK automático.

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not (
                user_repository.username_exists(conn, "__test_vet9__")
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de citas: {exc}")
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
