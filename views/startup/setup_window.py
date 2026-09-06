"""Pantalla de configuración inicial de VetCare (primer arranque).

Solo aparece cuando la tabla USERS está vacía. Crea el administrador
principal de la clínica con rol ADMIN asignado automáticamente.
"""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_NAME
from database.connection import DatabaseConnectionError
from services import bootstrap_service
from services.bootstrap_service import FirstAdminData
from utils.validators import ValidationError

logger = logging.getLogger(__name__)


class SetupWindow(QWidget):
    """Formulario de creación del primer administrador."""

    admin_created = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("appBackground")
        self.setWindowTitle(f"{APP_NAME} — Configuración inicial")
        self.setMinimumSize(700, 640)
        self.resize(820, 720)
        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll)

        content = QWidget()
        content.setObjectName("appBackground")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.addStretch()
        layout.addWidget(self._build_card(), alignment=Qt.AlignCenter)
        layout.addStretch()

    def _build_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        card.setFixedWidth(560)
        card.setGraphicsEffect(self._soft_shadow())

        layout = QVBoxLayout(card)
        layout.setContentsMargins(44, 36, 44, 36)
        layout.setSpacing(6)

        title = QLabel(f"Bienvenido a {APP_NAME}")
        title.setObjectName("screenTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Configuremos el administrador principal de la clínica.")
        subtitle.setObjectName("screenSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(18)

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft)

        self.full_name_input = QLineEdit()
        self.full_name_input.setPlaceholderText("Ej.: Laura Méndez")
        form.addRow("Nombre completo", self.full_name_input)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Ej.: lmendez")
        form.addRow("Nombre de usuario", self.username_input)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Ej.: laura@clinica.com")
        form.addRow("Correo electrónico", self.email_input)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Opcional")
        form.addRow("Teléfono", self.phone_input)

        self.clinic_name_input = QLineEdit()
        self.clinic_name_input.setPlaceholderText("Opcional")
        form.addRow("Nombre de la clínica", self.clinic_name_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Mínimo 8 caracteres, letra y número")
        form.addRow("Contraseña", self.password_input)

        self.confirmation_input = QLineEdit()
        self.confirmation_input.setEchoMode(QLineEdit.Password)
        form.addRow("Confirmar contraseña", self.confirmation_input)

        layout.addLayout(form)
        layout.addSpacing(8)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.create_button = QPushButton("Crear administrador")
        self.create_button.clicked.connect(self._on_create_clicked)
        layout.addSpacing(6)
        layout.addWidget(self.create_button)

        note = QLabel("El rol ADMIN se asigna automáticamente al primer usuario.")
        note.setObjectName("versionLabel")
        note.setAlignment(Qt.AlignCenter)
        layout.addSpacing(4)
        layout.addWidget(note)

        return card

    @staticmethod
    def _soft_shadow() -> QGraphicsDropShadowEffect:
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 105, 120, 45))
        return shadow

    # -------------------------------------------------------------- Eventos

    def _on_create_clicked(self) -> None:
        data = FirstAdminData(
            full_name=self.full_name_input.text(),
            username=self.username_input.text(),
            email=self.email_input.text(),
            phone=self.phone_input.text(),
            password=self.password_input.text(),
            password_confirmation=self.confirmation_input.text(),
            clinic_name=self.clinic_name_input.text(),
        )

        self.create_button.setEnabled(False)
        try:
            bootstrap_service.create_first_admin(data)
        except ValidationError as exc:
            self._show_error(str(exc))
            return
        except DatabaseConnectionError as exc:
            self._show_error(str(exc))
            return
        except Exception:
            logger.exception("Error inesperado al crear el primer administrador")
            self._show_error(
                "Ocurrió un error inesperado al crear el administrador. "
                "Revise el log de la aplicación."
            )
            return
        finally:
            self.create_button.setEnabled(True)

        QMessageBox.information(
            self,
            APP_NAME,
            "Administrador creado correctamente.\nYa puede iniciar sesión.",
        )
        self.admin_created.emit()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
