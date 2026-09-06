"""Diálogo de registro o edición de un procedimiento quirúrgico."""

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from database.connection import DatabaseConnectionError
from models.consultation import Consultation
from models.medication import Medication
from models.surgery import Surgery
from models.user import User
from services import surgery_service
from services.permission_service import PermissionDeniedError
from services.surgery_service import SurgeryFormData
from utils.validators import ValidationError


class SurgeryDialog(QDialog):
    """Formulario modal de control quirúrgico."""

    def __init__(
        self,
        consultation: Consultation,
        veterinarians: list[User],
        medications: list[Medication],
        surgery: Surgery | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._consultation = consultation
        self._vets = veterinarians
        self._medications = medications
        self._surgery = surgery
        self.setWindowTitle("Editar cirugía" if surgery else "Nuevo procedimiento")
        self.setMinimumWidth(540)
        self._build_ui()
        if surgery is not None:
            self._load_surgery()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setVerticalSpacing(10)

        patient = QLabel(
            f"{self._consultation.pet_name} · {self._consultation.owner_name}"
        )
        form.addRow("Paciente", patient)

        self.vet_combo = QComboBox()
        for vet in self._vets:
            self.vet_combo.addItem(vet.full_name, vet.id)
        form.addRow("Veterinario", self.vet_combo)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej.: Ovariohisterectomía")
        form.addRow("Procedimiento", self.name_input)

        self.when_input = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.when_input.setCalendarPopup(True)
        self.when_input.setDisplayFormat("dd/MM/yyyy HH:mm")
        form.addRow("Fecha y hora", self.when_input)

        self.weight_input = QDoubleSpinBox()
        self.weight_input.setRange(0, 200)
        self.weight_input.setDecimals(2)
        self.weight_input.setSpecialValueText("Sin peso")
        self.weight_input.setSuffix(" kg")
        form.addRow("Peso", self.weight_input)

        self.preop_input = QTextEdit()
        self.preop_input.setFixedHeight(56)
        self.preop_input.setPlaceholderText("Observaciones preoperatorias")
        form.addRow("Preoperatorio", self.preop_input)

        self.postop_input = QTextEdit()
        self.postop_input.setFixedHeight(56)
        self.postop_input.setPlaceholderText("Observaciones posteriores")
        form.addRow("Postoperatorio", self.postop_input)

        self.reco_input = QTextEdit()
        self.reco_input.setFixedHeight(56)
        self.reco_input.setPlaceholderText("Recomendaciones de recuperación")
        form.addRow("Recomendaciones", self.reco_input)

        self.med_combo = QComboBox()
        self.med_combo.addItem("Sin medicamento adicional", None)
        for medication in self._medications:
            self.med_combo.addItem(medication.name, medication.id)
        form.addRow("Medicamento", self.med_combo)

        self.dose_input = QLineEdit()
        self.dose_input.setPlaceholderText("Dosis (texto, opcional)")
        form.addRow("Dosis", self.dose_input)

        self.route_input = QLineEdit()
        self.route_input.setPlaceholderText("Vía (opcional)")
        form.addRow("Vía", self.route_input)

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
        save = QPushButton("Guardar")
        save.clicked.connect(self._on_save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _load_surgery(self) -> None:
        surgery = self._surgery
        index = self.vet_combo.findData(surgery.veterinarian_id)
        if index >= 0:
            self.vet_combo.setCurrentIndex(index)
        self.name_input.setText(surgery.procedure_name)
        if surgery.scheduled_at:
            self.when_input.setDateTime(
                QDateTime.fromSecsSinceEpoch(int(surgery.scheduled_at.timestamp()))
            )
        if surgery.weight_kg:
            self.weight_input.setValue(float(surgery.weight_kg))
        self.preop_input.setPlainText(surgery.preoperative_notes or "")
        self.postop_input.setPlainText(surgery.postoperative_notes or "")
        self.reco_input.setPlainText(surgery.recovery_recommendations or "")

    def _form(self) -> SurgeryFormData:
        weight = self.weight_input.value()
        return SurgeryFormData(
            consultation_id=self._consultation.id,
            veterinarian_id=self.vet_combo.currentData(),
            procedure_name=self.name_input.text(),
            scheduled_at=self.when_input.dateTime().toPython(),
            weight_kg=weight if weight > 0 else None,
            preoperative_notes=self.preop_input.toPlainText(),
            postoperative_notes=self.postop_input.toPlainText(),
            recovery_recommendations=self.reco_input.toPlainText(),
            medication_id=self.med_combo.currentData(),
            medication_dose_text=self.dose_input.text(),
            medication_route=self.route_input.text(),
        )

    def _on_save(self) -> None:
        try:
            if self._surgery is None:
                surgery_service.create_surgery(self._form())
            else:
                surgery_service.update_surgery(self._surgery.id, self._form())
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        self.accept()
