"""Página del módulo Mascotas: listado + perfil del paciente (maestro-detalle)."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from config.constants import PET_SEX_DISPLAY, PET_STATUS_DISPLAY, Colors
from database.connection import DatabaseConnectionError
from models.pet import Pet
from services import permission_service, pet_service
from services.permission_service import PermissionDeniedError
from utils.images import resolve_photo
from utils.validators import ValidationError
from views.pets.pet_dialog import PetDialog

logger = logging.getLogger(__name__)

_COLUMNS = ["Nombre", "Especie", "Propietario", "Estado"]

_STATUS_COLORS = {
    "ACTIVE": Colors.SUCCESS,
    "DECEASED": Colors.MUTED,
    "INACTIVE": Colors.ERROR,
}


class PetsPage(QWidget):
    """Listado de mascotas con panel de perfil del paciente."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageArea")
        self._pets: list[Pet] = []
        self._selected: Pet | None = None
        self._loaded = False
        self._can_write = permission_service.has_permission("PETS_WRITE")
        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Mascotas")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar mascota o propietario...")
        self.search_input.setFixedWidth(240)
        self.search_input.textChanged.connect(self._apply_filters)
        header.addWidget(self.search_input)

        self.species_filter = QComboBox()
        self.species_filter.addItem("Todas las especies", None)
        self.species_filter.currentIndexChanged.connect(self._apply_filters)
        header.addWidget(self.species_filter)

        self.status_filter = QComboBox()
        self.status_filter.addItem("Todos los estados", None)
        for code, label in PET_STATUS_DISPLAY.items():
            self.status_filter.addItem(label, code)
        self.status_filter.currentIndexChanged.connect(self._apply_filters)
        header.addWidget(self.status_filter)

        self.new_button = QPushButton("＋ Nueva mascota")
        self.new_button.clicked.connect(self._on_new)
        self.new_button.setVisible(self._can_write)
        header.addWidget(self.new_button)

        layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)

        # ------------------------------ Izquierda: listado
        left = QVBoxLayout()
        self.model = QStandardItemModel(0, len(_COLUMNS))
        self.model.setHorizontalHeaderLabels(_COLUMNS)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.selectionModel().selectionChanged.connect(self._on_selection)
        if self._can_write:
            self.table.doubleClicked.connect(lambda _: self._on_edit())
        left.addWidget(self.table)

        actions = QHBoxLayout()
        actions.addStretch()
        self.edit_button = QPushButton("Editar")
        self.edit_button.setProperty("variant", "secondary")
        self.edit_button.clicked.connect(self._on_edit)
        self.edit_button.setVisible(self._can_write)
        actions.addWidget(self.edit_button)

        self.status_button = QPushButton("Cambiar estado")
        self.status_button.setProperty("variant", "secondary")
        self.status_button.setVisible(self._can_write)
        status_menu = QMenu(self.status_button)
        for code, label in PET_STATUS_DISPLAY.items():
            action = status_menu.addAction(label)
            action.triggered.connect(
                lambda _=False, c=code: self._on_change_status(c)
            )
        self.status_button.setMenu(status_menu)
        actions.addWidget(self.status_button)
        left.addLayout(actions)

        body.addLayout(left, stretch=11)

        # ------------------------------ Derecha: perfil
        body.addWidget(self._build_profile_panel(), stretch=9)
        layout.addLayout(body, stretch=1)

    def _build_profile_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        card = QFrame()
        card.setProperty("card", True)
        scroll.setWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.photo_label = QLabel("🐾")
        self.photo_label.setObjectName("photoPreview")
        self.photo_label.setFixedSize(96, 96)
        self.photo_label.setAlignment(Qt.AlignCenter)
        top.addWidget(self.photo_label)

        name_box = QVBoxLayout()
        self.pet_name_label = QLabel("Seleccione una mascota")
        self.pet_name_label.setObjectName("profileName")
        name_box.addWidget(self.pet_name_label)
        self.pet_breed_label = QLabel("")
        self.pet_breed_label.setObjectName("screenSubtitle")
        name_box.addWidget(self.pet_breed_label)
        self.pet_status_label = QLabel("")
        name_box.addWidget(self.pet_status_label)
        name_box.addStretch()
        top.addLayout(name_box)
        top.addStretch()
        layout.addLayout(top)

        form = QFormLayout()
        form.setVerticalSpacing(8)
        self._detail_labels: dict[str, QLabel] = {}
        for key, label in [
            ("owner", "Propietario"),
            ("sex_age", "Sexo / Edad"),
            ("color", "Color"),
            ("microchip", "Microchip"),
            ("blood", "Tipo de sangre"),
            ("allergies", "Alergias"),
            ("chronic", "Cond. crónicas"),
            ("features", "Características"),
            ("last_consultation", "Última consulta"),
            ("next_vaccine", "Próxima vacuna"),
        ]:
            value = QLabel("—")
            value.setWordWrap(True)
            self._detail_labels[key] = value
            form.addRow(f"{label}:", value)
        layout.addLayout(form)
        layout.addStretch()

        quick = QHBoxLayout()
        for text, tooltip in [
            ("Nueva consulta", "Disponible en el Objetivo 11"),
            ("Ver historial", "Disponible en el Objetivo 11"),
            ("Vacunar", "Disponible en el Objetivo 14"),
        ]:
            button = QPushButton(text)
            button.setEnabled(False)
            button.setToolTip(tooltip)
            quick.addWidget(button)
        layout.addLayout(quick)

        return scroll

    def showEvent(self, event) -> None:  # noqa: N802 (API Qt)
        super().showEvent(event)
        if not self._loaded:
            self.refresh()

    # ---------------------------------------------------------------- Datos

    def refresh(self) -> None:
        try:
            self._pets = pet_service.list_pets()
            species = pet_service.list_species()
            self._loaded = True
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Mascotas", str(exc))
            return

        current = self.species_filter.currentData()
        self.species_filter.blockSignals(True)
        self.species_filter.clear()
        self.species_filter.addItem("Todas las especies", None)
        for species_id, name in species:
            self.species_filter.addItem(name, species_id)
        index = self.species_filter.findData(current)
        self.species_filter.setCurrentIndex(index if index >= 0 else 0)
        self.species_filter.blockSignals(False)

        self._apply_filters()

    def _apply_filters(self) -> None:
        text = self.search_input.text().strip().lower()
        species_id = self.species_filter.currentData()
        status = self.status_filter.currentData()

        self.model.setRowCount(0)
        for pet in self._pets:
            if species_id is not None and pet.species_id != species_id:
                continue
            if status is not None and pet.status != status:
                continue
            haystack = f"{pet.name} {pet.owner_name or ''}".lower()
            if text and text not in haystack:
                continue

            estado = PET_STATUS_DISPLAY.get(pet.status, pet.status)
            row = [
                QStandardItem(pet.name),
                QStandardItem(pet.species_name or "—"),
                QStandardItem(pet.owner_name or "—"),
                QStandardItem(estado),
            ]
            row[3].setForeground(
                QColor(_STATUS_COLORS.get(pet.status, Colors.TEXT_DARK))
            )
            row[0].setData(pet.id, Qt.UserRole)
            for item in row:
                item.setEditable(False)
            self.model.appendRow(row)

        self._show_pet(None)

    # ------------------------------------------------------------ Selección

    def _on_selection(self, *_args) -> None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            self._show_pet(None)
            return
        pet_id = self.model.item(indexes[0].row(), 0).data(Qt.UserRole)
        pet = next((p for p in self._pets if p.id == pet_id), None)
        self._show_pet(pet)

    def _show_pet(self, pet: Pet | None) -> None:
        self._selected = pet
        if pet is None:
            self.pet_name_label.setText("Seleccione una mascota")
            self.pet_breed_label.setText("")
            self.pet_status_label.setText("")
            self.photo_label.setText("🐾")
            self.photo_label.setPixmap(QPixmap())
            for label in self._detail_labels.values():
                label.setText("—")
            return

        self.pet_name_label.setText(pet.name)
        breed = pet.breed_name or "Sin raza definida"
        self.pet_breed_label.setText(f"{pet.species_name} · {breed}")
        estado = PET_STATUS_DISPLAY.get(pet.status, pet.status)
        color = _STATUS_COLORS.get(pet.status, Colors.TEXT_DARK)
        self.pet_status_label.setText(estado)
        self.pet_status_label.setStyleSheet(f"color: {color}; font-weight: 700;")

        photo = resolve_photo(pet.photo_url)
        if photo:
            pixmap = QPixmap(str(photo))
            self.photo_label.setPixmap(
                pixmap.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.photo_label.setPixmap(QPixmap())
            self.photo_label.setText("🐾")

        sex = PET_SEX_DISPLAY.get(pet.sex, pet.sex)
        self._detail_labels["owner"].setText(pet.owner_name or "—")
        self._detail_labels["sex_age"].setText(f"{sex} · {pet.age_text()}")
        self._detail_labels["color"].setText(pet.color or "—")
        self._detail_labels["microchip"].setText(pet.microchip_number or "—")
        self._detail_labels["blood"].setText(pet.blood_type or "—")
        self._detail_labels["allergies"].setText(pet.allergies or "Sin alergias registradas")
        self._detail_labels["chronic"].setText(
            pet.chronic_conditions or "Sin condiciones registradas"
        )
        self._detail_labels["features"].setText(pet.distinctive_features or "—")
        self._detail_labels["last_consultation"].setText("— (Objetivo 11)")
        self._detail_labels["next_vaccine"].setText("— (Objetivo 14)")

    # -------------------------------------------------------------- Acciones

    def _dialog_catalogs(self):
        try:
            owners = pet_service.list_active_owners()
            species = pet_service.list_species()
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Mascotas", str(exc))
            return None
        if not owners:
            QMessageBox.information(
                self,
                "Mascotas",
                "Primero registre al menos un propietario activo.",
            )
            return None
        return owners, species

    def _on_new(self) -> None:
        catalogs = self._dialog_catalogs()
        if catalogs is None:
            return
        owners, species = catalogs
        dialog = PetDialog(owners, species, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_edit(self) -> None:
        if self._selected is None:
            QMessageBox.information(self, "Mascotas", "Seleccione una mascota primero.")
            return
        catalogs = self._dialog_catalogs()
        if catalogs is None:
            return
        owners, species = catalogs
        dialog = PetDialog(owners, species, pet=self._selected, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_change_status(self, status: str) -> None:
        if self._selected is None:
            QMessageBox.information(self, "Mascotas", "Seleccione una mascota primero.")
            return
        label = PET_STATUS_DISPLAY.get(status, status)
        answer = QMessageBox.question(
            self,
            "Mascotas",
            f"¿Cambiar el estado de «{self._selected.name}» a {label}?",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            pet_service.set_pet_status(self._selected.id, status)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Mascotas", str(exc))
            return
        self.refresh()
