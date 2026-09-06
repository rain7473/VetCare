"""Página de hospitalización: ingresos activos, áreas y espacios."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from config.constants import HOSPITALIZATION_STATUS_DISPLAY, Colors
from database.connection import DatabaseConnectionError
from models.hospitalization import Hospitalization
from services import hospitalization_service
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError
from views.hospitalization.hospitalization_dialogs import (
    AdmitDialog,
    AreaDialog,
    SpaceDialog,
)
from views.hospitalization.monitoring_dialog import MonitoringDialog, VitalRangeDialog

_COLUMNS = [
    "Ingreso",
    "Mascota",
    "Propietario",
    "Área / Espacio",
    "Veterinario",
    "Motivo",
    "Estado",
]

_STATUS_COLORS = {
    "ADMITTED": Colors.INFO,
    "OBSERVATION": Colors.WARNING,
    "CRITICAL": Colors.ERROR,
    "DISCHARGED": Colors.SUCCESS,
    "TRANSFERRED": Colors.MUTED,
}


class HospitalizationPage(QWidget):
    """Panel de pacientes hospitalizados."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageArea")
        self._items: list[Hospitalization] = []
        self._loaded = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Hospitalización")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar paciente...")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self._apply_filters)
        header.addWidget(self.search_input)

        self.all_check = QCheckBox("Incluir altas")
        self.all_check.toggled.connect(lambda _: self.refresh())
        header.addWidget(self.all_check)

        area_btn = QPushButton("＋ Área")
        area_btn.setProperty("variant", "secondary")
        area_btn.clicked.connect(self._on_area)
        header.addWidget(area_btn)

        space_btn = QPushButton("＋ Espacio")
        space_btn.setProperty("variant", "secondary")
        space_btn.clicked.connect(self._on_space)
        header.addWidget(space_btn)

        admit_btn = QPushButton("＋ Nuevo ingreso")
        admit_btn.clicked.connect(self._on_admit)
        header.addWidget(admit_btn)
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
            ("Monitoreo", self._on_monitoring),
            ("Rangos vitales", self._on_ranges),
            ("Observación", lambda: self._on_status("OBSERVATION")),
            ("Crítico", lambda: self._on_status("CRITICAL")),
            ("Dar de alta", lambda: self._on_status("DISCHARGED")),
            ("Transferir", lambda: self._on_status("TRANSFERRED")),
        ]:
            button = QPushButton(text)
            button.setProperty("variant", "secondary")
            button.clicked.connect(handler)
            actions.addWidget(button)
        layout.addLayout(actions)

        note = QLabel(
            "Las alertas clínicas solo se generan si existen rangos en VITAL_RANGES. "
            "Configure rangos antes de esperar alertas automáticas."
        )
        note.setObjectName("versionLabel")
        layout.addWidget(note)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loaded:
            self.refresh()

    def refresh(self) -> None:
        try:
            self._items = (
                hospitalization_service.list_all()
                if self.all_check.isChecked()
                else hospitalization_service.list_active()
            )
            self._loaded = True
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Hospitalización", str(exc))
            return
        self._apply_filters()

    def _apply_filters(self) -> None:
        text = self.search_input.text().strip().lower()
        self.model.setRowCount(0)
        for item in self._items:
            haystack = (
                f"{item.pet_name or ''} {item.owner_name or ''} "
                f"{item.space_code or ''} {item.area_name or ''} "
                f"{item.reason}"
            ).lower()
            if text and text not in haystack:
                continue
            space = "—"
            if item.space_code:
                space = f"{item.area_name or '—'} · {item.space_code}"
            reason = item.reason if len(item.reason) <= 48 else item.reason[:45] + "..."
            status = HOSPITALIZATION_STATUS_DISPLAY.get(item.status, item.status)
            row = [
                QStandardItem(item.admitted_at.strftime("%d/%m/%Y %H:%M")),
                QStandardItem(item.pet_name or "—"),
                QStandardItem(item.owner_name or "—"),
                QStandardItem(space),
                QStandardItem(item.veterinarian_name or "—"),
                QStandardItem(reason),
                QStandardItem(status),
            ]
            row[6].setForeground(
                QColor(_STATUS_COLORS.get(item.status, Colors.TEXT_DARK))
            )
            row[0].setData(item.id, Qt.UserRole)
            for cell in row:
                cell.setEditable(False)
            self.model.appendRow(row)

    def _selected(self) -> Hospitalization | None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(
                self, "Hospitalización", "Seleccione un ingreso primero."
            )
            return None
        hosp_id = self.model.item(indexes[0].row(), 0).data(Qt.UserRole)
        return next((item for item in self._items if item.id == hosp_id), None)

    def _catalogs(self, *, include_current_space: Hospitalization | None = None):
        try:
            pets = hospitalization_service.list_active_pets()
            vets = hospitalization_service.list_veterinarians()
            spaces = hospitalization_service.list_spaces(only_available=False)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Hospitalización", str(exc))
            return None
        if not pets:
            QMessageBox.information(
                self, "Hospitalización", "Primero registre al menos una mascota activa."
            )
            return None
        if not vets:
            QMessageBox.information(
                self, "Hospitalización", "No hay veterinarios o administradores activos."
            )
            return None
        if include_current_space and include_current_space.space_id:
            if not any(s.id == include_current_space.space_id for s in spaces):
                # El espacio ocupado por este ingreso ya viene en list_spaces.
                pass
        return pets, vets, spaces

    def _on_area(self) -> None:
        if AreaDialog(parent=self).exec():
            self.refresh()

    def _on_space(self) -> None:
        try:
            areas = hospitalization_service.list_areas()
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Hospitalización", str(exc))
            return
        if not areas:
            QMessageBox.information(
                self, "Hospitalización", "Primero cree un área de hospitalización."
            )
            return
        if SpaceDialog(areas, parent=self).exec():
            self.refresh()

    def _on_admit(self) -> None:
        catalogs = self._catalogs()
        if catalogs is None:
            return
        pets, vets, spaces = catalogs
        if AdmitDialog(pets, vets, spaces, parent=self).exec():
            self.refresh()

    def _on_edit(self) -> None:
        item = self._selected()
        if item is None:
            return
        if item.status in {"DISCHARGED", "TRANSFERRED"}:
            QMessageBox.information(
                self, "Hospitalización", "Este ingreso ya está cerrado."
            )
            return
        catalogs = self._catalogs(include_current_space=item)
        if catalogs is None:
            return
        pets, vets, spaces = catalogs
        if AdmitDialog(
            pets, vets, spaces, hospitalization=item, parent=self
        ).exec():
            self.refresh()

    def _on_monitoring(self) -> None:
        item = self._selected()
        if item is None:
            return
        if item.status in {"DISCHARGED", "TRANSFERRED"}:
            QMessageBox.information(
                self,
                "Hospitalización",
                "Solo se monitorean ingresos activos.",
            )
            return
        MonitoringDialog(item, parent=self).exec()
        self.refresh()

    def _on_ranges(self) -> None:
        if VitalRangeDialog(parent=self).exec():
            QMessageBox.information(
                self,
                "Hospitalización",
                "Rango vital guardado. Las próximas mediciones usarán ese umbral.",
            )

    def _on_status(self, new_status: str) -> None:
        item = self._selected()
        if item is None:
            return
        label = HOSPITALIZATION_STATUS_DISPLAY.get(new_status, new_status)
        notes = ""
        if new_status in {"DISCHARGED", "TRANSFERRED"}:
            notes, ok = QInputDialog.getMultiLineText(
                self,
                "Hospitalización",
                f"Notas de egreso para «{item.pet_name}» (opcional):",
            )
            if not ok:
                return
        elif QMessageBox.question(
            self,
            "Hospitalización",
            f"¿Marcar a «{item.pet_name}» como {label}?",
        ) != QMessageBox.Yes:
            return
        try:
            hospitalization_service.change_status(item.id, new_status, notes)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Hospitalización", str(exc))
            return
        self.refresh()
