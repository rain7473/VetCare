"""Diálogos de catálogo de áreas/espacios e ingreso hospitalario."""

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QComboBox,
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
from models.hospitalization import HospitalArea, HospitalSpace, Hospitalization
from models.pet import Pet
from models.user import User
from services import hospitalization_service
from services.hospitalization_service import (
    AreaFormData,
    HospitalizationFormData,
    SpaceFormData,
)
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError


class AreaDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nueva área de hospitalización")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()
        self.name_input = QLineEdit()
        form.addRow("Nombre", self.name_input)
        self.description_input = QTextEdit()
        self.description_input.setFixedHeight(48)
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
            hospitalization_service.create_area(
                AreaFormData(
                    name=self.name_input.text(),
                    description=self.description_input.toPlainText(),
                )
            )
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        self.accept()


class SpaceDialog(QDialog):
    def __init__(self, areas: list[HospitalArea], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nuevo espacio / jaula")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()
        self.area_combo = QComboBox()
        for area in areas:
            self.area_combo.addItem(area.name, area.id)
        form.addRow("Área", self.area_combo)
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Ej.: J-01")
        form.addRow("Código", self.code_input)
        self.description_input = QTextEdit()
        self.description_input.setFixedHeight(48)
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
            hospitalization_service.create_space(
                SpaceFormData(
                    area_id=self.area_combo.currentData(),
                    code=self.code_input.text(),
                    description=self.description_input.toPlainText(),
                )
            )
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        self.accept()


class AdmitDialog(QDialog):
    """Ingreso o edición de una hospitalización activa."""

    def __init__(
        self,
        pets: list[Pet],
        veterinarians: list[User],
        spaces: list[HospitalSpace],
        hospitalization: Hospitalization | None = None,
        preferred_pet_id: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._hospitalization = hospitalization
        self.setWindowTitle(
            "Editar hospitalización" if hospitalization else "Nuevo ingreso"
        )
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()

        self.pet_combo = QComboBox()
        selected = 0
        for index, pet in enumerate(pets):
            self.pet_combo.addItem(f"{pet.name} ({pet.owner_name})", pet.id)
            if preferred_pet_id and pet.id == preferred_pet_id:
                selected = index
            if hospitalization and pet.id == hospitalization.pet_id:
                selected = index
        if pets:
            self.pet_combo.setCurrentIndex(selected)
        self.pet_combo.setEnabled(hospitalization is None)
        form.addRow("Mascota", self.pet_combo)

        self.vet_combo = QComboBox()
        for vet in veterinarians:
            self.vet_combo.addItem(vet.full_name, vet.id)
        form.addRow("Veterinario", self.vet_combo)

        self.space_combo = QComboBox()
        self.space_combo.addItem("Sin espacio asignado", None)
        for space in spaces:
            label = f"{space.area_name} · {space.code}"
            if space.status != "AVAILABLE" and (
                hospitalization is None or space.id != hospitalization.space_id
            ):
                continue
            self.space_combo.addItem(label, space.id)
        form.addRow("Espacio / jaula", self.space_combo)

        self.admitted_input = QDateTimeEdit(QDateTime.currentDateTime())
        self.admitted_input.setCalendarPopup(True)
        self.admitted_input.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.admitted_input.setEnabled(hospitalization is None)
        form.addRow("Ingreso", self.admitted_input)

        self.reason_input = QTextEdit()
        self.reason_input.setFixedHeight(56)
        form.addRow("Motivo", self.reason_input)

        self.treatment_input = QTextEdit()
        self.treatment_input.setFixedHeight(56)
        self.treatment_input.setPlaceholderText("Plan de tratamiento (opcional)")
        form.addRow("Tratamiento", self.treatment_input)
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

        if hospitalization is not None:
            self._load(hospitalization)

    def _load(self, item: Hospitalization) -> None:
        index = self.vet_combo.findData(item.veterinarian_id)
        if index >= 0:
            self.vet_combo.setCurrentIndex(index)
        if item.space_id is not None:
            index = self.space_combo.findData(item.space_id)
            if index < 0:
                self.space_combo.addItem(
                    f"{item.area_name} · {item.space_code}", item.space_id
                )
                index = self.space_combo.findData(item.space_id)
            if index >= 0:
                self.space_combo.setCurrentIndex(index)
        self.reason_input.setPlainText(item.reason or "")
        self.treatment_input.setPlainText(item.treatment_plan or "")

    def _on_save(self) -> None:
        data = HospitalizationFormData(
            pet_id=self.pet_combo.currentData(),
            veterinarian_id=self.vet_combo.currentData(),
            space_id=self.space_combo.currentData(),
            consultation_id=(
                self._hospitalization.consultation_id
                if self._hospitalization
                else None
            ),
            admitted_at=self.admitted_input.dateTime().toPython(),
            reason=self.reason_input.toPlainText(),
            treatment_plan=self.treatment_input.toPlainText(),
        )
        try:
            if self._hospitalization is None:
                hospitalization_service.admit(data)
            else:
                hospitalization_service.update_hospitalization(
                    self._hospitalization.id, data
                )
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        self.accept()
