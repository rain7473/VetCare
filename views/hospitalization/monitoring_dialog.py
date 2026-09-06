"""Diálogos de monitoreo, rangos vitales y gestión de alertas."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from config.constants import Colors
from database.connection import DatabaseConnectionError
from models.hospitalization import Hospitalization
from services import monitoring_service
from services.monitoring_service import MonitoringFormData, VitalRangeFormData
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError


class VitalRangeDialog(QDialog):
    """Configura un rango en VITAL_RANGES (sin inventar valores por defecto)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configurar rango vital")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)

        note = QLabel(
            "Los rangos deben cargarse desde la configuración clínica. "
            "VetCare no inventa umbrales médicos."
        )
        note.setObjectName("screenSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        self.species_combo = QComboBox()
        try:
            for species_id, name in monitoring_service.list_species():
                self.species_combo.addItem(name, species_id)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            self.species_combo.addItem(str(exc), None)
        form.addRow("Especie", self.species_combo)

        self.parameter_combo = QComboBox()
        for code, label in monitoring_service.PARAMETER_LABELS.items():
            self.parameter_combo.addItem(f"{label} ({code})", code)
        form.addRow("Parámetro", self.parameter_combo)

        self.min_input = QDoubleSpinBox()
        self.min_input.setRange(-1, 9999)
        self.min_input.setDecimals(2)
        self.min_input.setSpecialValueText("Sin mínimo")
        self.min_input.setValue(-1)
        form.addRow("Mínimo", self.min_input)

        self.max_input = QDoubleSpinBox()
        self.max_input.setRange(-1, 9999)
        self.max_input.setDecimals(2)
        self.max_input.setSpecialValueText("Sin máximo")
        self.max_input.setValue(-1)
        form.addRow("Máximo", self.max_input)

        self.unit_input = QLineEdit()
        self.unit_input.setPlaceholderText("Ej.: °C, bpm, %")
        form.addRow("Unidad", self.unit_input)

        self.description_input = QTextEdit()
        self.description_input.setFixedHeight(48)
        form.addRow("Descripción", self.description_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("variant", "secondary")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Guardar rango")
        save.clicked.connect(self._on_save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _on_save(self) -> None:
        min_value = None if self.min_input.value() < 0 else self.min_input.value()
        max_value = None if self.max_input.value() < 0 else self.max_input.value()
        try:
            monitoring_service.save_vital_range(
                VitalRangeFormData(
                    species_id=self.species_combo.currentData(),
                    parameter_code=self.parameter_combo.currentData(),
                    min_value=min_value,
                    max_value=max_value,
                    unit=self.unit_input.text(),
                    description=self.description_input.toPlainText(),
                )
            )
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        self.accept()


class MonitoringDialog(QDialog):
    """Registra una medición y muestra historial/alertas del ingreso."""

    def __init__(self, hospitalization: Hospitalization, parent=None) -> None:
        super().__init__(parent)
        self._hosp = hospitalization
        self.setWindowTitle(f"Monitoreo · {hospitalization.pet_name}")
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        meta = QLabel(
            f"{self._hosp.pet_name} · {self._hosp.owner_name} · "
            f"{self._hosp.area_name or 'Sin área'} "
            f"{self._hosp.space_code or ''}".strip()
        )
        meta.setObjectName("screenSubtitle")
        meta.setWordWrap(True)
        layout.addWidget(meta)

        self.history_label = QLabel("Sin mediciones.")
        self.history_label.setWordWrap(True)
        self.history_label.setObjectName("versionLabel")
        layout.addWidget(self.history_label)

        self.alerts_label = QLabel("Sin alertas abiertas.")
        self.alerts_label.setWordWrap(True)
        self.alerts_label.setStyleSheet(f"color: {Colors.ERROR};")
        layout.addWidget(self.alerts_label)

        alert_actions = QHBoxLayout()
        ack = QPushButton("Acusar alerta abierta")
        ack.setProperty("variant", "secondary")
        ack.clicked.connect(lambda: self._on_alert_action("ACKNOWLEDGED"))
        resolve = QPushButton("Resolver alerta abierta")
        resolve.setProperty("variant", "secondary")
        resolve.clicked.connect(lambda: self._on_alert_action("RESOLVED"))
        alert_actions.addWidget(ack)
        alert_actions.addWidget(resolve)
        alert_actions.addStretch()
        layout.addLayout(alert_actions)

        form = QFormLayout()
        self.temp_input = self._optional_double("°C", 0, 45)
        self.hr_input = self._optional_int(0, 400)
        self.rr_input = self._optional_int(0, 200)
        self.spo2_input = self._optional_int(-1, 100, empty=-1)
        self.weight_input = self._optional_double("kg", 0, 200)
        self.pain_input = self._optional_int(-1, 10, empty=-1)
        form.addRow("Temperatura", self.temp_input)
        form.addRow("FC (bpm)", self.hr_input)
        form.addRow("FR (rpm)", self.rr_input)
        form.addRow("SpO2 (%)", self.spo2_input)
        form.addRow("Peso", self.weight_input)
        form.addRow("Dolor (0-10)", self.pain_input)

        self.feeding_input = QLineEdit()
        self.feeding_input.setPlaceholderText("Opcional")
        form.addRow("Alimentación", self.feeding_input)
        self.hydration_input = QLineEdit()
        self.hydration_input.setPlaceholderText("Opcional")
        form.addRow("Hidratación", self.hydration_input)
        self.observations_input = QTextEdit()
        self.observations_input.setFixedHeight(48)
        form.addRow("Observaciones", self.observations_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton("Cerrar")
        close.setProperty("variant", "secondary")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        save = QPushButton("Registrar medición")
        save.clicked.connect(self._on_save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    @staticmethod
    def _optional_double(suffix: str, minimum: float, maximum: float):
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(1)
        box.setSuffix(f" {suffix}" if suffix else "")
        box.setSpecialValueText("—")
        box.setValue(minimum)
        return box

    @staticmethod
    def _optional_int(minimum: int, maximum: int, empty: int = 0):
        box = QSpinBox()
        box.setRange(minimum, maximum)
        box.setSpecialValueText("—")
        box.setValue(empty)
        box.setProperty("emptyValue", empty)
        return box

    def _reload(self) -> None:
        try:
            records = monitoring_service.list_monitoring(self._hosp.id)
            alerts = monitoring_service.list_alerts(
                self._hosp.id, open_only=True
            )
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return

        if not records:
            self.history_label.setText("Sin mediciones registradas.")
        else:
            lines = []
            for item in records[:8]:
                when = item.recorded_at.strftime("%d/%m %H:%M")
                parts = [when, item.recorded_by_name or ""]
                if item.temperature_c is not None:
                    parts.append(f"{item.temperature_c} °C")
                if item.heart_rate_bpm is not None:
                    parts.append(f"FC {item.heart_rate_bpm}")
                if item.respiratory_rate_rpm is not None:
                    parts.append(f"FR {item.respiratory_rate_rpm}")
                if item.oxygen_saturation_pct is not None:
                    parts.append(f"SpO2 {item.oxygen_saturation_pct}%")
                if item.pain_level is not None:
                    parts.append(f"Dolor {item.pain_level}")
                lines.append(" · ".join(p for p in parts if p))
            self.history_label.setText("Últimas mediciones:\n" + "\n".join(lines))

        self._open_alerts = alerts
        if not alerts:
            self.alerts_label.setText("Sin alertas abiertas.")
            self.alerts_label.setStyleSheet(f"color: {Colors.MUTED};")
        else:
            lines = [
                f"[{a.severity}] {a.message} ({a.status})" for a in alerts[:6]
            ]
            self.alerts_label.setText(
                f"Alertas abiertas ({len(alerts)}):\n" + "\n".join(lines)
            )
            self.alerts_label.setStyleSheet(f"color: {Colors.ERROR};")

    def _spin_or_none(self, widget, integer: bool = False):
        empty = widget.property("emptyValue")
        if empty is None:
            empty = widget.minimum()
        if widget.value() == empty:
            return None
        return int(widget.value()) if integer else float(widget.value())

    def _on_save(self) -> None:
        data = MonitoringFormData(
            hospitalization_id=self._hosp.id,
            temperature_c=self._spin_or_none(self.temp_input),
            heart_rate_bpm=self._spin_or_none(self.hr_input, integer=True),
            respiratory_rate_rpm=self._spin_or_none(self.rr_input, integer=True),
            oxygen_saturation_pct=self._spin_or_none(self.spo2_input, integer=True),
            weight_kg=self._spin_or_none(self.weight_input),
            pain_level=self._spin_or_none(self.pain_input, integer=True),
            feeding_status=self.feeding_input.text(),
            hydration_status=self.hydration_input.text(),
            observations=self.observations_input.toPlainText(),
        )
        try:
            _, alert_ids = monitoring_service.record_monitoring(data)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        if alert_ids:
            QMessageBox.warning(
                self,
                "Monitoreo",
                f"Medición guardada. Se generaron {len(alert_ids)} alerta(s) "
                "según los rangos configurados.",
            )
        self.observations_input.clear()
        self._reload()

    def _on_alert_action(self, status: str) -> None:
        alerts = getattr(self, "_open_alerts", [])
        if not alerts:
            QMessageBox.information(self, "Monitoreo", "No hay alertas abiertas.")
            return
        alert = alerts[0]
        try:
            if status == "ACKNOWLEDGED":
                monitoring_service.acknowledge_alert(alert.id)
            else:
                monitoring_service.resolve_alert(alert.id)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Monitoreo", str(exc))
            return
        self._reload()
