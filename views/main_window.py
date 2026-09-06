"""Ventana principal de VetCare: sidebar + topbar + área de módulos."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_NAME
from models.user import User
from views.dashboard.dashboard_page import DashboardPage
from views.placeholder_page import PlaceholderPage
from widgets.sidebar import Sidebar
from widgets.topbar import Topbar

# Módulos placeholder: clave → (título, objetivo en el que se implementa)
_PLACEHOLDER_PAGES: dict[str, tuple[str, int]] = {
    "owners": ("Propietarios", 7),
    "pets": ("Mascotas", 8),
    "appointments": ("Citas", 9),
    "triage": ("Triaje", 10),
    "consultations": ("Consultas", 11),
    "vaccines": ("Vacunas", 14),
    "hospitalization": ("Hospitalización", 15),
    "inventory": ("Inventario", 19),
    "sales": ("Ventas", 21),
    "users": ("Usuarios", 6),
    "settings": ("Configuración", 6),
}


class MainWindow(QMainWindow):
    """Shell principal: navegación sin abrir ventanas nuevas."""

    logout_requested = Signal()

    def __init__(self, user: User) -> None:
        super().__init__()
        self._user = user
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1200, 700)
        self.resize(1366, 768)
        self._page_index: dict[str, int] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("appBackground")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigated.connect(self.navigate_to)
        root.addWidget(self.sidebar)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        self.topbar = Topbar(self._user)
        self.topbar.logout_requested.connect(self.logout_requested.emit)
        right.addWidget(self.topbar)

        self.stack = QStackedWidget()
        self._add_page("dashboard", DashboardPage(self._user))
        for key, (title, objective) in _PLACEHOLDER_PAGES.items():
            self._add_page(key, PlaceholderPage(title, objective))
        right.addWidget(self.stack, stretch=1)

        root.addLayout(right, stretch=1)

    def _add_page(self, key: str, page: QWidget) -> None:
        self._page_index[key] = self.stack.addWidget(page)

    def navigate_to(self, key: str) -> None:
        """Cambia el módulo visible y sincroniza la sidebar."""
        if key in self._page_index:
            self.stack.setCurrentIndex(self._page_index[key])
            self.sidebar.set_active(key)
