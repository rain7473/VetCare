"""Diálogo para abrir una consulta clínica en borrador."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from database.connection import DatabaseConnectionError
from models.pet import Pet
from models.user import User
from services import consultation_service, permission_service, pet_service, session
from services.consultation_service import ConsultationFormData
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError
from views.pets.pet_dialog import PetDialog
from views.entity_creation import create_veterinarian_nested
from widgets.dynamic_selector import DynamicEntitySelector, SelectorItem
from widgets.managed_dialog import ManagedDialog


class ConsultationDialog(ManagedDialog):
    """Formulario modal para crear una consulta (estado DRAFT)."""

    def __init__(
        self,
        pets: list[Pet],
        veterinarians: list[User],
        parent=None,
        preferred_pet_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._pets = pets
        self._vets = veterinarians
        self._preferred_pet_id = preferred_pet_id
        self.setWindowTitle("Nueva consulta")
        self.setMinimumWidth(540)
        self._build_ui()
        self._reload_links()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.pet_selector = DynamicEntitySelector(
            placeholder="Buscar mascota, propietario o microchip…",
            add_tooltip="Crear mascota",
        )
        self.pet_selector.set_items(
            self._pet_items(), selected_id=self._preferred_pet_id
        )
        self.pet_selector.set_add_enabled(
            permission_service.has_permission("PETS_WRITE"),
            "Crear mascota" if permission_service.has_permission("PETS_WRITE")
            else "Sin permiso para crear mascotas",
        )
        self.pet_selector.add_requested.connect(self._create_pet)
        self.pet_selector.selection_changed.connect(self._reload_links)
        form.addRow("Paciente", self.pet_selector)

        self.vet_selector = DynamicEntitySelector(
            placeholder="Buscar veterinario…",
            add_tooltip="Crear usuario veterinario",
        )
        current = session.get_current_user()
        self.vet_selector.set_items(
            self._vet_items(), selected_id=current.id if current is not None else None
        )
        self.vet_selector.set_add_enabled(
            permission_service.has_permission("USERS_MANAGE"),
            "Crear veterinario" if permission_service.has_permission("USERS_MANAGE")
            else "Sin permiso para crear usuarios",
        )
        self.vet_selector.add_requested.connect(self._create_veterinarian)
        form.addRow("Veterinario", self.vet_selector)

        self.appointment_combo = QComboBox()
        form.addRow("Cita", self.appointment_combo)

        self.triage_combo = QComboBox()
        form.addRow("Triaje", self.triage_combo)

        self.reason_input = QTextEdit()
        self.reason_input.setPlaceholderText("Motivo de consulta")
        self.reason_input.setFixedHeight(56)
        form.addRow("Motivo", self.reason_input)

        self.symptoms_input = QTextEdit()
        self.symptoms_input.setPlaceholderText("Opcional")
        self.symptoms_input.setFixedHeight(56)
        form.addRow("Síntomas", self.symptoms_input)

        self.observations_input = QTextEdit()
        self.observations_input.setPlaceholderText("Opcional")
        self.observations_input.setFixedHeight(56)
        form.addRow("Observaciones", self.observations_input)

        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("variant", "secondary")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Abrir consulta")
        save.clicked.connect(self._on_save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _reload_links(self, *_args) -> None:
        pet_id = self.pet_selector.current_id()
        self.appointment_combo.clear()
        self.appointment_combo.addItem("Sin cita vinculada", None)
        self.triage_combo.clear()
        self.triage_combo.addItem("Sin triaje vinculado", None)
        if pet_id is None:
            return
        try:
            for appointment in consultation_service.list_open_appointments(pet_id):
                when = appointment.appointment_at.strftime("%d/%m %H:%M")
                self.appointment_combo.addItem(
                    f"{when} · {appointment.reason[:40]}", appointment.id
                )
            for triage in consultation_service.list_recent_triages(pet_id):
                when = (
                    triage.created_at.strftime("%d/%m %H:%M")
                    if triage.created_at
                    else "—"
                )
                self.triage_combo.addItem(
                    f"P{triage.priority_level} · {when} · {triage.reason[:32]}",
                    triage.id,
                )
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)

    def _on_save(self) -> None:
        data = ConsultationFormData(
            pet_id=self.pet_selector.current_id(),
            veterinarian_id=self.vet_selector.current_id(),
            appointment_id=self.appointment_combo.currentData(),
            triage_id=self.triage_combo.currentData(),
            reason=self.reason_input.toPlainText(),
            symptoms=self.symptoms_input.toPlainText(),
            observations=self.observations_input.toPlainText(),
        )
        try:
            consultation_service.create_consultation(data)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        self.accept()

    def _pet_items(self) -> list[SelectorItem]:
        return [
            SelectorItem(
                pet.id,
                f"{pet.name} ({pet.owner_name})",
                " ".join(filter(None, [pet.microchip_number, pet.owner_name])),
            )
            for pet in self._pets
        ]

    def _create_pet(self) -> None:
        try:
            owners = pet_service.list_active_owners()
            species = pet_service.list_species()
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        dialog = PetDialog(owners, species, parent=self)
        if not dialog.exec() or dialog.created_id is None:
            return
        pet = pet_service.get_pet(dialog.created_id)
        if pet is None:
            return
        self._pets.append(pet)
        self.pet_selector.set_items(self._pet_items(), selected_id=pet.id)
        self._reload_links()

    def _vet_items(self) -> list[SelectorItem]:
        return [SelectorItem(v.id, v.full_name, v.username) for v in self._vets]

    def _create_veterinarian(self) -> None:
        try:
            vet = create_veterinarian_nested(self)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        if vet is None:
            return
        self._vets.append(vet)
        self.vet_selector.set_items(self._vet_items(), selected_id=vet.id)
