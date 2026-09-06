"""Diálogo de creación/edición de usuarios."""

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from config.constants import ROLE_DISPLAY_NAMES
from database.connection import DatabaseConnectionError
from models.user import User
from services import user_service
from services.permission_service import PermissionDeniedError
from services.user_service import UserFormData
from utils.validators import ValidationError

logger = logging.getLogger(__name__)


class UserDialog(QDialog):
    """Formulario modal para crear o editar un usuario."""

    def __init__(self, roles: list[tuple[int, str]], user: User | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._roles = roles
        self._user = user
        is_edit = user is not None
        self.setWindowTitle("Editar usuario" if is_edit else "Nuevo usuario")
        self.setMinimumWidth(460)
        self._build_ui()
        if is_edit:
            self._load_user()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setVerticalSpacing(12)

        self.full_name_input = QLineEdit()
        form.addRow("Nombre completo", self.full_name_input)

        self.username_input = QLineEdit()
        if self._user is not None:
            self.username_input.setEnabled(False)
            self.username_input.setToolTip("El nombre de usuario no se puede cambiar.")
        form.addRow("Nombre de usuario", self.username_input)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Opcional")
        form.addRow("Correo electrónico", self.email_input)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Opcional")
        form.addRow("Teléfono", self.phone_input)

        self.role_combo = QComboBox()
        for role_id, name in self._roles:
            self.role_combo.addItem(ROLE_DISPLAY_NAMES.get(name, name), role_id)
        form.addRow("Rol", self.role_combo)

        self.active_check = QCheckBox("Usuario activo")
        self.active_check.setChecked(True)
        form.addRow("", self.active_check)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.confirmation_input = QLineEdit()
        self.confirmation_input.setEchoMode(QLineEdit.Password)

        if self._user is None:
            self.password_input.setPlaceholderText("Mínimo 8 caracteres, letra y número")
            form.addRow("Contraseña", self.password_input)
            form.addRow("Confirmar contraseña", self.confirmation_input)
        else:
            self.password_input.setPlaceholderText("Dejar vacío para no cambiarla")
            form.addRow("Nueva contraseña", self.password_input)
            form.addRow("Confirmar nueva", self.confirmation_input)

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

    def _load_user(self) -> None:
        user = self._user
        self.full_name_input.setText(user.full_name)
        self.username_input.setText(user.username)
        self.email_input.setText(user.email or "")
        self.phone_input.setText(user.phone or "")
        self.active_check.setChecked(user.is_active)
        index = self.role_combo.findData(user.role_id)
        if index >= 0:
            self.role_combo.setCurrentIndex(index)

    # -------------------------------------------------------------- Guardar

    def _on_save(self) -> None:
        data = UserFormData(
            full_name=self.full_name_input.text(),
            username=self.username_input.text(),
            email=self.email_input.text(),
            phone=self.phone_input.text(),
            role_id=self.role_combo.currentData(),
            is_active=self.active_check.isChecked(),
            password=self.password_input.text(),
            password_confirmation=self.confirmation_input.text(),
        )

        try:
            if self._user is None:
                user_service.create_user(data)
            else:
                user_service.update_user(self._user.id, data)
                if data.password or data.password_confirmation:
                    user_service.reset_password(
                        self._user.id, data.password, data.password_confirmation
                    )
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self._show_error(str(exc))
            return
        except Exception:
            logger.exception("Error inesperado al guardar el usuario")
            self._show_error("Ocurrió un error inesperado al guardar.")
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
