"""Página del módulo Propietarios: listado, búsqueda y acciones."""

import logging

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from config.constants import Colors
from database.connection import DatabaseConnectionError
from models.owner import Owner
from services import owner_service, permission_service
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError
from views.owners.owner_dialog import OwnerDialog

logger = logging.getLogger(__name__)

_COLUMNS = ["Identificación", "Nombre", "Teléfono", "Email", "Estado"]


class OwnersPage(QWidget):
    """Listado de propietarios con registro, edición y desactivación."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageArea")
        self._owners: list[Owner] = []
        self._loaded = False
        self._can_write = permission_service.has_permission("OWNERS_WRITE")
        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Propietarios")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar propietario...")
        self.search_input.setFixedWidth(260)
        self.search_input.textChanged.connect(
            lambda text: self.proxy.setFilterFixedString(text)
        )
        header.addWidget(self.search_input)

        self.new_button = QPushButton("＋ Nuevo propietario")
        self.new_button.clicked.connect(self._on_new)
        self.new_button.setVisible(self._can_write)
        header.addWidget(self.new_button)

        layout.addLayout(header)

        self.model = QStandardItemModel(0, len(_COLUMNS))
        self.model.setHorizontalHeaderLabels(_COLUMNS)

        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        if self._can_write:
            self.table.doubleClicked.connect(lambda _: self._on_edit())
        layout.addWidget(self.table, stretch=1)

        actions = QHBoxLayout()
        actions.addStretch()

        self.edit_button = QPushButton("Editar")
        self.edit_button.setProperty("variant", "secondary")
        self.edit_button.clicked.connect(self._on_edit)
        self.edit_button.setVisible(self._can_write)
        actions.addWidget(self.edit_button)

        self.toggle_button = QPushButton("Activar / Desactivar")
        self.toggle_button.setProperty("variant", "secondary")
        self.toggle_button.clicked.connect(self._on_toggle_active)
        self.toggle_button.setVisible(self._can_write)
        actions.addWidget(self.toggle_button)

        layout.addLayout(actions)

    def showEvent(self, event) -> None:  # noqa: N802 (API Qt)
        super().showEvent(event)
        if not self._loaded:
            self.refresh()

    # ---------------------------------------------------------------- Datos

    def refresh(self) -> None:
        try:
            self._owners = owner_service.list_owners()
            self._loaded = True
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Propietarios", str(exc))
            return

        self.model.setRowCount(0)
        for owner in self._owners:
            estado = "Activo" if owner.is_active else "Inactivo"
            row = [
                QStandardItem(owner.identification or "—"),
                QStandardItem(owner.full_name),
                QStandardItem(owner.phone),
                QStandardItem(owner.email or "—"),
                QStandardItem(estado),
            ]
            row[4].setForeground(
                QColor(Colors.SUCCESS if owner.is_active else Colors.ERROR)
            )
            row[0].setData(owner.id, Qt.UserRole)
            for item in row:
                item.setEditable(False)
            self.model.appendRow(row)

    def _selected_owner(self) -> Owner | None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(
                self, "Propietarios", "Seleccione un propietario primero."
            )
            return None
        source_index = self.proxy.mapToSource(indexes[0])
        owner_id = self.model.item(source_index.row(), 0).data(Qt.UserRole)
        return next((o for o in self._owners if o.id == owner_id), None)

    # -------------------------------------------------------------- Acciones

    def _on_new(self) -> None:
        dialog = OwnerDialog(parent=self)
        if dialog.exec():
            self.refresh()

    def _on_edit(self) -> None:
        owner = self._selected_owner()
        if owner is None:
            return
        dialog = OwnerDialog(owner=owner, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_toggle_active(self) -> None:
        owner = self._selected_owner()
        if owner is None:
            return
        action = "desactivar" if owner.is_active else "activar"
        answer = QMessageBox.question(
            self,
            "Propietarios",
            f"¿Desea {action} a «{owner.full_name}»?",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            owner_service.set_owner_active(owner.id, not owner.is_active)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Propietarios", str(exc))
            return
        self.refresh()
