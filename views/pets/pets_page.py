"""Página del módulo Mascotas: listado + perfil del paciente (maestro-detalle)."""

import logging

import oracledb

from utils.icons import set_button_icon

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from config.constants import PET_STATUS_DISPLAY, Colors
from database.connection import DatabaseConnectionError
from models.pet import Pet
from services import permission_service, pet_profile_service, pet_service
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError
from views.pets.digital_card_dialog import DigitalCardDialog
from views.pets.pet_dialog import PetDialog
from views.pets.pet_profile_panel import PetProfilePanel

logger = logging.getLogger(__name__)

_COLUMNS = ["Nombre", "Especie", "Propietario", "Estado"]

_STATUS_COLORS = {
    "ACTIVE": Colors.SUCCESS,
    "DECEASED": Colors.MUTED,
    "INACTIVE": Colors.ERROR,
}


class PetsPage(QWidget):
    """Listado de mascotas con panel de perfil del paciente."""

    open_consultation_requested = Signal(int)
    open_history_requested = Signal(int)
    open_vaccination_requested = Signal(int)

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

        self.new_button = QPushButton("Nueva mascota", self)
        set_button_icon(self.new_button, "add")
        self.new_button.clicked.connect(self._on_new)
        header.addWidget(self.new_button)
        self.new_button.setVisible(self._can_write)

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
        self.edit_button = QPushButton("Editar", self)
        set_button_icon(self.edit_button, "edit", color="#008FA3")
        self.edit_button.setProperty("variant", "secondary")
        self.edit_button.clicked.connect(self._on_edit)
        actions.addWidget(self.edit_button)
        self.edit_button.setVisible(self._can_write)

        self.status_button = QPushButton("Cambiar estado", self)
        set_button_icon(self.status_button, "inactive", color="#008FA3")
        self.status_button.setProperty("variant", "secondary")
        status_menu = QMenu(self.status_button)
        for code, label in PET_STATUS_DISPLAY.items():
            action = status_menu.addAction(label)
            action.triggered.connect(
                lambda _=False, c=code: self._on_change_status(c)
            )
        self.status_button.setMenu(status_menu)
        actions.addWidget(self.status_button)
        self.status_button.setVisible(self._can_write)
        left.addLayout(actions)

        body.addLayout(left, stretch=11)

        # ------------------------------ Derecha: perfil
        body.addWidget(self._build_profile_panel(), stretch=9)
        layout.addLayout(body, stretch=1)

    def _build_profile_panel(self) -> QWidget:
        can_consult = permission_service.has_permission("CONSULTATIONS_WRITE")
        can_history = permission_service.has_permission("CONSULTATIONS_READ")
        can_vaccine = permission_service.has_permission("VACCINES_MANAGE")
        self.profile_panel = PetProfilePanel(
            can_write=self._can_write,
            can_consult=can_consult,
            can_history=can_history,
            can_vaccinate=can_vaccine,
        )
        self.profile_panel.edit_requested.connect(self._on_edit)
        self.profile_panel.photo_requested.connect(self._on_pick_photo)
        self.profile_panel.consultation_requested.connect(self._on_new_consultation)
        self.profile_panel.history_requested.connect(self._on_view_history)
        self.profile_panel.vaccination_requested.connect(self._on_vaccinate)
        self.profile_panel.card_requested.connect(self._on_digital_card)
        return self.profile_panel

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
        selected_id = self._selected.id if self._selected else None
        text = self.search_input.text().strip().lower()
        species_id = self.species_filter.currentData()
        status = self.status_filter.currentData()

        self.table.selectionModel().blockSignals(True)
        self.model.setRowCount(0)
        selected_row = None
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
            if pet.id == selected_id:
                selected_row = self.model.rowCount() - 1

        if selected_row is not None:
            self.table.selectRow(selected_row)
        self.table.selectionModel().blockSignals(False)
        self._on_selection()

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
        data = None
        if pet is not None:
            try:
                data = pet_profile_service.load_profile(pet.id)
            except (PermissionDeniedError, DatabaseConnectionError, oracledb.Error):
                logger.exception("No se pudo cargar el perfil clínico de la mascota %s", pet.id)
                QMessageBox.warning(self, "Mascotas", "No se pudieron cargar los datos clínicos del perfil.")
        self.profile_panel.set_pet(pet, data)

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

    def _on_digital_card(self) -> None:
        if self._selected is None:
            QMessageBox.information(self, "Mascotas", "Seleccione una mascota primero.")
            return
        DigitalCardDialog(self._selected.id, parent=self).exec()

    def _on_vaccinate(self) -> None:
        if self._selected is None:
            QMessageBox.information(self, "Mascotas", "Seleccione una mascota primero.")
            return
        self.open_vaccination_requested.emit(self._selected.id)

    def _on_new_consultation(self) -> None:
        if self._selected is None:
            QMessageBox.information(self, "Mascotas", "Seleccione una mascota primero.")
            return
        self.open_consultation_requested.emit(self._selected.id)

    def _on_view_history(self) -> None:
        if self._selected is None:
            QMessageBox.information(self, "Mascotas", "Seleccione una mascota primero.")
            return
        self.open_history_requested.emit(self._selected.id)

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

    def _on_pick_photo(self) -> None:
        if self._selected is None or not self._can_write:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Cambiar fotografía", "", "Imágenes (*.png *.jpg *.jpeg *.webp)"
        )
        if not path:
            return
        try:
            pet_service.update_pet_photo(self._selected.id, path)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError, oracledb.Error) as exc:
            logger.exception("No se pudo cambiar la fotografía de la mascota")
            QMessageBox.warning(self, "Mascotas", str(exc) if not isinstance(exc, oracledb.Error) else "No se pudo guardar la fotografía.")
            return
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
