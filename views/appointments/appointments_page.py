"""Página del módulo Citas: agenda por día con acciones de estado."""

import logging

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
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

from config.constants import APPOINTMENT_STATUS_DISPLAY, Colors
from database.connection import DatabaseConnectionError
from models.appointment import Appointment
from services import appointment_service
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError
from views.appointments.appointment_dialog import AppointmentDialog

logger = logging.getLogger(__name__)

_COLUMNS = ["Hora", "Mascota", "Propietario", "Motivo", "Veterinario", "Estado"]

_STATUS_COLORS = {
    "SCHEDULED": Colors.INFO,
    "CONFIRMED": Colors.PRIMARY,
    "IN_ATTENTION": Colors.WARNING,
    "COMPLETED": Colors.SUCCESS,
    "CANCELLED": Colors.ERROR,
    "NO_SHOW": Colors.MUTED,
}


class AppointmentsPage(QWidget):
    """Agenda de citas con filtros por día y estado."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageArea")
        self._appointments: list[Appointment] = []
        self._loaded = False
        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Citas")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd/MM/yyyy")
        self.date_input.dateChanged.connect(lambda _: self.refresh())
        header.addWidget(self.date_input)

        today_button = QPushButton("Hoy")
        today_button.setProperty("variant", "secondary")
        today_button.clicked.connect(
            lambda: self.date_input.setDate(QDate.currentDate())
        )
        header.addWidget(today_button)

        self.all_dates_check = QCheckBox("Todas las fechas")
        self.all_dates_check.toggled.connect(self._on_all_dates)
        header.addWidget(self.all_dates_check)

        self.status_filter = QComboBox()
        self.status_filter.addItem("Todos los estados", None)
        for code, label in APPOINTMENT_STATUS_DISPLAY.items():
            self.status_filter.addItem(label, code)
        self.status_filter.currentIndexChanged.connect(self._apply_filters)
        header.addWidget(self.status_filter)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar...")
        self.search_input.setFixedWidth(180)
        self.search_input.textChanged.connect(self._apply_filters)
        header.addWidget(self.search_input)

        self.new_button = QPushButton("＋ Nueva cita")
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
        self.table.doubleClicked.connect(lambda _: self._on_edit())
        layout.addWidget(self.table, stretch=1)

        actions = QHBoxLayout()
        actions.addStretch()
        for text, handler in [
            ("Editar", self._on_edit),
            ("Confirmar", lambda: self._on_status("CONFIRMED")),
            ("Cancelar cita", lambda: self._on_status("CANCELLED")),
            ("No asistió", lambda: self._on_status("NO_SHOW")),
        ]:
            button = QPushButton(text)
            button.setProperty("variant", "secondary")
            button.clicked.connect(handler)
            actions.addWidget(button)
        layout.addLayout(actions)

    def showEvent(self, event) -> None:  # noqa: N802 (API Qt)
        super().showEvent(event)
        if not self._loaded:
            self.refresh()

    # ---------------------------------------------------------------- Datos

    def _on_all_dates(self, checked: bool) -> None:
        self.date_input.setEnabled(not checked)
        self.refresh()

    def refresh(self) -> None:
        day = None
        if not self.all_dates_check.isChecked():
            qdate = self.date_input.date()
            day = qdate.toPython()
        try:
            self._appointments = appointment_service.list_appointments(day)
            self._loaded = True
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Citas", str(exc))
            return
        self._apply_filters()

    def _apply_filters(self) -> None:
        status = self.status_filter.currentData()
        text = self.search_input.text().strip().lower()

        self.model.setRowCount(0)
        for appt in self._appointments:
            if status is not None and appt.status != status:
                continue
            haystack = (
                f"{appt.pet_name or ''} {appt.owner_name or ''} "
                f"{appt.veterinarian_name or ''} {appt.reason}".lower()
            )
            if text and text not in haystack:
                continue

            when = appt.appointment_at.strftime(
                "%H:%M" if not self.all_dates_check.isChecked() else "%d/%m/%Y %H:%M"
            )
            estado = APPOINTMENT_STATUS_DISPLAY.get(appt.status, appt.status)
            reason = appt.reason if len(appt.reason) <= 60 else appt.reason[:57] + "..."
            row = [
                QStandardItem(when),
                QStandardItem(appt.pet_name or "—"),
                QStandardItem(appt.owner_name or "—"),
                QStandardItem(reason),
                QStandardItem(appt.veterinarian_name or "Sin asignar"),
                QStandardItem(estado),
            ]
            row[5].setForeground(
                QColor(_STATUS_COLORS.get(appt.status, Colors.TEXT_DARK))
            )
            row[0].setData(appt.id, Qt.UserRole)
            for item in row:
                item.setEditable(False)
            self.model.appendRow(row)

    def _selected_appointment(self) -> Appointment | None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(self, "Citas", "Seleccione una cita primero.")
            return None
        appt_id = self.model.item(indexes[0].row(), 0).data(Qt.UserRole)
        return next((a for a in self._appointments if a.id == appt_id), None)

    # -------------------------------------------------------------- Acciones

    def _dialog_catalogs(self):
        try:
            pets = appointment_service.list_active_pets()
            vets = appointment_service.list_veterinarians()
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Citas", str(exc))
            return None
        if not pets:
            QMessageBox.information(
                self, "Citas", "Primero registre al menos una mascota activa."
            )
            return None
        return pets, vets

    def _on_new(self) -> None:
        catalogs = self._dialog_catalogs()
        if catalogs is None:
            return
        pets, vets = catalogs
        dialog = AppointmentDialog(pets, vets, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_edit(self) -> None:
        appt = self._selected_appointment()
        if appt is None:
            return
        catalogs = self._dialog_catalogs()
        if catalogs is None:
            return
        pets, vets = catalogs
        dialog = AppointmentDialog(pets, vets, appointment=appt, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_status(self, new_status: str) -> None:
        appt = self._selected_appointment()
        if appt is None:
            return
        label = APPOINTMENT_STATUS_DISPLAY.get(new_status, new_status)
        answer = QMessageBox.question(
            self,
            "Citas",
            f"¿Marcar la cita de «{appt.pet_name}» como {label}?",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            appointment_service.change_status(appt.id, new_status)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Citas", str(exc))
            return
        self.refresh()
