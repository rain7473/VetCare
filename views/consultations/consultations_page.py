"""Página de consultas: listado cronológico + ficha clínica amplia."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.constants import CONSULTATION_STATUS_DISPLAY, Colors
from database.connection import DatabaseConnectionError
from models.consultation import Consultation, ConsultationVital, Diagnosis
from services import consultation_service, permission_service
from services.consultation_service import ConsultationFormData, VitalsFormData
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError
from views.consultations.consultation_dialog import ConsultationDialog

_COLUMNS = ["Fecha", "Paciente", "Propietario", "Veterinario", "Motivo", "Estado"]

_STATUS_COLORS = {
    "DRAFT": Colors.INFO,
    "FINALIZED": Colors.WARNING,
    "SEALED": Colors.SUCCESS,
}


class ConsultationsPage(QWidget):
    """Historial clínico con panel de trabajo tipo consulta."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageArea")
        self._items: list[Consultation] = []
        self._selected_id: int | None = None
        self._loaded = False
        self._can_write = permission_service.has_permission("CONSULTATIONS_WRITE")
        self._can_seal = permission_service.has_permission("CONSULTATIONS_SEAL")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Consultas")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar paciente o motivo...")
        self.search_input.setFixedWidth(220)
        self.search_input.textChanged.connect(self._apply_filters)
        header.addWidget(self.search_input)

        self.status_filter = QComboBox()
        self.status_filter.addItem("Todos los estados", None)
        for code, label in CONSULTATION_STATUS_DISPLAY.items():
            self.status_filter.addItem(label, code)
        self.status_filter.currentIndexChanged.connect(self._apply_filters)
        header.addWidget(self.status_filter)

        self.new_button = QPushButton("＋ Nueva consulta")
        self.new_button.clicked.connect(self._on_new)
        self.new_button.setVisible(self._can_write)
        header.addWidget(self.new_button)
        layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addLayout(self._build_list(), stretch=11)
        body.addWidget(self._build_workspace(), stretch=12)
        layout.addLayout(body, stretch=1)

    def _build_list(self) -> QVBoxLayout:
        left = QVBoxLayout()
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
        self.table.selectionModel().selectionChanged.connect(self._on_selection)
        left.addWidget(self.table)
        return left

    def _build_workspace(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setObjectName("pageArea")
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        self.header_card = self._card()
        head = QVBoxLayout(self.header_card)
        head.setContentsMargins(20, 16, 20, 16)
        self.patient_label = QLabel("Seleccione una consulta")
        self.patient_label.setObjectName("profileName")
        head.addWidget(self.patient_label)
        self.meta_label = QLabel("El historial se muestra en orden cronológico.")
        self.meta_label.setObjectName("screenSubtitle")
        self.meta_label.setWordWrap(True)
        head.addWidget(self.meta_label)
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusBadge")
        head.addWidget(self.status_label)
        self.integrity_label = QLabel("")
        self.integrity_label.setObjectName("versionLabel")
        self.integrity_label.setVisible(False)
        head.addWidget(self.integrity_label)
        layout.addWidget(self.header_card)

        self.reason_input = QTextEdit()
        self.symptoms_input = QTextEdit()
        self.observations_input = QTextEdit()
        self.diagnosis_summary_input = QTextEdit()
        self.treatment_summary_input = QTextEdit()
        for title, widget, hint in [
            ("Motivo de consulta", self.reason_input, "Motivo principal"),
            ("Síntomas", self.symptoms_input, "Síntomas referidos"),
            ("Observaciones", self.observations_input, "Hallazgos y notas"),
            ("Resumen diagnóstico", self.diagnosis_summary_input, "Resumen clínico"),
            ("Tratamiento", self.treatment_summary_input, "Plan terapéutico"),
        ]:
            widget.setPlaceholderText(hint)
            widget.setFixedHeight(72)
            layout.addWidget(self._titled_card(title, widget))

        layout.addWidget(self._build_vitals_card())
        layout.addWidget(self._build_diagnoses_card())

        presc = QLabel(
            "Las prescripciones se registran con la calculadora farmacológica "
            "(siguiente módulo). No se inventan dosis aquí."
        )
        presc.setObjectName("versionLabel")
        presc.setWordWrap(True)
        layout.addWidget(self._titled_card("Prescripciones", presc))

        actions = QHBoxLayout()
        self.save_button = QPushButton("Guardar borrador")
        self.save_button.clicked.connect(self._on_save)
        self.finalize_button = QPushButton("Finalizar consulta")
        self.finalize_button.setProperty("variant", "secondary")
        self.finalize_button.clicked.connect(self._on_finalize)
        self.seal_button = QPushButton("Sellar consulta")
        self.seal_button.setProperty("variant", "secondary")
        self.seal_button.clicked.connect(self._on_seal)
        self.print_button = QPushButton("Imprimir")
        self.print_button.setProperty("variant", "secondary")
        self.print_button.clicked.connect(self._on_print)
        for button in (
            self.save_button,
            self.finalize_button,
            self.seal_button,
            self.print_button,
        ):
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addStretch()
        self._set_workspace_enabled(False)
        return scroll

    def _build_vitals_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        title = QLabel("Signos vitales")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        self.vitals_list = QLabel("Sin mediciones registradas.")
        self.vitals_list.setWordWrap(True)
        self.vitals_list.setObjectName("versionLabel")
        layout.addWidget(self.vitals_list)

        form = QHBoxLayout()
        self.weight_input = self._optional_double("Peso kg", 0, 200, 1)
        self.temp_input = self._optional_double("Temp °C", 0, 45, 1)
        self.hr_input = self._optional_int("FC", 0, 400)
        self.rr_input = self._optional_int("FR", 0, 200)
        self.spo2_input = self._optional_int("SpO2", -1, 100, empty=-1)
        self.pain_input = self._optional_int("Dolor", -1, 10, empty=-1)
        for widget in (
            self.weight_input,
            self.temp_input,
            self.hr_input,
            self.rr_input,
            self.spo2_input,
            self.pain_input,
        ):
            form.addWidget(widget)
        layout.addLayout(form)

        self.vitals_notes = QLineEdit()
        self.vitals_notes.setPlaceholderText("Notas de la medición (opcional)")
        layout.addWidget(self.vitals_notes)

        self.add_vitals_button = QPushButton("Registrar signos")
        self.add_vitals_button.setProperty("variant", "secondary")
        self.add_vitals_button.clicked.connect(self._on_add_vitals)
        layout.addWidget(self.add_vitals_button, alignment=Qt.AlignLeft)
        return card

    def _build_diagnoses_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        title = QLabel("Diagnósticos")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        self.diagnoses_list = QLabel("Sin diagnósticos registrados.")
        self.diagnoses_list.setWordWrap(True)
        self.diagnoses_list.setObjectName("versionLabel")
        layout.addWidget(self.diagnoses_list)

        row = QHBoxLayout()
        self.diagnosis_code = QLineEdit()
        self.diagnosis_code.setPlaceholderText("Código (opc.)")
        self.diagnosis_code.setFixedWidth(110)
        self.diagnosis_text = QLineEdit()
        self.diagnosis_text.setPlaceholderText("Descripción del diagnóstico")
        self.primary_check = QCheckBox("Principal")
        row.addWidget(self.diagnosis_code)
        row.addWidget(self.diagnosis_text, stretch=1)
        row.addWidget(self.primary_check)
        layout.addLayout(row)

        self.add_diagnosis_button = QPushButton("Agregar diagnóstico")
        self.add_diagnosis_button.setProperty("variant", "secondary")
        self.add_diagnosis_button.clicked.connect(self._on_add_diagnosis)
        layout.addWidget(self.add_diagnosis_button, alignment=Qt.AlignLeft)
        return card

    @staticmethod
    def _card() -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        return card

    def _titled_card(self, title: str, widget: QWidget) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        label = QLabel(title)
        label.setObjectName("cardTitle")
        layout.addWidget(label)
        layout.addWidget(widget)
        return card

    @staticmethod
    def _optional_double(label: str, minimum: float, maximum: float, decimals: int):
        box = QDoubleSpinBox()
        box.setPrefix(f"{label} ")
        box.setRange(minimum, maximum)
        box.setDecimals(decimals)
        box.setSpecialValueText(f"{label} —")
        box.setValue(minimum)
        return box

    @staticmethod
    def _optional_int(label: str, minimum: int, maximum: int, empty: int = 0):
        box = QSpinBox()
        box.setPrefix(f"{label} ")
        box.setRange(minimum, maximum)
        box.setSpecialValueText(f"{label} —")
        box.setValue(empty)
        box.setProperty("emptyValue", empty)
        return box

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loaded:
            self.refresh()

    def refresh(self) -> None:
        try:
            self._items = consultation_service.list_consultations()
            self._loaded = True
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Consultas", str(exc))
            return
        self._apply_filters()
        if self._selected_id is not None:
            self._load_detail(self._selected_id)

    def _apply_filters(self) -> None:
        status = self.status_filter.currentData()
        text = self.search_input.text().strip().lower()
        self.model.setRowCount(0)
        for item in self._items:
            if status is not None and item.status != status:
                continue
            haystack = (
                f"{item.pet_name or ''} {item.owner_name or ''} "
                f"{item.veterinarian_name or ''} {item.reason}".lower()
            )
            if text and text not in haystack:
                continue
            when = item.started_at.strftime("%d/%m/%Y %H:%M")
            reason = item.reason if len(item.reason) <= 48 else item.reason[:45] + "..."
            row = [
                QStandardItem(when),
                QStandardItem(item.pet_name or "—"),
                QStandardItem(item.owner_name or "—"),
                QStandardItem(item.veterinarian_name or "—"),
                QStandardItem(reason),
                QStandardItem(CONSULTATION_STATUS_DISPLAY.get(item.status, item.status)),
            ]
            row[5].setForeground(QColor(_STATUS_COLORS.get(item.status, Colors.TEXT_DARK)))
            row[0].setData(item.id, Qt.UserRole)
            for cell in row:
                cell.setEditable(False)
            self.model.appendRow(row)

    def _on_selection(self) -> None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return
        consultation_id = self.model.item(indexes[0].row(), 0).data(Qt.UserRole)
        self._load_detail(consultation_id)

    def _load_detail(self, consultation_id: int) -> None:
        try:
            consultation, vitals, diagnoses = consultation_service.get_detail(
                consultation_id
            )
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Consultas", str(exc))
            return
        self._selected_id = consultation.id
        self.patient_label.setText(f"{consultation.pet_name}")
        started = consultation.started_at.strftime("%d/%m/%Y %H:%M")
        self.meta_label.setText(
            f"{consultation.owner_name} · {consultation.veterinarian_name} · {started}"
        )
        self.status_label.setText(
            CONSULTATION_STATUS_DISPLAY.get(consultation.status, consultation.status)
        )
        self._set_badge_color(consultation.status)
        self._show_integrity(consultation)
        self.reason_input.setPlainText(consultation.reason or "")
        self.symptoms_input.setPlainText(consultation.symptoms or "")
        self.observations_input.setPlainText(consultation.observations or "")
        self.diagnosis_summary_input.setPlainText(consultation.diagnosis_summary or "")
        self.treatment_summary_input.setPlainText(consultation.treatment_summary or "")
        self.vitals_list.setText(self._format_vitals(vitals))
        self.diagnoses_list.setText(self._format_diagnoses(diagnoses))
        editable = consultation.status == "DRAFT" and self._can_write
        self._set_workspace_enabled(True, editable=editable)
        self.seal_button.setEnabled(consultation.status == "FINALIZED" and self._can_seal)
        self.finalize_button.setEnabled(editable)
        self.save_button.setEnabled(editable)
        self.print_button.setEnabled(True)

    def _show_integrity(self, consultation: Consultation) -> None:
        if consultation.status != "SEALED":
            self.integrity_label.setVisible(False)
            return
        try:
            intact = consultation_service.verify_seal(consultation.id)
        except (PermissionDeniedError, DatabaseConnectionError):
            intact = False
        self.integrity_label.setText(
            "Integridad verificada ✓" if intact else "Error de integridad ⚠"
        )
        self.integrity_label.setVisible(True)

    def _set_badge_color(self, status: str) -> None:
        color = _STATUS_COLORS.get(status, Colors.MUTED)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 700;")

    def _set_workspace_enabled(self, has_selection: bool, editable: bool = False) -> None:
        widgets = [
            self.reason_input,
            self.symptoms_input,
            self.observations_input,
            self.diagnosis_summary_input,
            self.treatment_summary_input,
            self.weight_input,
            self.temp_input,
            self.hr_input,
            self.rr_input,
            self.spo2_input,
            self.pain_input,
            self.vitals_notes,
            self.add_vitals_button,
            self.diagnosis_code,
            self.diagnosis_text,
            self.primary_check,
            self.add_diagnosis_button,
            self.save_button,
            self.finalize_button,
        ]
        for widget in widgets:
            widget.setEnabled(has_selection and editable)
        self.seal_button.setEnabled(False)
        self.print_button.setEnabled(has_selection)

    def _form_data(self, consultation: Consultation) -> ConsultationFormData:
        return ConsultationFormData(
            pet_id=consultation.pet_id,
            veterinarian_id=consultation.veterinarian_id,
            appointment_id=consultation.appointment_id,
            triage_id=consultation.triage_id,
            reason=self.reason_input.toPlainText(),
            symptoms=self.symptoms_input.toPlainText(),
            observations=self.observations_input.toPlainText(),
            diagnosis_summary=self.diagnosis_summary_input.toPlainText(),
            treatment_summary=self.treatment_summary_input.toPlainText(),
        )

    def _selected(self) -> Consultation | None:
        if self._selected_id is None:
            QMessageBox.information(self, "Consultas", "Seleccione una consulta primero.")
            return None
        return next((item for item in self._items if item.id == self._selected_id), None)

    def filter_by_pet_name(self, pet_name: str) -> None:
        self.search_input.setText(pet_name)
        self.refresh()

    def start_for_pet(self, pet_id: int) -> None:
        self.refresh()
        self._open_new_dialog(preferred_pet_id=pet_id)

    def _on_new(self) -> None:
        self._open_new_dialog()

    def _open_new_dialog(self, preferred_pet_id: int | None = None) -> None:
        try:
            pets = consultation_service.list_active_pets()
            vets = consultation_service.list_veterinarians()
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Consultas", str(exc))
            return
        if not pets:
            QMessageBox.information(
                self, "Consultas", "Primero registre al menos una mascota activa."
            )
            return
        if not vets:
            QMessageBox.information(
                self, "Consultas", "No hay veterinarios o administradores activos."
            )
            return
        dialog = ConsultationDialog(
            pets, vets, parent=self, preferred_pet_id=preferred_pet_id
        )
        if dialog.exec():
            self.refresh()

    def _on_save(self) -> None:
        consultation = self._selected()
        if consultation is None:
            return
        try:
            consultation_service.update_content(consultation.id, self._form_data(consultation))
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Consultas", str(exc))
            return
        self.refresh()

    def _on_finalize(self) -> None:
        consultation = self._selected()
        if consultation is None:
            return
        if QMessageBox.question(
            self,
            "Consultas",
            f"¿Finalizar la consulta de «{consultation.pet_name}»?",
        ) != QMessageBox.Yes:
            return
        try:
            consultation_service.update_content(consultation.id, self._form_data(consultation))
            consultation_service.finalize(consultation.id)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Consultas", str(exc))
            return
        self.refresh()

    def _on_seal(self) -> None:
        consultation = self._selected()
        if consultation is None:
            return
        if QMessageBox.question(
            self,
            "Consultas",
            "El sellado es irreversible. ¿Sellar esta consulta?",
        ) != QMessageBox.Yes:
            return
        try:
            sealed_hash = consultation_service.seal(consultation.id)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Consultas", str(exc))
            return
        QMessageBox.information(
            self, "Consultas", f"Consulta sellada.\nHash: {sealed_hash}"
        )
        self.refresh()

    def _on_add_vitals(self) -> None:
        consultation = self._selected()
        if consultation is None:
            return
        data = VitalsFormData(
            weight_kg=self._spin_or_none(self.weight_input),
            temperature_c=self._spin_or_none(self.temp_input),
            heart_rate_bpm=self._spin_or_none(self.hr_input, integer=True),
            respiratory_rate_rpm=self._spin_or_none(self.rr_input, integer=True),
            oxygen_saturation_pct=self._spin_or_none(self.spo2_input, integer=True),
            pain_level=self._spin_or_none(self.pain_input, integer=True),
            notes=self.vitals_notes.text(),
        )
        try:
            consultation_service.add_vitals(consultation.id, data)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Consultas", str(exc))
            return
        self.vitals_notes.clear()
        self.refresh()

    def _on_add_diagnosis(self) -> None:
        consultation = self._selected()
        if consultation is None:
            return
        try:
            consultation_service.add_diagnosis(
                consultation.id,
                diagnostic_code=self.diagnosis_code.text(),
                description=self.diagnosis_text.text(),
                is_primary=self.primary_check.isChecked(),
            )
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Consultas", str(exc))
            return
        self.diagnosis_code.clear()
        self.diagnosis_text.clear()
        self.primary_check.setChecked(False)
        self.refresh()

    def _on_print(self) -> None:
        consultation = self._selected()
        if consultation is None:
            return
        try:
            consultation, vitals, diagnoses = consultation_service.get_detail(
                consultation.id
            )
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Consultas", str(exc))
            return
        html = self._print_html(consultation, vitals, diagnoses)
        dialog = QDialog(self)
        dialog.setWindowTitle("Imprimir consulta")
        dialog.resize(640, 520)
        box = QVBoxLayout(dialog)
        preview = QTextEdit()
        preview.setReadOnly(True)
        document = QTextDocument()
        document.setHtml(html)
        preview.setDocument(document)
        box.addWidget(preview)
        close = QPushButton("Cerrar")
        close.clicked.connect(dialog.accept)
        box.addWidget(close, alignment=Qt.AlignRight)
        dialog.exec()

    @staticmethod
    def _spin_or_none(widget, integer: bool = False):
        empty = widget.property("emptyValue")
        if empty is None:
            empty = widget.minimum()
        if widget.value() == empty:
            return None
        return int(widget.value()) if integer else float(widget.value())

    @staticmethod
    def _format_vitals(vitals: list[ConsultationVital]) -> str:
        if not vitals:
            return "Sin mediciones registradas."
        lines = []
        for vital in vitals:
            when = vital.recorded_at.strftime("%d/%m %H:%M") if vital.recorded_at else "—"
            parts = [when, vital.recorded_by_name or ""]
            if vital.weight_kg is not None:
                parts.append(f"{vital.weight_kg} kg")
            if vital.temperature_c is not None:
                parts.append(f"{vital.temperature_c} °C")
            if vital.heart_rate_bpm is not None:
                parts.append(f"FC {vital.heart_rate_bpm}")
            if vital.respiratory_rate_rpm is not None:
                parts.append(f"FR {vital.respiratory_rate_rpm}")
            if vital.oxygen_saturation_pct is not None:
                parts.append(f"SpO2 {vital.oxygen_saturation_pct}%")
            if vital.pain_level is not None:
                parts.append(f"Dolor {vital.pain_level}")
            lines.append(" · ".join(part for part in parts if part))
        return "\n".join(lines)

    @staticmethod
    def _format_diagnoses(diagnoses: list[Diagnosis]) -> str:
        if not diagnoses:
            return "Sin diagnósticos registrados."
        lines = []
        for diagnosis in diagnoses:
            mark = "Principal · " if diagnosis.is_primary else ""
            code = f"{diagnosis.diagnostic_code} — " if diagnosis.diagnostic_code else ""
            lines.append(f"{mark}{code}{diagnosis.description}")
        return "\n".join(lines)

    @staticmethod
    def _print_html(
        consultation: Consultation,
        vitals: list[ConsultationVital],
        diagnoses: list[Diagnosis],
    ) -> str:
        status = CONSULTATION_STATUS_DISPLAY.get(consultation.status, consultation.status)
        return f"""
        <h2>Consulta clínica — VetCare</h2>
        <p><b>Paciente:</b> {consultation.pet_name}<br>
        <b>Propietario:</b> {consultation.owner_name}<br>
        <b>Veterinario:</b> {consultation.veterinarian_name}<br>
        <b>Estado:</b> {status}<br>
        <b>Inicio:</b> {consultation.started_at}</p>
        <h3>Motivo</h3><p>{consultation.reason or '—'}</p>
        <h3>Síntomas</h3><p>{consultation.symptoms or '—'}</p>
        <h3>Observaciones</h3><p>{consultation.observations or '—'}</p>
        <h3>Diagnóstico</h3><p>{consultation.diagnosis_summary or '—'}</p>
        <h3>Tratamiento</h3><p>{consultation.treatment_summary or '—'}</p>
        """
