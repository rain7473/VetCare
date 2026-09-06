"""Pruebas del Objetivo 16: monitoreo y alertas clínicas.

Solo genera alertas cuando existe un rango en VITAL_RANGES.
Todo con INSERT + ROLLBACK (no persiste datos).

    python -m tests.monitoring_test
"""

import sys
from datetime import datetime


def run() -> int:
    from database.connection import connection_scope
    from models.user import User
    from repositories import (
        hospitalization_repository,
        monitoring_repository,
        owner_repository,
        pet_repository,
        role_repository,
        species_repository,
        user_repository,
    )
    from services import hospitalization_service, monitoring_service, session
    from services.hospitalization_service import (
        AreaFormData,
        HospitalizationFormData,
        SpaceFormData,
    )
    from services.monitoring_service import MonitoringFormData, VitalRangeFormData
    from services.permission_service import PermissionDeniedError
    from utils.security import hash_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}
    now = datetime.now()

    def measurement(hosp_id, **overrides) -> MonitoringFormData:
        values = dict(
            hospitalization_id=hosp_id,
            temperature_c=38.5,
            heart_rate_bpm=90,
            respiratory_rate_rpm=25,
            oxygen_saturation_pct=98,
            weight_kg=10.0,
            pain_level=2,
            feeding_status="Normal",
            hydration_status="Normal",
            observations="",
        )
        values.update(overrides)
        return MonitoringFormData(**values)

    try:
        session.set_current_user(
            User(
                id=999,
                role_id=1,
                username="fake_mon",
                email=None,
                full_name="Fake Mon",
                phone=None,
                is_active=True,
                role_name="TEST",
            ),
            frozenset(),
        )
        try:
            monitoring_service.list_vital_ranges()
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        with connection_scope() as conn:
            owner_id = owner_repository.insert_owner(
                conn,
                identification=None,
                first_name="Mon",
                last_name="Prueba",
                phone="6000-0016",
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
                name="MonPet",
                sex="FEMALE",
                birth_date=None,
                approximate_age_months=30,
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
                username="__test_vet16__",
                email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Vet Mon",
                phone=None,
            )
            session.set_current_user(
                User(
                    id=vet_id,
                    role_id=vet_role,
                    username="__test_vet16__",
                    email=None,
                    full_name="Vet Mon",
                    phone=None,
                    is_active=True,
                    role_name="VETERINARIAN",
                ),
                frozenset({"HOSPITAL_MANAGE"}),
            )

            area_id = hospitalization_service._create_area(
                conn, AreaFormData(name="UCI mon", description="")
            )
            space_id = hospitalization_service._create_space(
                conn,
                SpaceFormData(area_id=area_id, code="M-16", description=""),
            )
            hosp_id = hospitalization_service._admit(
                conn,
                HospitalizationFormData(
                    pet_id=pet_id,
                    veterinarian_id=vet_id,
                    space_id=space_id,
                    consultation_id=None,
                    admitted_at=now,
                    reason="Monitoreo",
                    treatment_plan="",
                ),
            )

            try:
                monitoring_service._record_monitoring(
                    conn, measurement(hosp_id, temperature_c=None, heart_rate_bpm=None,
                                      respiratory_rate_rpm=None,
                                      oxygen_saturation_pct=None, weight_kg=None,
                                      pain_level=None, feeding_status="",
                                      hydration_status="", observations="")
                )
                results["Medición vacía rechazada"] = False
            except ValidationError:
                results["Medición vacía rechazada"] = True

            mid, alerts = monitoring_service._record_monitoring(
                conn, measurement(hosp_id)
            )
            results["Registrar monitoreo sin rangos"] = mid > 0 and alerts == []

            try:
                monitoring_service._save_vital_range(
                    conn,
                    VitalRangeFormData(
                        species_id=None,
                        parameter_code="TEMPERATURE_C",
                        min_value=37.5,
                        max_value=39.5,
                        unit="°C",
                        description="",
                    ),
                )
                results["Rango sin especie rechazado"] = False
            except ValidationError:
                results["Rango sin especie rechazado"] = True

            monitoring_service._save_vital_range(
                conn,
                VitalRangeFormData(
                    species_id=species_id,
                    parameter_code="TEMPERATURE_C",
                    min_value=37.5,
                    max_value=39.5,
                    unit="°C",
                    description="Rango de prueba",
                ),
            )
            monitoring_service._save_vital_range(
                conn,
                VitalRangeFormData(
                    species_id=species_id,
                    parameter_code="OXYGEN_SATURATION_PCT",
                    min_value=94,
                    max_value=100,
                    unit="%",
                    description="",
                ),
            )
            results["Configurar rangos"] = (
                len(monitoring_repository.list_vital_ranges(conn, species_id)) >= 2
            )

            mid2, alerts2 = monitoring_service._record_monitoring(
                conn,
                measurement(hosp_id, temperature_c=41.0, oxygen_saturation_pct=88),
            )
            results["Alertas por fuera de rango"] = mid2 > 0 and len(alerts2) == 2

            open_alerts = monitoring_repository.list_alerts(
                conn, hospitalization_id=hosp_id, open_only=True
            )
            results["Listar alertas abiertas"] = len(open_alerts) == 2

            first = open_alerts[0]
            monitoring_service._set_alert_status(conn, first.id, "ACKNOWLEDGED")
            ack = next(
                a
                for a in monitoring_repository.list_alerts(conn, hospitalization_id=hosp_id)
                if a.id == first.id
            )
            results["Acusar alerta"] = ack.status == "ACKNOWLEDGED"

            monitoring_service._set_alert_status(
                conn, first.id, "RESOLVED", resolved_by=vet_id
            )
            resolved = next(
                a
                for a in monitoring_repository.list_alerts(conn, hospitalization_id=hosp_id)
                if a.id == first.id
            )
            results["Resolver alerta"] = resolved.status == "RESOLVED"

            hospitalization_service._change_status(conn, hosp_id, "DISCHARGED", "Alta")
            try:
                monitoring_service._record_monitoring(conn, measurement(hosp_id))
                results["No monitorear alta"] = False
            except ValidationError:
                results["No monitorear alta"] = True

        with connection_scope() as conn:
            results["ROLLBACK dejó la base intacta"] = not (
                user_repository.username_exists(conn, "__test_vet16__")
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de monitoreo: {exc}")
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
