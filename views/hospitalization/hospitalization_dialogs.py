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
from services import hospitalization_service, permission_service
from services.hospitalization_service import (
    AreaFormData,
    HospitalizationFormData,
    SpaceFormData,
)
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError
from views.entity_creation import create_pet_nested, create_veterinarian_nested
from widgets.dynamic_selector import DynamicEntitySelector, SelectorItem
from widgets.managed_dialog import ManagedDialog


class AreaDialog(ManagedDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.created_id: int | None = None
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
            self.created_id = hospitalization_service.create_area(
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


class SpaceDialog(ManagedDialog):
    def __init__(self, areas: list[HospitalArea], parent=None) -> None:
        super().__init__(parent)
        self._areas = areas
        self.created_id: int | None = None
        self.setWindowTitle("Nuevo espacio / jaula")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()
        self.area_selector = DynamicEntitySelector(
            placeholder="Buscar área…",
            add_tooltip="Crear área",
        )
        self.area_selector.set_items(self._area_items())
        self.area_selector.set_add_enabled(
            permission_service.has_permission("HOSPITAL_MANAGE")
        )
        self.area_selector.add_requested.connect(self._create_area)
        form.addRow("Área", self.area_selector)
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
            self.created_id = hospitalization_service.create_space(
                SpaceFormData(
                    area_id=self.area_selector.current_id(),
                    code=self.code_input.text(),
                    description=self.description_input.toPlainText(),
                )
            )
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        self.accept()

    def _area_items(self) -> list[SelectorItem]:
        return [SelectorItem(a.id, a.name, a.description or "") for a in self._areas]

    def _create_area(self) -> None:
        dialog = AreaDialog(parent=self)
        if not dialog.exec() or dialog.created_id is None:
            return
        self._areas = hospitalization_service.list_areas()
        self.area_selector.set_items(
            self._area_items(), selected_id=dialog.created_id
        )


class AdmitDialog(ManagedDialog):
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
        self._pets = pets
        self._veterinarians = veterinarians
        self._spaces = spaces
        self._hospitalization = hospitalization
        self.setWindowTitle(
            "Editar hospitalización" if hospitalization else "Nuevo ingreso"
        )
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()

        selected_pet_id = (
            hospitalization.pet_id if hospitalization else preferred_pet_id
        )
        self.pet_selector = DynamicEntitySelector(
            placeholder="Buscar mascota, propietario o microchip…",
            add_tooltip="Crear mascota",
        )
        self.pet_selector.set_items(self._pet_items(), selected_id=selected_pet_id)
        self.pet_selector.setEnabled(hospitalization is None)
        self.pet_selector.set_add_enabled(
            hospitalization is None and permission_service.has_permission("PETS_WRITE")
        )
        self.pet_selector.add_requested.connect(self._create_pet)
        form.addRow("Mascota", self.pet_selector)

        self.vet_selector = DynamicEntitySelector(
            placeholder="Buscar veterinario…",
            add_tooltip="Crear usuario veterinario",
        )
        self.vet_selector.set_items(self._vet_items())
        self.vet_selector.set_add_enabled(
            permission_service.has_permission("USERS_MANAGE"),
            "Crear veterinario" if permission_service.has_permission("USERS_MANAGE")
            else "Sin permiso para crear usuarios",
        )
        self.vet_selector.add_requested.connect(self._create_veterinarian)
        form.addRow("Veterinario", self.vet_selector)

        self.space_selector = DynamicEntitySelector(
            placeholder="Buscar área o espacio…",
            add_tooltip="Crear espacio / jaula",
            allow_empty=True,
            empty_label="Sin espacio asignado",
        )
        self.space_selector.set_items(
            self._space_items(),
            selected_id=hospitalization.space_id if hospitalization else None,
        )
        self.space_selector.set_add_enabled(
            permission_service.has_permission("HOSPITAL_MANAGE")
        )
        self.space_selector.add_requested.connect(self._create_space)
        form.addRow("Espacio / jaula", self.space_selector)

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
        self.vet_selector.select_id(item.veterinarian_id)
        if item.space_id is not None and not self.space_selector.select_id(item.space_id):
            self.space_selector.set_items(
                self._space_items()
                + [SelectorItem(item.space_id, f"{item.area_name} · {item.space_code}")],
                selected_id=item.space_id,
            )
        self.reason_input.setPlainText(item.reason or "")
        self.treatment_input.setPlainText(item.treatment_plan or "")

    def _on_save(self) -> None:
        data = HospitalizationFormData(
            pet_id=self.pet_selector.current_id(),
            veterinarian_id=self.vet_selector.current_id(),
            space_id=self.space_selector.current_id(),
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

    def _pet_items(self) -> list[SelectorItem]:
        return [
            SelectorItem(
                p.id,
                f"{p.name} ({p.owner_name})",
                " ".join(filter(None, [p.microchip_number, p.owner_name])),
            )
            for p in self._pets
        ]

    def _space_items(self) -> list[SelectorItem]:
        return [
            SelectorItem(s.id, f"{s.area_name} · {s.code}", s.description or "")
            for s in self._spaces
            if s.status == "AVAILABLE"
            or (self._hospitalization and s.id == self._hospitalization.space_id)
        ]

    def _vet_items(self) -> list[SelectorItem]:
        return [
            SelectorItem(v.id, v.full_name, v.username)
            for v in self._veterinarians
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

    def _create_space(self) -> None:
        try:
            areas = hospitalization_service.list_areas()
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        dialog = SpaceDialog(areas, parent=self)
        if not dialog.exec() or dialog.created_id is None:
            return
        self._spaces = hospitalization_service.list_spaces()
        self.space_selector.set_items(
            self._space_items(), selected_id=dialog.created_id
        )

    def _create_veterinarian(self) -> None:
        try:
            vet = create_veterinarian_nested(self)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        if vet is None:
            return
        self._veterinarians.append(vet)
        self.vet_selector.set_items(self._vet_items(), selected_id=vet.id)
