"""Card de indicador (stat card) para dashboards de VetCare."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QSizePolicy
from utils.icons import icon_label


class StatCard(QFrame):
    """Card blanca con título, valor destacado e ícono."""

    clicked = Signal()

    def __init__(self, title: str, value: str, icon: str, detail: str = "", *, clickable=False, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.setObjectName("dashboardStatCard")
        self.setMinimumHeight(112)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.PointingHandCursor)
            self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(f"{title}: {value}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
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

        self.detail_label = QLabel(detail, self)
        self.detail_label.setObjectName("statDetail")
        self.detail_label.setWordWrap(True)
        text_box.addWidget(self.detail_label)
        self.detail_label.setVisible(bool(detail))
        text_box.addStretch()

        layout.addLayout(text_box, stretch=1)

        graphic = icon_label(icon, 28)
        layout.addWidget(graphic, alignment=Qt.AlignTop | Qt.AlignRight)

    def mouseReleaseEvent(self, event):
        if self._clickable and event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self._clickable and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)

    def set_detail(self, detail: str) -> None:
        self.detail_label.setText(detail)
        self.detail_label.setVisible(bool(detail))
