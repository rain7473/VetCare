"""Diálogos de catálogo y aplicación de vacunas."""

from PySide6.QtCore import QDate, QDateTime
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from database.connection import DatabaseConnectionError
from models.pet import Pet
from models.vaccine import Vaccine
from services import vaccine_service
from services.permission_service import PermissionDeniedError
from services.vaccine_service import VaccinationFormData, VaccineCatalogData
from utils.validators import ValidationError


class CatalogDialog(QDialog):
    """Alta de una vacuna en el catálogo."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nueva vacuna del catálogo")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()
        self.name_input = QLineEdit()
        form.addRow("Nombre", self.name_input)
        self.manufacturer_input = QLineEdit()
        self.manufacturer_input.setPlaceholderText("Opcional")
        form.addRow("Fabricante", self.manufacturer_input)
        self.description_input = QTextEdit()
        self.description_input.setFixedHeight(56)
        form.addRow("Descripción", self.description_input)
        layout.addLayout(form)
        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
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

    def _on_save(self) -> None:
        try:
            vaccine_service.add_to_catalog(
                VaccineCatalogData(
                    name=self.name_input.text(),
                    manufacturer=self.manufacturer_input.text(),
                    description=self.description_input.toPlainText(),
                )
            )
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        self.accept()


class ApplyDialog(QDialog):
    """Registro de una aplicación de vacuna."""

    def __init__(
        self,
        pets: list[Pet],
        vaccines: list[Vaccine],
        preferred_pet_id: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aplicar vacuna")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()

        self.pet_combo = QComboBox()
        selected = 0
        for index, pet in enumerate(pets):
            self.pet_combo.addItem(f"{pet.name} ({pet.owner_name})", pet.id)
            if pet.id == preferred_pet_id:
                selected = index
        if pets:
            self.pet_combo.setCurrentIndex(selected)
        form.addRow("Mascota", self.pet_combo)

        self.vaccine_combo = QComboBox()
        for vaccine in vaccines:
            label = vaccine.name
            if vaccine.manufacturer:
                label += f" · {vaccine.manufacturer}"
            self.vaccine_combo.addItem(label, vaccine.id)
        form.addRow("Vacuna", self.vaccine_combo)

        self.applied_input = QDateTimeEdit(QDateTime.currentDateTime())
        self.applied_input.setCalendarPopup(True)
        self.applied_input.setDisplayFormat("dd/MM/yyyy HH:mm")
        form.addRow("Fecha de aplicación", self.applied_input)

        self.lot_input = QLineEdit()
        self.lot_input.setPlaceholderText("Opcional")
        form.addRow("Lote", self.lot_input)

        self.expiry_input = QDateEdit()
        self.expiry_input.setCalendarPopup(True)
        self.expiry_input.setDisplayFormat("dd/MM/yyyy")
        self.expiry_input.setSpecialValueText("Sin vencimiento")
        self.expiry_input.setDate(QDate())
        form.addRow("Vencimiento", self.expiry_input)

        self.next_input = QDateEdit()
        self.next_input.setCalendarPopup(True)
        self.next_input.setDisplayFormat("dd/MM/yyyy")
        self.next_input.setSpecialValueText("Sin próxima fecha")
        self.next_input.setDate(QDate())
        form.addRow("Próxima aplicación", self.next_input)

        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(48)
        form.addRow("Notas", self.notes_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("variant", "secondary")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Registrar aplicación")
        save.clicked.connect(self._on_save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _on_save(self) -> None:
        expiry = self.expiry_input.date()
        nxt = self.next_input.date()
        try:
            vaccine_service.apply_vaccination(
                VaccinationFormData(
                    pet_id=self.pet_combo.currentData(),
                    vaccine_id=self.vaccine_combo.currentData(),
                    consultation_id=None,
                    applied_at=self.applied_input.dateTime().toPython(),
                    lot_number=self.lot_input.text(),
                    expiry_date=expiry.toPython() if expiry.isValid() else None,
                    next_due_date=nxt.toPython() if nxt.isValid() else None,
                    notes=self.notes_input.toPlainText(),
                )
            )
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        self.accept()
