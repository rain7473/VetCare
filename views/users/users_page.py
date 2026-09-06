"""Página del módulo Usuarios: listado, búsqueda y acciones."""

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

from config.constants import ROLE_DISPLAY_NAMES, Colors
from database.connection import DatabaseConnectionError
from models.user import User
from services import user_service
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError
from views.users.user_dialog import UserDialog

logger = logging.getLogger(__name__)

_COLUMNS = ["Usuario", "Nombre completo", "Rol", "Email", "Teléfono", "Estado",
            "Último acceso"]


class UsersPage(QWidget):
    """Listado de usuarios con creación, edición y activación."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageArea")
        self._users: list[User] = []
        self._loaded = False
        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Usuarios")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar usuario...")
        self.search_input.setFixedWidth(260)
        self.search_input.textChanged.connect(self._on_search)
        header.addWidget(self.search_input)

        self.new_button = QPushButton("＋ Nuevo usuario")
        self.new_button.clicked.connect(self._on_new)
        header.addWidget(self.new_button)

        layout.addLayout(header)

        self.model = QStandardItemModel(0, len(_COLUMNS))
        self.model.setHorizontalHeaderLabels(_COLUMNS)

        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)  # todas las columnas

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.doubleClicked.connect(lambda _: self._on_edit())
        layout.addWidget(self.table, stretch=1)

        actions = QHBoxLayout()
        actions.addStretch()

        self.edit_button = QPushButton("Editar")
        self.edit_button.setProperty("variant", "secondary")
        self.edit_button.clicked.connect(self._on_edit)
        actions.addWidget(self.edit_button)

        self.toggle_button = QPushButton("Activar / Desactivar")
        self.toggle_button.setProperty("variant", "secondary")
        self.toggle_button.clicked.connect(self._on_toggle_active)
        actions.addWidget(self.toggle_button)

        layout.addLayout(actions)

    def showEvent(self, event) -> None:  # noqa: N802 (API Qt)
        super().showEvent(event)
        if not self._loaded:
            self.refresh()

    # ------------------------------------------------------------------ Datos

    def refresh(self) -> None:
        try:
            self._users = user_service.list_users()
            self._loaded = True
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Usuarios", str(exc))
            return

        self.model.setRowCount(0)
        for user in self._users:
            estado = "Activo" if user.is_active else "Inactivo"
            last_login = (
                user.last_login_at.strftime("%d/%m/%Y %H:%M")
                if user.last_login_at
                else "—"
            )
            row = [
                QStandardItem(user.username),
                QStandardItem(user.full_name),
                QStandardItem(
                    ROLE_DISPLAY_NAMES.get(user.role_name or "", user.role_name or "")
                ),
                QStandardItem(user.email or "—"),
                QStandardItem(user.phone or "—"),
                QStandardItem(estado),
                QStandardItem(last_login),
            ]
            row[5].setForeground(
                QColor(Colors.SUCCESS if user.is_active else Colors.ERROR)
            )
            row[0].setData(user.id, Qt.UserRole)
            for item in row:
                item.setEditable(False)
            self.model.appendRow(row)

    def _selected_user(self) -> User | None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(self, "Usuarios", "Seleccione un usuario primero.")
            return None
        source_index = self.proxy.mapToSource(indexes[0])
        user_id = self.model.item(source_index.row(), 0).data(Qt.UserRole)
        return next((u for u in self._users if u.id == user_id), None)

    # ------------------------------------------------------------------ Acciones

    def _on_search(self, text: str) -> None:
        self.proxy.setFilterFixedString(text)

    def _load_roles(self) -> list[tuple[int, str]] | None:
        try:
            return user_service.list_roles()
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Usuarios", str(exc))
            return None

    def _on_new(self) -> None:
        roles = self._load_roles()
        if roles is None:
            return
        dialog = UserDialog(roles, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_edit(self) -> None:
        user = self._selected_user()
        if user is None:
            return
        roles = self._load_roles()
        if roles is None:
            return
        dialog = UserDialog(roles, user=user, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_toggle_active(self) -> None:
        user = self._selected_user()
        if user is None:
            return
        action = "desactivar" if user.is_active else "activar"
        answer = QMessageBox.question(
            self,
            "Usuarios",
            f"¿Desea {action} al usuario «{user.username}»?",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            user_service.set_user_active(user.id, not user.is_active)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Usuarios", str(exc))
            return
        self.refresh()
