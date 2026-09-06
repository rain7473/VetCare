"""Página de dashboard (estructura visual).

Los indicadores muestran «—» hasta que el Objetivo 22 los conecte a
Oracle y los adapte por rol.
"""

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from config.constants import ROLE_DISPLAY_NAMES
from models.user import User
from widgets.stat_card import StatCard


class DashboardPage(QWidget):
    """Dashboard de bienvenida con stat cards."""

    def __init__(self, user: User) -> None:
        super().__init__()
        self.setObjectName("pageArea")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        first_name = user.full_name.split()[0] if user.full_name.split() else ""
        title = QLabel(f"Hola, {first_name} 👋")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        role_display = ROLE_DISPLAY_NAMES.get(user.role_name or "", user.role_name or "")
        subtitle = QLabel(f"Sesión iniciada como {role_display}.")
        subtitle.setObjectName("screenSubtitle")
        layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setSpacing(16)

        self.cards = {
            "pets": StatCard("Mascotas registradas", "—", "🐾"),
            "appointments": StatCard("Citas de hoy", "—", "📅"),
            "hospitalized": StatCard("Hospitalizados", "—", "🛏"),
            "low_stock": StatCard("Stock bajo", "—", "📦"),
        }
        for column, card in enumerate(self.cards.values()):
            grid.addWidget(card, 0, column)

        layout.addLayout(grid)

        note = QLabel("Los indicadores se conectarán a Oracle en el Objetivo 22.")
        note.setObjectName("versionLabel")
        layout.addWidget(note)
        layout.addStretch()
