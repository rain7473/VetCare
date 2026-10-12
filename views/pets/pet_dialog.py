"""Diálogo de registro/edición de mascotas."""

import logging

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from config.constants import PET_SEX_DISPLAY, PET_STATUS_DISPLAY
from database.connection import DatabaseConnectionError
from models.owner import Owner
from models.pet import Pet
from services import owner_service, permission_service, pet_service
from services.permission_service import PermissionDeniedError
from services.pet_service import PetFormData
from utils.images import resolve_photo
from utils.icons import pixmap, set_button_icon
from utils.validators import ValidationError
from views.owners.owner_dialog import OwnerDialog
from widgets.dynamic_selector import DynamicEntitySelector, SelectorItem
from widgets.managed_dialog import ManagedDialog

logger = logging.getLogger(__name__)


class PetDialog(ManagedDialog):
    """Formulario modal para crear o editar una mascota."""

    def __init__(
        self,
        owners: list[Owner],
        species: list[tuple[int, str]],
        pet: Pet | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._owners = owners
        self._species = species
        self._pet = pet
        self.created_id: int | None = None
        self._photo_source = ""
        self.setWindowTitle("Editar mascota" if pet else "Nueva mascota")
        self.setMinimumWidth(560)
        self._build_ui()
        if pet is not None:
            self._load_pet()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.owner_selector = DynamicEntitySelector(
            placeholder="Buscar por nombre, identificación o teléfono…",
            add_tooltip="Crear propietario",
        )
        self.owner_selector.set_items(self._owner_items())
        self.owner_selector.set_add_enabled(
            permission_service.has_permission("OWNERS_WRITE"),
            "Crear propietario" if permission_service.has_permission("OWNERS_WRITE")
            else "Sin permiso para crear propietarios",
        )
        self.owner_selector.add_requested.connect(self._create_owner)
        form.addRow("Propietario", self.owner_selector)

        self.name_input = QLineEdit()
        form.addRow("Nombre", self.name_input)

        self.species_selector = DynamicEntitySelector(
            placeholder="Buscar especie…",
            add_tooltip="Crear especie",
        )
        self.species_selector.set_items(
            [SelectorItem(species_id, name) for species_id, name in self._species]
        )
        self.species_selector.set_add_enabled(
            False, "Las especies se administran como catálogo clínico"
        )
        self.species_selector.selection_changed.connect(self._reload_breeds)
        form.addRow("Especie", self.species_selector)

        self.breed_selector = DynamicEntitySelector(
            placeholder="Buscar raza…",
            add_tooltip="Crear raza",
            allow_empty=True,
            empty_label="— Sin raza —",
        )
        self.breed_selector.add_requested.connect(self._create_breed)
        form.addRow("Raza", self.breed_selector)

        self.sex_combo = QComboBox()
        for code, label in PET_SEX_DISPLAY.items():
            self.sex_combo.addItem(label, code)
        form.addRow("Sexo", self.sex_combo)

        birth_row = QHBoxLayout()
        self.birth_check = QCheckBox("Conocida")
        self.birth_check.setChecked(True)
        self.birth_check.toggled.connect(self._on_birth_toggle)
        birth_row.addWidget(self.birth_check)

        self.birth_input = QDateEdit(QDate.currentDate())
        self.birth_input.setCalendarPopup(True)
        self.birth_input.setMaximumDate(QDate.currentDate())
        birth_row.addWidget(self.birth_input)

        birth_row.addSpacing(10)
        birth_row.addWidget(QLabel("Edad aprox. (meses):"))
        self.age_spin = QSpinBox()
        self.age_spin.setRange(-1, 600)
        self.age_spin.setValue(-1)
        self.age_spin.setSpecialValueText("—")
        self.age_spin.setEnabled(False)
        birth_row.addWidget(self.age_spin)
        birth_row.addStretch()
        form.addRow("Nacimiento", birth_row)

        self.color_input = QLineEdit()
        self.color_input.setPlaceholderText("Opcional")
        form.addRow("Color", self.color_input)

        self.microchip_input = QLineEdit()
        self.microchip_input.setPlaceholderText("Opcional (único)")
        form.addRow("Microchip", self.microchip_input)

        self.blood_input = QLineEdit()
        self.blood_input.setPlaceholderText("Opcional")
        form.addRow("Tipo de sangre", self.blood_input)

        self.features_input = QTextEdit()
        self.features_input.setPlaceholderText("Opcional")
        self.features_input.setFixedHeight(48)
        form.addRow("Características", self.features_input)

        self.allergies_input = QTextEdit()
        self.allergies_input.setPlaceholderText("Opcional")
        self.allergies_input.setFixedHeight(48)
        form.addRow("Alergias", self.allergies_input)

        self.chronic_input = QTextEdit()
        self.chronic_input.setPlaceholderText("Opcional")
        self.chronic_input.setFixedHeight(48)
        form.addRow("Cond. crónicas", self.chronic_input)

        photo_row = QHBoxLayout()
        self.photo_preview = QLabel()
        self.photo_preview.setPixmap(pixmap("pets", 30, "#79B6C5"))
        self.photo_preview.setAlignment(Qt.AlignCenter)
        self.photo_preview.setFixedSize(72, 72)
        self.photo_preview.setAlignment(Qt.AlignCenter)
        self.photo_preview.setObjectName("photoPreview")
        photo_row.addWidget(self.photo_preview)

        photo_button = QPushButton("Seleccionar foto...")
        set_button_icon(photo_button, "camera", color="#008FA3")
        photo_button.setProperty("variant", "secondary")
        photo_button.clicked.connect(self._on_pick_photo)
        photo_row.addWidget(photo_button)
        photo_row.addStretch()
        form.addRow("Fotografía", photo_row)

        self.status_combo = QComboBox()
        for code, label in PET_STATUS_DISPLAY.items():
            self.status_combo.addItem(label, code)
        if self._pet is None:
            self.status_combo.setVisible(False)
            form.addRow("", self.status_combo)
        else:
            form.addRow("Estado", self.status_combo)

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

        self._reload_breeds()

    # ------------------------------------------------------------- Helpers

    def _on_birth_toggle(self, known: bool) -> None:
        self.birth_input.setEnabled(known)
        self.age_spin.setEnabled(not known)

    def _reload_breeds(self) -> None:
        species_id = self.species_selector.current_id()
        current_id = self.breed_selector.current_id()
        if species_id is None:
            self.breed_selector.set_items([])
            return
        try:
            breeds = pet_service.list_breeds(species_id)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            logger.warning("No se pudieron cargar razas: %s", exc)
            breeds = []
        selected_id = current_id
        if self._pet and self._pet.species_id == species_id:
            selected_id = self._pet.breed_id
        self.breed_selector.set_items(
            [SelectorItem(breed_id, name) for breed_id, name in breeds],
            selected_id=selected_id,
        )

    def _on_pick_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar foto", "", "Imágenes (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            self._photo_source = path
            self._set_preview(path)

    def _set_preview(self, path: str) -> None:
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self.photo_preview.setPixmap(
                pixmap.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def _load_pet(self) -> None:
        pet = self._pet
        if not self.owner_selector.select_id(pet.owner_id):
            self.owner_selector.set_items(
                self._owner_items()
                + [SelectorItem(pet.owner_id, pet.owner_name or "(propietario)")],
                selected_id=pet.owner_id,
            )

        self.name_input.setText(pet.name)
        self.species_selector.select_id(pet.species_id)
        self._reload_breeds()

        sex_index = self.sex_combo.findData(pet.sex)
        if sex_index >= 0:
            self.sex_combo.setCurrentIndex(sex_index)

        if pet.birth_date:
            born = pet.birth_date
            self.birth_check.setChecked(True)
            self.birth_input.setDate(QDate(born.year, born.month, born.day))
        else:
            self.birth_check.setChecked(False)
            if pet.approximate_age_months is not None:
                self.age_spin.setValue(pet.approximate_age_months)

        self.color_input.setText(pet.color or "")
        self.microchip_input.setText(pet.microchip_number or "")
        self.blood_input.setText(pet.blood_type or "")
        self.features_input.setPlainText(pet.distinctive_features or "")
        self.allergies_input.setPlainText(pet.allergies or "")
        self.chronic_input.setPlainText(pet.chronic_conditions or "")

        photo = resolve_photo(pet.photo_url)
        if photo:
            self._set_preview(str(photo))

        st_index = self.status_combo.findData(pet.status)
        if st_index >= 0:
            self.status_combo.setCurrentIndex(st_index)

    # -------------------------------------------------------------- Guardar

    def _form_data(self) -> PetFormData:
        birth = None
        age = None
        if self.birth_check.isChecked():
            qdate = self.birth_input.date()
            birth = qdate.toPython()
        elif self.age_spin.value() >= 0:
            age = self.age_spin.value()

        return PetFormData(
            owner_id=self.owner_selector.current_id(),
            species_id=self.species_selector.current_id(),
            breed_name=(
                self.breed_selector.combo.currentText()
                if self.breed_selector.current_id() is not None
                else ""
            ),
            name=self.name_input.text(),
            sex=self.sex_combo.currentData(),
            birth_date=birth,
            approximate_age_months=age,
            color=self.color_input.text(),
            distinctive_features=self.features_input.toPlainText(),
            microchip_number=self.microchip_input.text(),
            blood_type=self.blood_input.text(),
            allergies=self.allergies_input.toPlainText(),
            chronic_conditions=self.chronic_input.toPlainText(),
            photo_source=self._photo_source,
            status=self.status_combo.currentData() or "ACTIVE",
        )

    def _on_save(self) -> None:
        try:
            if self._pet is None:
                self.created_id = pet_service.create_pet(self._form_data())
            else:
                pet_service.update_pet(self._pet.id, self._form_data())
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        except Exception:
            logger.exception("Error inesperado al guardar la mascota")
            self.error_label.setText("Ocurrió un error inesperado al guardar.")
            self.error_label.setVisible(True)
            return
        self.accept()

    def _owner_items(self) -> list[SelectorItem]:
        return [
            SelectorItem(
                owner.id,
                owner.full_name,
                " ".join(
                    filter(
                        None,
                        [owner.identification, owner.phone, owner.secondary_phone, owner.email],
                    )
                ),
            )
            for owner in self._owners
        ]

    def _create_owner(self) -> None:
        dialog = OwnerDialog(parent=self)
        if not dialog.exec() or dialog.created_id is None:
            return
        owner = owner_service.get_owner(dialog.created_id)
        if owner is None:
            return
        self._owners.append(owner)
        self.owner_selector.set_items(self._owner_items(), selected_id=owner.id)

    def _create_breed(self) -> None:
        species_id = self.species_selector.current_id()
        if species_id is None:
            self.error_label.setText("Seleccione una especie antes de crear la raza.")
            self.error_label.setVisible(True)
            return
        name, accepted = QInputDialog.getText(self, "Nueva raza", "Nombre de la raza:")
        if not accepted or not name.strip():
            return
        try:
            breed_id = pet_service.create_breed(species_id, name)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        self._reload_breeds()
        self.breed_selector.select_id(breed_id)
