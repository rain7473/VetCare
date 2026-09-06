"""Diálogo de registro/edición de propietarios."""

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from database.connection import DatabaseConnectionError
from models.owner import Owner
from services import owner_service
from services.owner_service import OwnerFormData
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError

logger = logging.getLogger(__name__)


class OwnerDialog(QDialog):
    """Formulario modal para crear o editar un propietario."""

    def __init__(self, owner: Owner | None = None, parent=None) -> None:
        super().__init__(parent)
        self._owner = owner
        self.setWindowTitle("Editar propietario" if owner else "Nuevo propietario")
        self.setMinimumWidth(500)
        self._build_ui()
        if owner is not None:
            self._load_owner()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setVerticalSpacing(12)

        self.identification_input = QLineEdit()
        self.identification_input.setPlaceholderText("Opcional (cédula, DNI...)")
        form.addRow("Identificación", self.identification_input)

        self.first_name_input = QLineEdit()
        form.addRow("Nombre", self.first_name_input)

        self.last_name_input = QLineEdit()
        form.addRow("Apellido", self.last_name_input)

        self.phone_input = QLineEdit()
        form.addRow("Teléfono", self.phone_input)

        self.secondary_phone_input = QLineEdit()
        self.secondary_phone_input.setPlaceholderText("Opcional")
        form.addRow("Segundo teléfono", self.secondary_phone_input)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Opcional")
        form.addRow("Email", self.email_input)

        self.address_input = QTextEdit()
        self.address_input.setPlaceholderText("Opcional")
        self.address_input.setFixedHeight(60)
        form.addRow("Dirección", self.address_input)

        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Opcional")
        self.notes_input.setFixedHeight(60)
        form.addRow("Notas", self.notes_input)

        self.active_check = QCheckBox("Propietario activo")
        self.active_check.setChecked(True)
        if self._owner is None:
            self.active_check.setVisible(False)
        form.addRow("", self.active_check)

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

    def _load_owner(self) -> None:
        owner = self._owner
        self.identification_input.setText(owner.identification or "")
        self.first_name_input.setText(owner.first_name)
        self.last_name_input.setText(owner.last_name)
        self.phone_input.setText(owner.phone)
        self.secondary_phone_input.setText(owner.secondary_phone or "")
        self.email_input.setText(owner.email or "")
        self.address_input.setPlainText(owner.address or "")
        self.notes_input.setPlainText(owner.notes or "")
        self.active_check.setChecked(owner.is_active)

    def _on_save(self) -> None:
        data = OwnerFormData(
            identification=self.identification_input.text(),
            first_name=self.first_name_input.text(),
            last_name=self.last_name_input.text(),
            phone=self.phone_input.text(),
            secondary_phone=self.secondary_phone_input.text(),
            email=self.email_input.text(),
            address=self.address_input.toPlainText(),
            notes=self.notes_input.toPlainText(),
            is_active=self.active_check.isChecked(),
        )
        try:
            if self._owner is None:
                owner_service.create_owner(data)
            else:
                owner_service.update_owner(self._owner.id, data)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        except Exception:
            logger.exception("Error inesperado al guardar el propietario")
            self.error_label.setText("Ocurrió un error inesperado al guardar.")
            self.error_label.setVisible(True)
            return

        self.accept()
