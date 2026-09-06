"""Card de indicador (stat card) para dashboards de VetCare."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


class StatCard(QFrame):
    """Card blanca con título, valor destacado e ícono."""

    def __init__(self, title: str, value: str, icon: str) -> None:
        super().__init__()
        self.setProperty("card", True)
        self.setMinimumHeight(96)
        self.setMaximumHeight(120)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        text_box = QVBoxLayout()
        text_box.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("statTitle")
        self.title_label.setWordWrap(True)
        text_box.addWidget(self.title_label)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("statValue")
        text_box.addWidget(self.value_label)
        text_box.addStretch()

        layout.addLayout(text_box, stretch=1)

        icon_label = QLabel(icon)
        icon_label.setObjectName("statIcon")
        icon_label.setAlignment(Qt.AlignTop | Qt.AlignRight)
        layout.addWidget(icon_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
