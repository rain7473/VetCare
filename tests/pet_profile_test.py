"""Pruebas de la ficha de mascotas; Oracle solo se consulta, sin DML."""

import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def run() -> int:
    from main import create_app
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from models.consultation import Consultation
    from models.user import User
    from models.vaccine import PetVaccination
    from services import pet_profile_service, pet_service, session
    from services.permission_service import PermissionDeniedError
    from views.pets.pet_profile_panel import _rounded_photo
    from views.pets.pets_page import PetsPage
    from views.consultations.consultations_page import ConsultationsPage

    app = create_app([])
    user = User(
        id=0, role_id=1, username="profile_test", email=None,
        full_name="Prueba perfil", phone=None, is_active=True, role_name="ADMIN",
    )
    full_access = frozenset({
        "PETS_READ", "PETS_WRITE", "CONSULTATIONS_READ",
        "CONSULTATIONS_WRITE", "VACCINES_MANAGE",
    })
    session.set_current_user(user, full_access)
    checks: dict[str, bool] = {}
    try:
        page = PetsPage()
        with tempfile.TemporaryDirectory() as image_dir:
            image_path = Path(image_dir) / "photo.png"
            source = QPixmap(24, 42)
            source.fill(Qt.cyan)
            source.save(str(image_path))
            checks["Foto rectangular se recorta sin error"] = not _rounded_photo(
                str(image_path)
            ).isNull()
        page.resize(1100, 650)
        page.show()
        app.processEvents()
        checks["Cinco pestañas del perfil"] = [
            page.profile_panel.tabs.tabText(index) for index in range(5)
        ] == ["Información", "Historial", "Vacunas", "Consultas", "Archivos"]
        checks["Datos reales del listado"] = page.model.rowCount() > 0
        if page.model.rowCount():
            page.table.selectRow(0)
            app.processEvents()
            first_id = page._selected.id
            checks["Selección actualiza cabecera"] = (
                page.profile_panel.name_label.text() == page._selected.name
            )
            checks["Datos clínicos corresponden a la mascota"] = all(
                item.pet_id == first_id for item in
                pet_profile_service.load_profile(first_id).consultations
            )
            checks["Botones inferiores visibles"] = all(
                button.isVisible() for button in page.profile_panel.quick_buttons
            )
            checks["Selección sobrevive al refresco"] = (
                page.refresh() is None and page._selected.id == first_id
            )
            selected = page._selected
            consultation = Consultation(
                id=41, pet_id=first_id, appointment_id=None, triage_id=None,
                veterinarian_id=1, reason="Revisión", symptoms=None,
                observations="Observación de prueba", diagnosis_summary=None,
                treatment_summary=None, status="FINALIZED", started_at=datetime.now(),
                ended_at=None, sealed_at=None, sealed_by=None, sealed_hash=None,
                veterinarian_name="Veterinaria de prueba",
            )
            vaccination = PetVaccination(
                id=51, pet_id=first_id, vaccine_id=1, consultation_id=None,
                inventory_lot_id=None, applied_by=1, applied_at=datetime.now(),
                lot_number=None, expiry_date=None,
                next_due_date=date.today() + timedelta(days=30), notes=None,
                vaccine_name="Vacuna de prueba", applied_by_name="Veterinaria de prueba",
            )
            fixture = pet_profile_service.PetProfileData(
                (consultation,), (vaccination,), 12.5, True, True,
            )
            superseded = replace(
                vaccination, id=50,
                applied_at=vaccination.applied_at - timedelta(days=90),
                next_due_date=date.today() + timedelta(days=1),
            )
            checks["Refuerzo reciente sustituye fecha previa"] = (
                pet_profile_service.PetProfileData(
                    vaccinations=(superseded, vaccination)
                ).next_vaccination == vaccination
            )
            page.profile_panel.set_pet(selected, fixture)
            checks["Seguimiento muestra fechas y peso"] = (
                page.profile_panel.follow_values["Última consulta"].text() ==
                consultation.started_at.strftime("%d/%m/%Y")
                and "Vacuna de prueba" in
                page.profile_panel.follow_values["Próxima vacuna"].text()
                and "12.5 kg" in page.profile_panel.meta_label.text()
            )
            checks["Notas clínicas provienen de consulta"] = (
                "Observación de prueba" in page.profile_panel.notes_label.text()
            )
            checks["Historial y pestañas clínicas muestran registros"] = (
                page.profile_panel.history_layout.count() == 3
                and page.profile_panel.consult_layout.count() == 2
                and page.profile_panel.vaccine_layout.count() == 2
            )
            page._show_pet(selected)  # Restaura únicamente datos leídos de Oracle.
            requested: list[int] = []
            page.open_consultation_requested.connect(requested.append)
            page.profile_panel.quick_buttons[0].click()
            checks["Nueva consulta recibe mascota seleccionada"] = requested == [first_id]
            history_requested: list[int] = []
            page.open_history_requested.connect(history_requested.append)
            page.profile_panel.quick_buttons[1].click()
            checks["Historial recibe ID, no nombre ambiguo"] = history_requested == [first_id]
            vaccination_requested: list[int] = []
            page.open_vaccination_requested.connect(vaccination_requested.append)
            page.profile_panel.quick_buttons[2].click()
            checks["Vacunar recibe mascota seleccionada"] = (
                vaccination_requested == [first_id]
            )
            clinical_page = ConsultationsPage()
            same_name = replace(consultation, id=42, pet_id=first_id + 1)
            with patch(
                "views.consultations.consultations_page.consultation_service.list_consultations",
                return_value=[consultation, same_name],
            ):
                clinical_page.filter_by_pet_id(first_id)
            checks["Historial filtra ID exacto"] = clinical_page.model.rowCount() == 1
            clinical_page.search_input.setText("Revisión")
            checks["Buscar en consultas libera filtro de perfil"] = (
                clinical_page.model.rowCount() == 2
            )
            clinical_page.close()
            if page.model.rowCount() > 1:
                page.table.selectRow(1)
                app.processEvents()
                checks["Otra fila cambia el perfil"] = (
                    page.profile_panel.name_label.text() == page._selected.name
                    and page._selected.id != first_id
                )
        for width in (1100, 1600, 1920):
            page.resize(width, 650)
            app.processEvents()
            panel = page.profile_panel
            checks[f"Sin desborde horizontal a {width}px"] = (
                panel.geometry().right() <= page.contentsRect().right()
                and panel.tabs.currentWidget().horizontalScrollBar().maximum() == 0
            )
            if not checks[f"Sin desborde horizontal a {width}px"]:
                print(
                    f"  Diagnóstico {width}: panel={panel.geometry()}, "
                    f"página={page.contentsRect()}, "
                    f"scroll={panel.tabs.currentWidget().horizontalScrollBar().maximum()}"
                )
            checks[f"Acciones visibles a {width}px"] = all(
                button.isVisible() and button.height() > 0
                for button in panel.quick_buttons
            )
            checks[f"Tarjetas adaptadas a {width}px"] = (
                panel.info_grid.itemAtPosition(0, 1) is not None
                if panel.width() >= 440 else
                panel.info_grid.itemAtPosition(0, 1) is None
            )
        session.set_current_user(user, frozenset({"PETS_READ"}))
        if page._selected:
            limited = pet_profile_service.load_profile(page._selected.id)
            checks["Sin permiso no filtra datos clínicos"] = (
                not limited.clinical_allowed and not limited.consultations
                and not limited.vaccines_allowed and not limited.vaccinations
            )
            try:
                pet_service.update_pet_photo(page._selected.id, "no-se-usa.png")
                checks["Cambio de foto exige PETS_WRITE"] = False
            except PermissionDeniedError:
                checks["Cambio de foto exige PETS_WRITE"] = True
        page.close()
    finally:
        session.clear()
    for name, passed in checks.items():
        print(f"  [{'OK' if passed else 'FALLO'}] {name}")
    return 0 if checks and all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(run())
