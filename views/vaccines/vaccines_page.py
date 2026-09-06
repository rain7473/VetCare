"""Página de vacunas: catálogo, historial y alertas de próxima aplicación."""

from datetime import date

from PySide6.QtCore import Qt
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
from models.vaccine import PetVaccination
from services import vaccine_service
from services.permission_service import PermissionDeniedError
from views.vaccines.vaccine_dialogs import ApplyDialog, CatalogDialog

_COLUMNS = [
    "Fecha",
    "Mascota",
    "Propietario",
    "Vacuna",
    "Lote",
    "Vence",
    "Próxima",
    "Aplicó",
]


class VaccinesPage(QWidget):
    """Historial de vacunación con alertas por fecha próxima."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageArea")
        self._items: list[PetVaccination] = []
        self._loaded = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Vacunas")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar mascota o vacuna...")
        self.search_input.setFixedWidth(220)
        self.search_input.textChanged.connect(self._apply_filters)
        header.addWidget(self.search_input)

        catalog = QPushButton("＋ Catálogo")
        catalog.setProperty("variant", "secondary")
        catalog.clicked.connect(self._on_catalog)
        header.addWidget(catalog)

        apply_btn = QPushButton("＋ Aplicar vacuna")
        apply_btn.clicked.connect(self._on_apply)
        header.addWidget(apply_btn)
        layout.addLayout(header)

        self.alert_label = QLabel("")
        self.alert_label.setObjectName("errorLabel")
        self.alert_label.setWordWrap(True)
        self.alert_label.setVisible(False)
        layout.addWidget(self.alert_label)

        self.model = QStandardItemModel(0, len(_COLUMNS))
        self.model.setHorizontalHeaderLabels(_COLUMNS)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table, stretch=1)

        note = QLabel(
            "Las próximas fechas las indica el veterinario; VetCare no inventa calendarios."
        )
        note.setObjectName("versionLabel")
        layout.addWidget(note)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loaded:
            self.refresh()

    def refresh(self) -> None:
        try:
            self._items = vaccine_service.list_applications()
            alerts = vaccine_service.list_due_alerts(30)
            self._loaded = True
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Vacunas", str(exc))
            return
        if alerts:
            names = ", ".join(
                f"{a.pet_name} ({a.vaccine_name})" for a in alerts[:5]
            )
            extra = "" if len(alerts) <= 5 else f" y {len(alerts) - 5} más"
            self.alert_label.setText(
                f"Vacunas próximas o vencidas (30 días): {names}{extra}"
            )
            self.alert_label.setVisible(True)
        else:
            self.alert_label.setVisible(False)
        self._apply_filters()

    def _apply_filters(self) -> None:
        text = self.search_input.text().strip().lower()
        today = date.today()
        self.model.setRowCount(0)
        for item in self._items:
            haystack = (
                f"{item.pet_name or ''} {item.owner_name or ''} "
                f"{item.vaccine_name or ''} {item.lot_number or ''}"
            ).lower()
            if text and text not in haystack:
                continue
            next_due = item.next_due_date.strftime("%d/%m/%Y") if item.next_due_date else "—"
            row = [
                QStandardItem(item.applied_at.strftime("%d/%m/%Y %H:%M")),
                QStandardItem(item.pet_name or "—"),
                QStandardItem(item.owner_name or "—"),
                QStandardItem(item.vaccine_name or "—"),
                QStandardItem(item.lot_number or "—"),
                QStandardItem(
                    item.expiry_date.strftime("%d/%m/%Y") if item.expiry_date else "—"
                ),
                QStandardItem(next_due),
                QStandardItem(item.applied_by_name or "—"),
            ]
            if item.next_due_date and item.next_due_date <= today:
                row[6].setForeground(QColor(Colors.ERROR))
            elif item.next_due_date and (item.next_due_date - today).days <= 30:
                row[6].setForeground(QColor(Colors.WARNING))
            for cell in row:
                cell.setEditable(False)
            self.model.appendRow(row)

    def _on_catalog(self) -> None:
        if CatalogDialog(parent=self).exec():
            self.refresh()

    def _on_apply(self, preferred_pet_id: int | None = None) -> None:
        try:
            pets = vaccine_service.list_active_pets()
            vaccines = vaccine_service.list_catalog()
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Vacunas", str(exc))
            return
        if not pets:
            QMessageBox.information(
                self, "Vacunas", "Primero registre al menos una mascota activa."
            )
            return
        if not vaccines:
            QMessageBox.information(
                self, "Vacunas", "Primero agregue una vacuna al catálogo."
            )
            return
        if ApplyDialog(pets, vaccines, preferred_pet_id=preferred_pet_id, parent=self).exec():
            self.refresh()

    def start_for_pet(self, pet_id: int) -> None:
        self.refresh()
        self._on_apply(preferred_pet_id=pet_id)
