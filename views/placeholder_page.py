"""Página placeholder para módulos aún no implementados."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class PlaceholderPage(QWidget):
    """Página con el título del módulo y una nota de desarrollo."""

    def __init__(self, title: str, objective: int) -> None:
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

        note = QLabel(
            f"Este módulo se implementará en el Objetivo {objective}."
        )
        note.setObjectName("screenSubtitle")
        note.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(note)

        layout.addWidget(card)
        layout.addStretch()
