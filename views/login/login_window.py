"""Ventana de inicio de sesión de VetCare."""

import logging

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_NAME, APP_TAGLINE
from database.connection import DatabaseConnectionError
from services import auth_service
from services.auth_service import AuthenticationError

logger = logging.getLogger(__name__)

_SETTINGS_REMEMBER = "login/remember_username"
_SETTINGS_USERNAME = "login/last_username"


class LoginWindow(QWidget):
    """Formulario de login contra la tabla USERS."""

    login_succeeded = Signal(object)  # emite el User autenticado

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("appBackground")
        self.setWindowTitle(f"{APP_NAME} — Iniciar sesión")
        self.setMinimumSize(640, 560)
        self.resize(760, 620)
        self._settings = QSettings(APP_NAME, APP_NAME)
        self._build_ui()
        self._load_remembered_username()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 40, 48, 40)
        root.addStretch()
        root.addWidget(self._build_card(), alignment=Qt.AlignCenter)
        root.addStretch()

    def _build_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        card.setFixedWidth(460)
        card.setGraphicsEffect(self._soft_shadow())

        layout = QVBoxLayout(card)
        layout.setContentsMargins(44, 36, 44, 36)
        layout.setSpacing(6)

        logo = QLabel("🐾")
        logo.setObjectName("logoBadge")
        logo.setFixedSize(72, 72)
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo, alignment=Qt.AlignCenter)
        layout.addSpacing(6)

        title = QLabel(APP_NAME)
        title.setObjectName("screenTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Inicie sesión para continuar")
        subtitle.setObjectName("screenSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(16)

        form = QFormLayout()
        form.setVerticalSpacing(12)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Nombre de usuario")
        form.addRow("Usuario", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Contraseña")
        form.addRow("Contraseña", self.password_input)

        layout.addLayout(form)
        layout.addSpacing(4)

        self.show_password_check = QCheckBox("Mostrar contraseña")
        self.show_password_check.toggled.connect(self._on_toggle_password)
        layout.addWidget(self.show_password_check)

        self.remember_check = QCheckBox("Recordar usuario")
        layout.addWidget(self.remember_check)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addSpacing(4)
        layout.addWidget(self.error_label)

        self.login_button = QPushButton("Iniciar sesión")
        self.login_button.clicked.connect(self._on_login_clicked)
        layout.addSpacing(8)
        layout.addWidget(self.login_button)

        tagline = QLabel(APP_TAGLINE)
        tagline.setObjectName("versionLabel")
        tagline.setAlignment(Qt.AlignCenter)
        layout.addSpacing(4)
        layout.addWidget(tagline)

        # Enter envía el formulario desde cualquiera de los dos campos.
        self.username_input.returnPressed.connect(self._on_login_clicked)
        self.password_input.returnPressed.connect(self._on_login_clicked)

        return card

    @staticmethod
    def _soft_shadow() -> QGraphicsDropShadowEffect:
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 105, 120, 45))
        return shadow

    # -------------------------------------------------------------- Eventos

    def _on_toggle_password(self, visible: bool) -> None:
        self.password_input.setEchoMode(
            QLineEdit.Normal if visible else QLineEdit.Password
        )

    def _on_login_clicked(self) -> None:
        username = self.username_input.text()
        password = self.password_input.text()

        self.login_button.setEnabled(False)
        try:
            user = auth_service.authenticate(username, password)
        except (AuthenticationError, DatabaseConnectionError) as exc:
            self._show_error(str(exc))
            return
        except Exception:
            logger.exception("Error inesperado durante el login")
            self._show_error("Ocurrió un error inesperado al iniciar sesión.")
            return
        finally:
            self.login_button.setEnabled(True)

        self._save_remembered_username()
        self.password_input.clear()
        self.login_succeeded.emit(user)

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)

    # ---------------------------------------------------- Recordar usuario

    def _load_remembered_username(self) -> None:
        remember = self._settings.value(_SETTINGS_REMEMBER, False, type=bool)
        if remember:
            self.remember_check.setChecked(True)
            self.username_input.setText(
                self._settings.value(_SETTINGS_USERNAME, "", type=str)
            )
            self.password_input.setFocus()

    def _save_remembered_username(self) -> None:
        remember = self.remember_check.isChecked()
        self._settings.setValue(_SETTINGS_REMEMBER, remember)
        self._settings.setValue(
            _SETTINGS_USERNAME,
            self.username_input.text().strip().lower() if remember else "",
        )
