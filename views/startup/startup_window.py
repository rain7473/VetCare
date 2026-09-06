"""Ventana mínima de inicio de VetCare (Objetivo 1).

Muestra la identidad visual básica de la aplicación. En objetivos
posteriores esta pantalla dará paso al flujo real de arranque
(health check de Oracle, configuración inicial o login).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_DESCRIPTION, APP_NAME, APP_TAGLINE, APP_VERSION


class StartupWindow(QWidget):
    """Ventana de bienvenida con la identidad visual VetCare."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("appBackground")
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(640, 440)
        self.resize(760, 520)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 48, 48, 48)
        root.addStretch()
        root.addWidget(self._build_brand_card(), alignment=Qt.AlignCenter)
        root.addStretch()

    def _build_brand_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        card.setMinimumWidth(480)
        card.setGraphicsEffect(self._soft_shadow())

        layout = QVBoxLayout(card)
        layout.setContentsMargins(48, 40, 48, 32)
        layout.setSpacing(10)

        logo = QLabel("🐾")
        logo.setObjectName("logoBadge")
        logo.setFixedSize(72, 72)
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo, alignment=Qt.AlignCenter)
        layout.addSpacing(8)

        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(APP_DESCRIPTION)
        subtitle.setObjectName("appSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(6)
        accent = QFrame()
        accent.setObjectName("accentLine")
        accent.setFixedWidth(120)
        layout.addWidget(accent, alignment=Qt.AlignCenter)
        layout.addSpacing(6)

        tagline = QLabel(APP_TAGLINE)
        tagline.setObjectName("appTagline")
        tagline.setAlignment(Qt.AlignCenter)
        layout.addWidget(tagline)

        layout.addSpacing(12)
        version = QLabel(f"Versión {APP_VERSION}")
        version.setObjectName("versionLabel")
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)

        return card

    @staticmethod
    def _soft_shadow() -> QGraphicsDropShadowEffect:
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 105, 120, 45))
        return shadow
