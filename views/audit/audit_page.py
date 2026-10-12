"""Página de consulta de auditoría (estrictamente de solo lectura)."""

import json
import logging
from datetime import date

from utils.icons import set_button_icon

from PySide6.QtCore import QDate, QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from database.connection import DatabaseConnectionError
from models.audit import AuditEvent
from services import audit_service
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError
from widgets.managed_dialog import ManagedDialog

logger = logging.getLogger(__name__)

_COLUMNS = ["Fecha", "Usuario", "Entidad", "ID", "Acción"]


class AuditPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageArea")
        self._events: list[AuditEvent] = []
        self._loaded = False
        self._options_loaded = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Auditoría")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar en resultados...")
        self.search_input.setFixedWidth(240)
        self.search_input.textChanged.connect(self._apply_search)
        header.addWidget(self.search_input)
        refresh = QPushButton("Actualizar")
        set_button_icon(refresh, "refresh", color="#008FA3")
        refresh.setProperty("variant", "secondary")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        layout.addLayout(header)

        filters = QHBoxLayout()
        self.entity_combo = QComboBox()
        self.action_combo = QComboBox()
        self.user_combo = QComboBox()
        for combo, label in (
            (self.entity_combo, "Todas las entidades"),
            (self.action_combo, "Todas las acciones"),
            (self.user_combo, "Todos los usuarios"),
        ):
            combo.addItem(label, None)
            filters.addWidget(combo)
        self.date_check = QCheckBox("Filtrar fechas")
        filters.addWidget(self.date_check)
        self.from_date = QDateEdit(QDate.currentDate().addDays(-30))
        self.to_date = QDateEdit(QDate.currentDate())
        for editor in (self.from_date, self.to_date):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("dd/MM/yyyy")
            editor.setEnabled(False)
        self.date_check.toggled.connect(self.from_date.setEnabled)
        self.date_check.toggled.connect(self.to_date.setEnabled)
        filters.addWidget(self.from_date)
        filters.addWidget(self.to_date)
        apply_button = QPushButton("Aplicar filtros")
        set_button_icon(apply_button, "filter")
        apply_button.clicked.connect(self.refresh)
        filters.addWidget(apply_button)
        layout.addLayout(filters)

        self.model = QStandardItemModel(0, len(_COLUMNS))
        self.model.setHorizontalHeaderLabels(_COLUMNS)
        self.proxy = QSortFilterProxyModel(self)
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
        self.table.doubleClicked.connect(lambda _index: self._show_detail())
        layout.addWidget(self.table, stretch=1)

        footer = QHBoxLayout()
        note = QLabel("Bitácora append-only: los eventos no pueden editarse ni eliminarse.")
        note.setObjectName("versionLabel")
        footer.addWidget(note)
        footer.addStretch()
        detail = QPushButton("Ver detalle")
        set_button_icon(detail, "view", color="#008FA3")
        detail.setProperty("variant", "secondary")
        detail.clicked.connect(self._show_detail)
        footer.addWidget(detail)
        layout.addLayout(footer)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loaded:
            self.refresh()

    def refresh(self) -> None:
        try:
            if not self._options_loaded:
                self._load_options()
            filters = audit_service.AuditFilters(
                entity_type=self.entity_combo.currentData(),
                action=self.action_combo.currentData(),
                user_id=self.user_combo.currentData(),
                from_date=self._qdate(self.from_date.date()) if self.date_check.isChecked() else None,
                to_date=self._qdate(self.to_date.date()) if self.date_check.isChecked() else None,
            )
            self._events = audit_service.list_events(filters)
            self._loaded = True
        except (PermissionDeniedError, DatabaseConnectionError, ValidationError) as exc:
            QMessageBox.warning(self, "Auditoría", str(exc))
            return
        self._populate()

    def _load_options(self) -> None:
        entities, actions, users = audit_service.list_filter_options()
        for value in entities:
            self.entity_combo.addItem(value, value)
        for value in actions:
            self.action_combo.addItem(value, value)
        for user_id, name in users:
            self.user_combo.addItem(name, user_id)
        self._options_loaded = True

    def _populate(self) -> None:
        self.model.setRowCount(0)
        self.table.setSortingEnabled(False)
        for event in self._events:
            row = [
                QStandardItem(event.created_at.strftime("%d/%m/%Y %H:%M:%S")),
                QStandardItem(event.user_name or event.username or "Sistema"),
                QStandardItem(event.entity_type),
                QStandardItem(str(event.entity_id) if event.entity_id is not None else "—"),
                QStandardItem(event.action),
            ]
            row[0].setData(event.id, Qt.UserRole)
            self.model.appendRow(row)
        self.table.setSortingEnabled(True)
        self._apply_search(self.search_input.text())

    def _apply_search(self, text: str) -> None:
        self.proxy.setFilterFixedString(text.strip())

    def _selected_event(self) -> AuditEvent | None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(self, "Auditoría", "Seleccione un evento primero.")
            return None
        source = self.proxy.mapToSource(indexes[0])
        event_id = self.model.item(source.row(), 0).data(Qt.UserRole)
        return next((item for item in self._events if item.id == event_id), None)

    def _show_detail(self) -> None:
        event = self._selected_event()
        if event is not None:
            AuditDetailDialog(event, self).exec()

    @staticmethod
    def _qdate(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())


class AuditDetailDialog(ManagedDialog):
    def __init__(self, event: AuditEvent, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Evento de auditoría #{event.id}")
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        summary = QFormLayout()
        summary.addRow("Fecha:", QLabel(event.created_at.strftime("%d/%m/%Y %H:%M:%S")))
        summary.addRow("Usuario:", QLabel(event.user_name or event.username or "Sistema"))
        summary.addRow("Entidad:", QLabel(event.entity_type))
        summary.addRow("Registro:", QLabel(str(event.entity_id or "—")))
        summary.addRow("Acción:", QLabel(event.action))
        layout.addLayout(summary)
        for title, raw in (("Datos anteriores", event.old_data), ("Datos nuevos", event.new_data)):
            layout.addWidget(QLabel(title))
            editor = QPlainTextEdit(_pretty_json(raw))
            editor.setReadOnly(True)
            layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def _pretty_json(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        return raw
