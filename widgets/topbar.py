"""Topbar de VetCare: búsqueda global, notificaciones y usuario conectado."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QVBoxLayout,
)

from config.constants import ROLE_DISPLAY_NAMES
from models.user import User


class Topbar(QFrame):
    """Barra superior de la ventana principal."""

    logout_requested = Signal()

    def __init__(self, user: User) -> None:
        super().__init__()
        self.setObjectName("topbar")
        self.setFixedHeight(64)
        self._user = user
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 10, 24, 10)
        layout.setSpacing(16)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("globalSearch")
        self.search_input.setPlaceholderText(
            "🔎  Buscar propietario, mascota, cita o historial..."
        )
        self.search_input.setFixedHeight(38)
        self.search_input.setMaximumWidth(520)
        self.search_input.setToolTip(
            "Búsqueda global (se activa en un objetivo posterior)"
        )
        layout.addWidget(self.search_input, stretch=1)

        layout.addStretch()

        self.notifications_button = QPushButton("🔔")
        self.notifications_button.setObjectName("notifButton")
        self.notifications_button.setFixedSize(38, 38)
        self.notifications_button.setToolTip(
            "Notificaciones (se activan en un objetivo posterior)"
        )
        layout.addWidget(self.notifications_button)

        layout.addWidget(self._build_user_chip())

    def _build_user_chip(self) -> QFrame:
        chip = QFrame()
        chip.setObjectName("userChip")

        layout = QHBoxLayout(chip)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(10)

        avatar = QLabel(self._initials())
        avatar.setObjectName("avatarBadge")
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignCenter)
        layout.addWidget(avatar)

        text_box = QVBoxLayout()
        text_box.setSpacing(0)

        name = QLabel(self._user.full_name)
        name.setObjectName("topbarUserName")
        text_box.addWidget(name)

        role = QLabel(
            ROLE_DISPLAY_NAMES.get(self._user.role_name or "", self._user.role_name or "")
        )
        role.setObjectName("topbarUserRole")
        text_box.addWidget(role)

        layout.addLayout(text_box)

        menu_button = QPushButton("▾")
        menu_button.setObjectName("userMenuButton")
        menu_button.setFixedSize(28, 28)
        menu_button.setCursor(Qt.PointingHandCursor)

        menu = QMenu(menu_button)
        logout_action = menu.addAction("Cerrar sesión")
        logout_action.triggered.connect(self.logout_requested.emit)
        menu_button.setMenu(menu)
        layout.addWidget(menu_button)

        return chip

    def _initials(self) -> str:
        parts = [p for p in self._user.full_name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()
