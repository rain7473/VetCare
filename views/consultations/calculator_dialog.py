"""Calculadora farmacológica: dosis solo desde guías configuradas."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from database.connection import DatabaseConnectionError
from models.consultation import Consultation
from models.medication import Medication, MedicationGuideline
from services import pharmacology_service
from services.permission_service import PermissionDeniedError
from services.pharmacology_service import DoseCalculation, PrescriptionFormData
from utils.validators import ValidationError
from widgets.dynamic_selector import DynamicEntitySelector, SelectorItem
from widgets.managed_dialog import ManagedDialog


class CalculatorDialog(ManagedDialog):
    """Calcula y, si la consulta está en borrador, guarda la prescripción."""

    def __init__(self, consultation: Consultation, parent=None) -> None:
        super().__init__(parent)
        self._consultation = consultation
        self._medications: list[Medication] = []
        self._guidelines: list[MedicationGuideline] = []
        self.setWindowTitle("Calculadora farmacológica")
        self.setMinimumWidth(560)
        self._build_ui()
        self._load_catalog()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        intro = QLabel(
            "Las dosis salen de las guías configuradas en Oracle. "
            "VetCare no inventa parámetros médicos."
        )
        intro.setObjectName("screenSubtitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.medication_selector = DynamicEntitySelector(
            placeholder="Buscar medicamento, principio o presentación…",
            add_tooltip="Crear medicamento",
        )
        self.medication_selector.set_add_enabled(
            False, "El catálogo farmacológico se administra desde configuración médica"
        )
        self.medication_selector.selection_changed.connect(self._reload_guidelines)
        form.addRow("Medicamento", self.medication_selector)

        self.guideline_selector = DynamicEntitySelector(
            placeholder="Buscar guía por especie o unidad…",
            add_tooltip="Crear guía farmacológica",
        )
        self.guideline_selector.set_add_enabled(
            False, "Las guías se administran desde configuración médica"
        )
        self.guideline_selector.selection_changed.connect(self._apply_guideline)
        form.addRow("Guía", self.guideline_selector)

        self.weight_input = QDoubleSpinBox()
        self.weight_input.setRange(0.01, 200)
        self.weight_input.setDecimals(2)
        self.weight_input.setSuffix(" kg")
        self.weight_input.valueChanged.connect(self._recalculate)
        form.addRow("Peso usado", self.weight_input)

        self.dose_input = QDoubleSpinBox()
        self.dose_input.setRange(0, 999)
        self.dose_input.setDecimals(3)
        self.dose_input.valueChanged.connect(self._recalculate)
        form.addRow("Dosis por kg", self.dose_input)

        self.range_label = QLabel("Sin guía seleccionada")
        self.range_label.setObjectName("versionLabel")
        form.addRow("Rango de la guía", self.range_label)

        self.duration_input = QSpinBox()
        self.duration_input.setRange(0, 365)
        self.duration_input.setSpecialValueText("Sin duración")
        self.duration_input.setSuffix(" días")
        form.addRow("Duración", self.duration_input)

        self.instructions_input = QTextEdit()
        self.instructions_input.setPlaceholderText("Instrucciones (opcional)")
        self.instructions_input.setFixedHeight(56)
        form.addRow("Instrucciones", self.instructions_input)
        layout.addLayout(form)

        self.result_label = QLabel("Complete peso y dosis para calcular.")
        self.result_label.setWordWrap(True)
        self.result_label.setObjectName("cardTitle")
        layout.addWidget(self.result_label)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cerrar")
        cancel.setProperty("variant", "secondary")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.save_button = QPushButton("Agregar a la consulta")
        self.save_button.setEnabled(self._consultation.status == "DRAFT")
        self.save_button.clicked.connect(self._on_save)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

    def _load_catalog(self) -> None:
        try:
            self._medications = pharmacology_service.list_medications()
            last_weight = pharmacology_service.last_weight_for_consultation(
                self._consultation.id
            )
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            self._show_error(str(exc))
            return
        if last_weight:
            self.weight_input.setValue(last_weight)
        if not self._medications:
            self.medication_selector.set_items([])
            self._show_error(
                "El catálogo de medicamentos está vacío. Configure guías en Oracle "
                "antes de prescribir."
            )
            return
        self.medication_selector.set_items(
            [
                SelectorItem(
                    medication.id,
                    f"{medication.name}{f' · {medication.presentation}' if medication.presentation else ''}",
                    " ".join(
                        filter(
                            None,
                            [medication.active_ingredient, medication.concentration_unit],
                        )
                    ),
                )
                for medication in self._medications
            ]
        )
        self._reload_guidelines()

    def _current_medication(self) -> Medication | None:
        medication_id = self.medication_selector.current_id()
        return next((m for m in self._medications if m.id == medication_id), None)

    def _current_guideline(self) -> MedicationGuideline | None:
        guideline_id = self.guideline_selector.current_id()
        return next((g for g in self._guidelines if g.id == guideline_id), None)

    def _reload_guidelines(self, *_args) -> None:
        medication = self._current_medication()
        self.guideline_selector.set_items([])
        self._guidelines = []
        if medication is None:
            return
        try:
            species_id = pharmacology_service.species_id_for_consultation(
                self._consultation.id
            )
            self._guidelines = pharmacology_service.list_guidelines(
                medication.id, species_id
            )
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            self._show_error(str(exc))
            return
        if not self._guidelines:
            self.range_label.setText("No hay guía para este medicamento/especie.")
            self._recalculate()
            return
        self.guideline_selector.set_items(
            [
                SelectorItem(
                    guideline.id,
                    f"{guideline.species_name or 'Todas las especies'} · {guideline.dose_unit}/kg",
                    guideline.frequency_text or "",
                )
                for guideline in self._guidelines
            ]
        )
        self._apply_guideline()

    def _apply_guideline(self, *_args) -> None:
        guideline = self._current_guideline()
        if guideline is None:
            self.range_label.setText("Sin guía seleccionada")
            self._recalculate()
            return
        minimum = guideline.min_dose_per_kg
        maximum = guideline.max_dose_per_kg
        if minimum is not None:
            self.dose_input.setMinimum(float(minimum))
        else:
            self.dose_input.setMinimum(0)
        if maximum is not None:
            self.dose_input.setMaximum(float(maximum))
        else:
            self.dose_input.setMaximum(999)
        if minimum is not None:
            self.dose_input.setValue(float(minimum))
        text = f"{minimum or '—'} – {maximum or '—'} {guideline.dose_unit}/kg"
        if guideline.frequency_text:
            text += f" · {guideline.frequency_text}"
        self.range_label.setText(text)
        self._recalculate()

    def _recalculate(self) -> None:
        medication = self._current_medication()
        guideline = self._current_guideline()
        if medication is None or guideline is None:
            self.result_label.setText("Seleccione un medicamento con guía configurada.")
            return
        try:
            result = pharmacology_service.calculate_dose(
                weight_kg=self.weight_input.value(),
                dose_per_kg=self.dose_input.value(),
                concentration_value=(
                    float(medication.concentration_value)
                    if medication.concentration_value is not None
                    else None
                ),
                concentration_unit=medication.concentration_unit,
                dose_unit=guideline.dose_unit,
                frequency_text=guideline.frequency_text,
                duration_days=(
                    self.duration_input.value() or None
                ),
            )
        except ValidationError as exc:
            self.result_label.setText(str(exc))
            return
        self.result_label.setText(self._format_result(result, medication))

    @staticmethod
    def _format_result(result: DoseCalculation, medication: Medication) -> str:
        lines = [
            f"Peso usado: {result.weight_used_kg} kg",
            f"Dosis por kg: {result.dose_per_kg} {result.dose_unit}/kg",
            f"Dosis total: {result.calculated_total_dose} {result.dose_unit}",
        ]
        if result.concentration_value is not None:
            lines.append(
                f"Concentración: {result.concentration_value} "
                f"{result.concentration_unit or ''}".strip()
            )
        else:
            lines.append("Concentración: no configurada (sin volumen)")
        if result.calculated_volume is not None:
            unit = result.volume_unit or ""
            lines.append(f"Volumen calculado: {result.calculated_volume} {unit}".strip())
        if medication.default_route:
            lines.append(f"Vía: {medication.default_route}")
        if result.frequency_text:
            lines.append(f"Frecuencia: {result.frequency_text}")
        if result.duration_days:
            lines.append(f"Duración: {result.duration_days} días")
        return "\n".join(lines)

    def _on_save(self) -> None:
        data = PrescriptionFormData(
            consultation_id=self._consultation.id,
            medication_id=self.medication_selector.current_id(),
            guideline_id=self.guideline_selector.current_id(),
            weight_kg=self.weight_input.value(),
            dose_per_kg=self.dose_input.value(),
            duration_days=self.duration_input.value() or None,
            instructions=self.instructions_input.toPlainText(),
        )
        try:
            pharmacology_service.create_prescription(data)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self._show_error(str(exc))
            return
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
