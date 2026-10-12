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
from services import permission_service, vaccine_service
from services.permission_service import PermissionDeniedError
from services.vaccine_service import VaccinationFormData, VaccineCatalogData
from utils.validators import ValidationError
from views.entity_creation import create_pet_nested
from widgets.dynamic_selector import DynamicEntitySelector, SelectorItem
from widgets.managed_dialog import ManagedDialog


class CatalogDialog(ManagedDialog):
    """Alta de una vacuna en el catálogo."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.created_id: int | None = None
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
            self.created_id = vaccine_service.add_to_catalog(
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


class ApplyDialog(ManagedDialog):
    """Registro de una aplicación de vacuna."""

    def __init__(
        self,
        pets: list[Pet],
        vaccines: list[Vaccine],
        preferred_pet_id: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._pets = pets
        self._vaccines = vaccines
        self.setWindowTitle("Aplicar vacuna")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()

        self.pet_selector = DynamicEntitySelector(
            placeholder="Buscar mascota, propietario o microchip…",
            add_tooltip="Crear mascota",
        )
        self.pet_selector.set_items(self._pet_items(), selected_id=preferred_pet_id)
        self.pet_selector.set_add_enabled(
            permission_service.has_permission("PETS_WRITE"),
            "Crear mascota" if permission_service.has_permission("PETS_WRITE")
            else "Sin permiso para crear mascotas",
        )
        self.pet_selector.add_requested.connect(self._create_pet)
        form.addRow("Mascota", self.pet_selector)

        self.vaccine_selector = DynamicEntitySelector(
            placeholder="Buscar vacuna o fabricante…",
            add_tooltip="Agregar vacuna al catálogo",
        )
        self.vaccine_selector.set_items(self._vaccine_items())
        self.vaccine_selector.set_add_enabled(
            permission_service.has_permission("VACCINES_MANAGE")
        )
        self.vaccine_selector.add_requested.connect(self._create_vaccine)
        form.addRow("Vacuna", self.vaccine_selector)

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
                    pet_id=self.pet_selector.current_id(),
                    vaccine_id=self.vaccine_selector.current_id(),
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

    def _pet_items(self) -> list[SelectorItem]:
        return [
            SelectorItem(
                p.id,
                f"{p.name} ({p.owner_name})",
                " ".join(filter(None, [p.microchip_number, p.owner_name])),
            )
            for p in self._pets
        ]

    def _vaccine_items(self) -> list[SelectorItem]:
        return [
            SelectorItem(
                v.id,
                f"{v.name}{f' · {v.manufacturer}' if v.manufacturer else ''}",
                v.manufacturer or "",
            )
            for v in self._vaccines
        ]

    def _create_pet(self) -> None:
        try:
            pet = create_pet_nested(self)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        if pet is None:
            return
        self._pets.append(pet)
        self.pet_selector.set_items(self._pet_items(), selected_id=pet.id)

    def _create_vaccine(self) -> None:
        dialog = CatalogDialog(parent=self)
        if not dialog.exec() or dialog.created_id is None:
            return
        self._vaccines = vaccine_service.list_catalog()
        self.vaccine_selector.set_items(
            self._vaccine_items(), selected_id=dialog.created_id
        )
