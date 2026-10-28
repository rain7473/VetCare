"""Sidebar de navegación de VetCare (fija a la izquierda)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from config.constants import APP_FOOTER_MOTTO, APP_NAME, APP_TAGLINE
from utils.branding import SYMBOL_LOGO_PATH, scaled_logo
from utils.icons import set_button_icon

# (clave, ícono, etiqueta)
NAV_ITEMS: list[tuple[str, str, str]] = [
    ("dashboard", "dashboard", "Dashboard"),
    ("owners", "owners", "Propietarios"),
    ("pets", "pets", "Mascotas"),
    ("appointments", "appointments", "Citas"),
    ("triage", "triage", "Triaje"),
    ("consultations", "consultations", "Consultas"),
    ("vaccines", "vaccines", "Vacunas"),
    ("hospitalization", "hospitalization", "Hospitalización"),
    ("inventory", "inventory", "Inventario"),
    ("sales", "sales", "Ventas"),
    ("users", "users", "Usuarios"),
    ("audit", "audit", "Auditoría"),
    ("settings", "settings", "Configuración"),
]


class Sidebar(QFrame):
    """Menú lateral con estado activo por módulo.

    Solo muestra los módulos incluidos en ``visible_keys`` (determinados
    por los permisos del usuario conectado).
    """

    navigated = Signal(str)  # clave del módulo seleccionado

    def __init__(self, visible_keys: set[str] | None = None) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(232)
        self._visible_keys = visible_keys
        self._buttons: dict[str, QPushButton] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 20, 14, 16)
        layout.setSpacing(2)

        brand = QHBoxLayout()
        brand.setSpacing(9)

        logo = QLabel()
        logo.setObjectName("sidebarLogo")
        logo.setFixedSize(38, 38)
        logo.setAlignment(Qt.AlignCenter)
        logo.setPixmap(scaled_logo(SYMBOL_LOGO_PATH, 32, 32))
        brand.addWidget(logo, 0, Qt.AlignVCenter)

        identity = QVBoxLayout()
        identity.setContentsMargins(0, 3, 0, 3)
        identity.setSpacing(1)
        title = QLabel(APP_NAME)
        title.setObjectName("sidebarTitle")
        identity.addWidget(title)

        subtitle = QLabel(APP_TAGLINE)
        subtitle.setObjectName("sidebarSubtitle")
        identity.addWidget(subtitle)
        brand.addLayout(identity, 1)
        layout.addLayout(brand)
        layout.addSpacing(14)

        group = QButtonGroup(self)
        group.setExclusive(True)

        for key, icon, label in NAV_ITEMS:
            if self._visible_keys is not None and key not in self._visible_keys:
                continue
            button = QPushButton(label)
            set_button_icon(button, icon, color="#C7EDF0", active="#FFFFFF")
            button.setProperty("nav", True)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.navigated.emit(k))
            group.addButton(button)
            layout.addWidget(button)
            self._buttons[key] = button

        layout.addStretch()

        footer = QLabel(APP_FOOTER_MOTTO)
        footer.setObjectName("sidebarFooter")
        footer.setWordWrap(True)
        layout.addWidget(footer)

        if "dashboard" in self._buttons:
            self._buttons["dashboard"].setChecked(True)

    def set_active(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)
