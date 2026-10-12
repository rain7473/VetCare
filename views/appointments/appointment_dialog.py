"""Diálogo de creación/edición de citas."""

import logging

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from database.connection import DatabaseConnectionError
from models.appointment import Appointment
from models.pet import Pet
from models.user import User
from services import appointment_service, permission_service, pet_service
from services.appointment_service import AppointmentFormData
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError
from views.pets.pet_dialog import PetDialog
from views.entity_creation import create_veterinarian_nested
from widgets.dynamic_selector import DynamicEntitySelector, SelectorItem
from widgets.managed_dialog import ManagedDialog

logger = logging.getLogger(__name__)


class AppointmentDialog(ManagedDialog):
    """Formulario modal para crear o editar una cita."""

    def __init__(
        self,
        pets: list[Pet],
        veterinarians: list[User],
        appointment: Appointment | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._pets = pets
        self._vets = veterinarians
        self._appointment = appointment
        self.setWindowTitle("Editar cita" if appointment else "Nueva cita")
        self.setMinimumWidth(500)
        self._build_ui()
        if appointment is not None:
            self._load_appointment()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setVerticalSpacing(12)

        self.pet_selector = DynamicEntitySelector(
            placeholder="Buscar mascota o propietario…",
            add_tooltip="Crear mascota",
        )
        self.pet_selector.set_items(self._pet_items())
        self.pet_selector.set_add_enabled(
            permission_service.has_permission("PETS_WRITE"),
            "Crear mascota" if permission_service.has_permission("PETS_WRITE")
            else "Sin permiso para crear mascotas",
        )
        self.pet_selector.add_requested.connect(self._create_pet)
        form.addRow("Mascota", self.pet_selector)

        self.vet_selector = DynamicEntitySelector(
            placeholder="Buscar veterinario…",
            add_tooltip="Crear usuario veterinario",
            allow_empty=True,
            empty_label="Sin asignar",
        )
        self.vet_selector.set_items(self._vet_items(), selected_id=None)
        self.vet_selector.set_add_enabled(
            permission_service.has_permission("USERS_MANAGE"),
            "Crear veterinario" if permission_service.has_permission("USERS_MANAGE")
            else "Sin permiso para crear usuarios",
        )
        self.vet_selector.add_requested.connect(self._create_veterinarian)
        form.addRow("Veterinario", self.vet_selector)

        self.datetime_input = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.datetime_input.setCalendarPopup(True)
        self.datetime_input.setDisplayFormat("dd/MM/yyyy HH:mm")
        form.addRow("Fecha y hora", self.datetime_input)

        self.reason_input = QTextEdit()
        self.reason_input.setPlaceholderText("Motivo de la cita")
        self.reason_input.setFixedHeight(64)
        form.addRow("Motivo", self.reason_input)

        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Opcional")
        self.notes_input.setFixedHeight(48)
        form.addRow("Notas", self.notes_input)

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
        save = QPushButton("Guardar")
        save.clicked.connect(self._on_save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _load_appointment(self) -> None:
        appt = self._appointment
        if not self.pet_selector.select_id(appt.pet_id):
            self.pet_selector.set_items(
                self._pet_items()
                + [SelectorItem(appt.pet_id, appt.pet_name or "(mascota)")],
                selected_id=appt.pet_id,
            )
        self.vet_selector.select_id(appt.veterinarian_id)

        at = appt.appointment_at
        self.datetime_input.setDateTime(
            QDateTime(at.year, at.month, at.day, at.hour, at.minute)
        )
        self.reason_input.setPlainText(appt.reason)
        self.notes_input.setPlainText(appt.notes or "")

    def _on_save(self) -> None:
        data = AppointmentFormData(
            pet_id=self.pet_selector.current_id(),
            veterinarian_id=self.vet_selector.current_id(),
            appointment_at=self.datetime_input.dateTime().toPython(),
            reason=self.reason_input.toPlainText(),
            notes=self.notes_input.toPlainText(),
        )
        try:
            if self._appointment is None:
                appointment_service.create_appointment(data)
            else:
                appointment_service.update_appointment(self._appointment.id, data)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        except Exception:
            logger.exception("Error inesperado al guardar la cita")
            self.error_label.setText("Ocurrió un error inesperado al guardar.")
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
