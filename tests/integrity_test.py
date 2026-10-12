"""Pruebas del Objetivo 17: historial inmutable / SHA-256 / enmiendas.

    python -m tests.integrity_test
"""

import sys


def run() -> int:
    from database.connection import connection_scope
    from models.user import User
    from repositories import (
        amendment_repository,
        consultation_repository,
        owner_repository,
        pet_repository,
        role_repository,
        species_repository,
        user_repository,
    )
    from services import consultation_service, integrity_service, session
    from services.consultation_service import ConsultationFormData
    from services.integrity_service import AmendmentFormData
    from services.permission_service import PermissionDeniedError
    from utils.security import hash_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}

    try:
        session.set_current_user(
            User(
                id=1001,
                role_id=1,
                username="fake_int",
                email=None,
                full_name="Fake Int",
                phone=None,
                is_active=True,
                role_name="TEST",
            ),
            frozenset(),
        )
        try:
            integrity_service.list_amendments(1)
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        with connection_scope() as conn:
            owner_id = owner_repository.insert_owner(
                conn,
                identification=None,
                first_name="Int",
                last_name="Prueba",
                phone="6000-0017",
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
                name="IntPet",
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
                username="__test_vet17__",
                email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Vet Int",
                phone=None,
            )
            session.set_current_user(
                User(
                    id=vet_id,
                    role_id=vet_role,
                    username="__test_vet17__",
                    email=None,
                    full_name="Vet Int",
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

            cid = consultation_service._create_consultation(
                conn,
                ConsultationFormData(
                    pet_id=pet_id,
                    veterinarian_id=vet_id,
                    appointment_id=None,
                    triage_id=None,
                    reason="Control",
                    symptoms="",
                    observations="",
                ),
            )

            try:
                integrity_service._add_amendment(
                    conn,
                    AmendmentFormData(
                        consultation_id=cid,
                        reason="Corrección",
                        amendment_text="Texto",
                    ),
                )
                results["Enmienda en DRAFT rechazada"] = False
            except ValidationError:
                results["Enmienda en DRAFT rechazada"] = True

            consultation_service._finalize(conn, cid)
            sealed_hash = consultation_repository.seal(conn, cid, vet_id)
            results["Sellar consulta"] = (
                isinstance(sealed_hash, str) and len(sealed_hash) == 64
            )
            results["Verificar sello Oracle"] = consultation_repository.verify_hash(
                conn, cid
            )

            try:
                integrity_service._add_amendment(
                    conn,
                    AmendmentFormData(
                        consultation_id=cid, reason=" ", amendment_text="x"
                    ),
                )
                results["Motivo vacío rechazado"] = False
            except ValidationError:
                results["Motivo vacío rechazado"] = True

            aid = integrity_service._add_amendment(
                conn,
                AmendmentFormData(
                    consultation_id=cid,
                    reason="Error tipográfico",
                    amendment_text="El diagnóstico correcto es otitis.",
                ),
            )
            amendments = amendment_repository.list_by_consultation(conn, cid)
            results["Crear enmienda"] = len(amendments) == 1 and amendments[0].id == aid
            results["Enmienda con hash"] = (
                amendments[0].amendment_hash is not None
                and len(amendments[0].amendment_hash) == 64
            )

            report = integrity_service._verify(conn, cid)
            results["Reporte sello OK"] = report.seal_ok is True
            results["Reporte enmienda OK"] = (
                len(report.amendments) == 1 and report.amendments[0][1] is True
            )

            # Trigger append-only: no UPDATE.
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE clinical_amendments SET reason = 'x' WHERE id = :id",
                        {"id": aid},
                    )
                results["UPDATE enmienda bloqueado"] = False
            except Exception as exc:  # noqa: BLE001
                results["UPDATE enmienda bloqueado"] = "20008" in str(exc) or "inmutables" in str(
                    exc
                ).lower()

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not (
                user_repository.username_exists(conn, "__test_vet17__")
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de integridad: {exc}")
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
