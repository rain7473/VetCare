"""Diálogo de registro de triaje con semáforo de prioridad automático."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from config.constants import (
    CONSCIOUSNESS_DISPLAY,
    TRIAGE_PRIORITY_DISPLAY,
    Colors,
)
from database.connection import DatabaseConnectionError
from models.pet import Pet
from services import triage_service
from services.permission_service import PermissionDeniedError
from services.triage_service import TriageFormData, suggest_priority
from utils.validators import ValidationError

logger = logging.getLogger(__name__)

_PRIORITY_COLORS = {1: Colors.ERROR, 2: Colors.WARNING, 3: Colors.INFO, 4: Colors.SUCCESS}


class TriageDialog(QDialog):
    """Formulario modal de triaje (registro inmutable)."""

    def __init__(self, pets: list[Pet], parent=None) -> None:
        super().__init__(parent)
        self._pets = pets
        self._manual_priority = False
        self.setWindowTitle("Nuevo triaje")
        self.setMinimumWidth(560)
        self._build_ui()
        self._recalculate()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.pet_combo = QComboBox()
        for pet in self._pets:
            self.pet_combo.addItem(f"{pet.name} ({pet.owner_name})", pet.id)
        self.pet_combo.currentIndexChanged.connect(self._reload_appointments)
        form.addRow("Mascota", self.pet_combo)

        self.appointment_combo = QComboBox()
        self.appointment_combo.addItem("Sin cita vinculada", None)
        form.addRow("Cita", self.appointment_combo)

        self.reason_input = QTextEdit()
        self.reason_input.setPlaceholderText("Motivo de la visita / emergencia")
        self.reason_input.setFixedHeight(52)
        form.addRow("Motivo", self.reason_input)

        self.consciousness_combo = QComboBox()
        self.consciousness_combo.addItem("No evaluado", None)
        for code, label in CONSCIOUSNESS_DISPLAY.items():
            self.consciousness_combo.addItem(label, code)
        self.consciousness_combo.currentIndexChanged.connect(self._recalculate)
        form.addRow("Consciencia", self.consciousness_combo)

        flags_row = QHBoxLayout()
        self.respiratory_check = QCheckBox("Dificultad respiratoria")
        self.bleeding_check = QCheckBox("Sangrado activo")
        self.seizures_check = QCheckBox("Convulsiones")
        for check in (self.respiratory_check, self.bleeding_check, self.seizures_check):
            check.toggled.connect(self._recalculate)
            flags_row.addWidget(check)
        form.addRow("Signos", flags_row)

        self.walk_combo = QComboBox()
        self.walk_combo.addItem("No evaluado", None)
        self.walk_combo.addItem("Sí", True)
        self.walk_combo.addItem("No", False)
        self.walk_combo.currentIndexChanged.connect(self._recalculate)
        form.addRow("¿Puede caminar?", self.walk_combo)

        pain_row = QHBoxLayout()
        self.pain_slider = QSlider(Qt.Horizontal)
        self.pain_slider.setRange(-1, 10)
        self.pain_slider.setValue(-1)
        self.pain_slider.valueChanged.connect(self._on_pain_change)
        pain_row.addWidget(self.pain_slider)
        self.pain_label = QLabel("—")
        self.pain_label.setFixedWidth(40)
        pain_row.addWidget(self.pain_label)
        form.addRow("Dolor (0-10)", pain_row)

        vitals_row = QHBoxLayout()
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(19.9, 45.0)
        self.temp_spin.setDecimals(1)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(19.9)
        self.temp_spin.setSpecialValueText("—")
        self.temp_spin.setSuffix(" °C")
        self.temp_spin.valueChanged.connect(self._recalculate)
        vitals_row.addWidget(QLabel("T°:"))
        vitals_row.addWidget(self.temp_spin)

        self.hr_spin = QSpinBox()
        self.hr_spin.setRange(0, 400)
        self.hr_spin.setValue(0)
        self.hr_spin.setSpecialValueText("—")
        vitals_row.addWidget(QLabel("FC:"))
        vitals_row.addWidget(self.hr_spin)

        self.rr_spin = QSpinBox()
        self.rr_spin.setRange(0, 200)
        self.rr_spin.setValue(0)
        self.rr_spin.setSpecialValueText("—")
        vitals_row.addWidget(QLabel("FR:"))
        vitals_row.addWidget(self.rr_spin)

        self.spo2_spin = QSpinBox()
        self.spo2_spin.setRange(-1, 100)
        self.spo2_spin.setValue(-1)
        self.spo2_spin.setSpecialValueText("—")
        self.spo2_spin.setSuffix(" %")
        self.spo2_spin.valueChanged.connect(self._recalculate)
        vitals_row.addWidget(QLabel("SpO2:"))
        vitals_row.addWidget(self.spo2_spin)
        form.addRow("Vitales", vitals_row)

        priority_row = QHBoxLayout()
        self.priority_badge = QLabel("")
        self.priority_badge.setObjectName("priorityBadge")
        self.priority_badge.setAlignment(Qt.AlignCenter)
        self.priority_badge.setFixedHeight(30)
        self.priority_badge.setMinimumWidth(140)
        priority_row.addWidget(self.priority_badge)

        self.priority_combo = QComboBox()
        for level, label in TRIAGE_PRIORITY_DISPLAY.items():
            self.priority_combo.addItem(label, level)
        self.priority_combo.activated.connect(self._on_manual_priority)
        priority_row.addWidget(self.priority_combo)
        priority_row.addStretch()
        form.addRow("Prioridad", priority_row)

        self.priority_reason_input = QTextEdit()
        self.priority_reason_input.setFixedHeight(44)
        form.addRow("Razón prioridad", self.priority_reason_input)

        self.observations_input = QTextEdit()
        self.observations_input.setPlaceholderText("Opcional")
        self.observations_input.setFixedHeight(44)
        form.addRow("Observaciones", self.observations_input)

        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("variant", "secondary")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Registrar triaje")
        save.clicked.connect(self._on_save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        self._reload_appointments()

    # ------------------------------------------------------------- Cálculo

    def _on_pain_change(self, value: int) -> None:
        self.pain_label.setText("—" if value < 0 else str(value))
        self._recalculate()

    def _on_manual_priority(self) -> None:
        self._manual_priority = True
        self._update_badge(self.priority_combo.currentData())

    def _current_signs(self) -> dict:
        return dict(
            consciousness_status=self.consciousness_combo.currentData(),
            respiratory_distress=self.respiratory_check.isChecked(),
            active_bleeding=self.bleeding_check.isChecked(),
            can_walk=self.walk_combo.currentData(),
            seizures=self.seizures_check.isChecked(),
            pain_level=(
                None if self.pain_slider.value() < 0 else self.pain_slider.value()
            ),
            temperature_c=(
                None if self.temp_spin.value() <= 19.9 else self.temp_spin.value()
            ),
            oxygen_saturation_pct=(
                None if self.spo2_spin.value() < 0 else self.spo2_spin.value()
            ),
        )

    def _recalculate(self, *_args) -> None:
        level, reason = suggest_priority(**self._current_signs())
        if not self._manual_priority:
            index = self.priority_combo.findData(level)
            if index >= 0:
                self.priority_combo.setCurrentIndex(index)
            self.priority_reason_input.setPlainText(reason)
            self._update_badge(level)

    def _update_badge(self, level: int) -> None:
        color = _PRIORITY_COLORS.get(level, Colors.MUTED)
        self.priority_badge.setText(TRIAGE_PRIORITY_DISPLAY.get(level, str(level)))
        self.priority_badge.setStyleSheet(
            f"background-color: {color}; color: white; font-weight: 700;"
            "border-radius: 8px; padding: 4px 10px;"
        )

    # ------------------------------------------------------------- Guardar

    def _reload_appointments(self) -> None:
        pet_id = self.pet_combo.currentData()
        self.appointment_combo.clear()
        self.appointment_combo.addItem("Sin cita vinculada", None)
        if pet_id is None:
            return
        try:
            for appt in triage_service.list_open_appointments(pet_id):
                when = appt.appointment_at.strftime("%d/%m %H:%M")
                self.appointment_combo.addItem(f"{when} · {appt.reason[:40]}", appt.id)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            logger.warning("No se pudieron cargar citas: %s", exc)

    def _on_save(self) -> None:
        signs = self._current_signs()
        data = TriageFormData(
            pet_id=self.pet_combo.currentData(),
            appointment_id=self.appointment_combo.currentData(),
            reason=self.reason_input.toPlainText(),
            heart_rate_bpm=None if self.hr_spin.value() == 0 else self.hr_spin.value(),
            respiratory_rate_rpm=(
                None if self.rr_spin.value() == 0 else self.rr_spin.value()
            ),
            priority_level=self.priority_combo.currentData(),
            priority_reason=self.priority_reason_input.toPlainText(),
            observations=self.observations_input.toPlainText(),
            **signs,
        )
        try:
            triage_service.create_triage(data)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        except Exception:
            logger.exception("Error inesperado al registrar el triaje")
            self.error_label.setText("Ocurrió un error inesperado al guardar.")
            self.error_label.setVisible(True)
            return
        self.accept()
