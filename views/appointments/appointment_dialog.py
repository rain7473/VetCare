"""Diálogo de creación/edición de citas."""

import logging

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QComboBox,
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
from services import appointment_service
from services.appointment_service import AppointmentFormData
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError

logger = logging.getLogger(__name__)


class AppointmentDialog(QDialog):
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

        self.pet_combo = QComboBox()
        for pet in self._pets:
            self.pet_combo.addItem(f"{pet.name} ({pet.owner_name})", pet.id)
        form.addRow("Mascota", self.pet_combo)

        self.vet_combo = QComboBox()
        self.vet_combo.addItem("Sin asignar", None)
        for vet in self._vets:
            self.vet_combo.addItem(vet.full_name, vet.id)
        form.addRow("Veterinario", self.vet_combo)

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
        index = self.pet_combo.findData(appt.pet_id)
        if index < 0:
            self.pet_combo.addItem(appt.pet_name or "(mascota)", appt.pet_id)
            index = self.pet_combo.count() - 1
        self.pet_combo.setCurrentIndex(index)

        vet_index = self.vet_combo.findData(appt.veterinarian_id)
        self.vet_combo.setCurrentIndex(vet_index if vet_index >= 0 else 0)

        at = appt.appointment_at
        self.datetime_input.setDateTime(
            QDateTime(at.year, at.month, at.day, at.hour, at.minute)
        )
        self.reason_input.setPlainText(appt.reason)
        self.notes_input.setPlainText(appt.notes or "")

    def _on_save(self) -> None:
        data = AppointmentFormData(
            pet_id=self.pet_combo.currentData(),
            veterinarian_id=self.vet_combo.currentData(),
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
