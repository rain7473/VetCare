"""Página placeholder para módulos aún no implementados."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
from utils.icons import icon_label


class PlaceholderPage(QWidget):
    """Página con el título del módulo y una nota de desarrollo."""

    def __init__(self, title: str, objective: int | None) -> None:
        super().__init__()
        self.setObjectName("pageArea")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QLabel(title)
        header.setObjectName("pageTitle")
        layout.addWidget(header)

        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 40, 32, 40)
        card_layout.addWidget(icon_label("settings", 32), alignment=Qt.AlignCenter)

        message = (
            f"Este módulo se implementará en el Objetivo {objective}."
            if objective is not None
            else "Módulo reservado para una futura versión."
        )
        note = QLabel(message)
        note.setObjectName("screenSubtitle")
        note.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(note)

        layout.addWidget(card)
        layout.addStretch()
