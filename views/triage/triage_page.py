"""Página del módulo Triaje: lista del día ordenada por prioridad."""

import logging

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from config.constants import TRIAGE_PRIORITY_DISPLAY, Colors
from database.connection import DatabaseConnectionError
from models.triage import Triage
from services import triage_service
from services.permission_service import PermissionDeniedError
from views.triage.triage_dialog import TriageDialog

logger = logging.getLogger(__name__)

_COLUMNS = ["Prioridad", "Hora", "Mascota", "Propietario", "Motivo", "Registrado por"]

_PRIORITY_COLORS = {1: Colors.ERROR, 2: Colors.WARNING, 3: Colors.INFO, 4: Colors.SUCCESS}


class TriagePage(QWidget):
    """Cola de triaje del día (semáforo de prioridades)."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageArea")
        self._triages: list[Triage] = []
        self._loaded = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Triaje")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd/MM/yyyy")
        self.date_input.dateChanged.connect(lambda _: self.refresh())
        header.addWidget(self.date_input)

        self.all_dates_check = QCheckBox("Todas las fechas")
        self.all_dates_check.toggled.connect(self._on_all_dates)
        header.addWidget(self.all_dates_check)

        self.new_button = QPushButton("＋ Nuevo triaje")
        self.new_button.clicked.connect(self._on_new)
        header.addWidget(self.new_button)

        layout.addLayout(header)

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
        layout.addWidget(self.table, stretch=1)

        note = QLabel(
            "Los triajes son registros clínicos inmutables: no se editan ni se eliminan."
        )
        note.setObjectName("versionLabel")
        layout.addWidget(note)

    def showEvent(self, event) -> None:  # noqa: N802 (API Qt)
        super().showEvent(event)
        if not self._loaded:
            self.refresh()

    def _on_all_dates(self, checked: bool) -> None:
        self.date_input.setEnabled(not checked)
        self.refresh()

    def refresh(self) -> None:
        day = None
        if not self.all_dates_check.isChecked():
            day = self.date_input.date().toPython()
        try:
            self._triages = triage_service.list_triages(day)
            self._loaded = True
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Triaje", str(exc))
            return

        self.model.setRowCount(0)
        for triage in self._triages:
            when = triage.created_at.strftime(
                "%H:%M" if not self.all_dates_check.isChecked() else "%d/%m/%Y %H:%M"
            )
            reason = (
                triage.reason if len(triage.reason) <= 60 else triage.reason[:57] + "..."
            )
            row = [
                QStandardItem(
                    TRIAGE_PRIORITY_DISPLAY.get(
                        triage.priority_level, str(triage.priority_level)
                    )
                ),
                QStandardItem(when),
                QStandardItem(triage.pet_name or "—"),
                QStandardItem(triage.owner_name or "—"),
                QStandardItem(reason),
                QStandardItem(triage.recorded_by_name or "—"),
            ]
            color = _PRIORITY_COLORS.get(triage.priority_level, Colors.TEXT_DARK)
            row[0].setForeground(QColor(color))
            row[0].setData(triage.id, Qt.UserRole)
            for item in row:
                item.setEditable(False)
            self.model.appendRow(row)

    def _on_new(self) -> None:
        try:
            pets = triage_service.list_active_pets()
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Triaje", str(exc))
            return
        if not pets:
            QMessageBox.information(
                self, "Triaje", "Primero registre al menos una mascota activa."
            )
            return
        dialog = TriageDialog(pets, parent=self)
        if dialog.exec():
            self.refresh()
