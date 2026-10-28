"""Datos de clínica, preferencias de avisos y acceso a parámetros clínicos."""
import logging
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLineEdit, QLabel, QPushButton, QCheckBox, QSpinBox
from services import settings_service, session, permission_service
from views.hospitalization.monitoring_dialog import VitalRangeDialog

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("pageArea")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Configuración de la clínica", self))
        form = QFormLayout()
        self.fields = {}
        for key, label in settings_service.FIELDS.items():
            field = QLineEdit(self)
            field.setMaxLength(250)
            self.fields[key] = field
            form.addRow(label, field)
        layout.addLayout(form)
        self.desktop = QCheckBox("Avisos de escritorio para mi usuario en este equipo", self)
        layout.addWidget(self.desktop)
        self.interval = QSpinBox(self)
        self.interval.setRange(30, 3600)
        self.interval.setSuffix(" segundos")
        form.addRow("Revisar avisos cada", self.interval)
        layout.addWidget(QLabel("Los avisos se revisan mientras VetCare está abierto. Windows puede silenciarlos.", self))
        save = QPushButton("Guardar configuración", self)
        save.clicked.connect(self.save)
        layout.addWidget(save)
        medical = QPushButton("Configurar rangos vitales", self)
        medical.setEnabled(permission_service.has_permission("HOSPITAL_MANAGE"))
        medical.clicked.connect(lambda: VitalRangeDialog(self).exec())
        layout.addWidget(medical)
        self.message = QLabel(self)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        layout.addStretch()

    def refresh(self):
        try:
            values = settings_service.load()
            for k, field in self.fields.items():
                field.setText(str(values.get(k) or ""))
            prefs = QSettings("VetCare", "VetCare")
            prefix = f"notifications/{session.get_current_user().id}/"
            self.desktop.setChecked(prefs.value(prefix + "desktop", True, type=bool))
            self.interval.setValue(prefs.value(prefix + "interval", 60, type=int))
        except Exception:
            logger.exception("Carga de configuración")
            self.message.setText("No se pudo cargar la configuración.")

    def save(self):
        try:
            settings_service.save({k: w.text() for k, w in self.fields.items()})
            prefs = QSettings("VetCare", "VetCare")
            prefix = f"notifications/{session.get_current_user().id}/"
            prefs.setValue(prefix + "desktop", self.desktop.isChecked())
            prefs.setValue(prefix + "interval", self.interval.value())
            self.message.setText("Configuración guardada. Los avisos aplicarán los cambios en la próxima revisión.")
        except settings_service.ValidationError as exc:
            self.message.setText(str(exc))
        except Exception:
            logger.exception("Guardado de configuración")
            self.message.setText("No se pudo guardar la configuración.")
