"""Ventana principal de VetCare: sidebar + topbar + área de módulos.

La sidebar y las páginas se construyen según los permisos del usuario
conectado; además, la navegación vuelve a verificar el permiso en la
lógica (defensa ante rutas internas).
"""

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_NAME
from models.user import User
from services import permission_service
from views.appointments.appointments_page import AppointmentsPage
from views.dashboard.dashboard_page import DashboardPage
from views.owners.owners_page import OwnersPage
from views.pets.pets_page import PetsPage
from views.placeholder_page import PlaceholderPage
from views.users.users_page import UsersPage
from widgets.sidebar import Sidebar
from widgets.topbar import Topbar

logger = logging.getLogger(__name__)

# Módulos placeholder: clave → (título, objetivo en el que se implementa)
_PLACEHOLDER_PAGES: dict[str, tuple[str, int]] = {
    "triage": ("Triaje", 10),
    "consultations": ("Consultas", 11),
    "vaccines": ("Vacunas", 14),
    "hospitalization": ("Hospitalización", 15),
    "inventory": ("Inventario", 19),
    "sales": ("Ventas", 21),
    "settings": ("Configuración", 23),
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

        allowed = permission_service.accessible_modules()

        self.sidebar = Sidebar(visible_keys=allowed)
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
        if "owners" in allowed:
            self._add_page("owners", OwnersPage())
        if "pets" in allowed:
            self._add_page("pets", PetsPage())
        if "appointments" in allowed:
            self._add_page("appointments", AppointmentsPage())
        if "users" in allowed:
            self._add_page("users", UsersPage())
        for key, (title, objective) in _PLACEHOLDER_PAGES.items():
            if key in allowed:
                self._add_page(key, PlaceholderPage(title, objective))
        right.addWidget(self.stack, stretch=1)

        root.addLayout(right, stretch=1)

    def _add_page(self, key: str, page: QWidget) -> None:
        self._page_index[key] = self.stack.addWidget(page)

    def navigate_to(self, key: str) -> None:
        """Cambia el módulo visible, verificando el permiso en la lógica."""
        if not permission_service.can_access_module(key):
            logger.warning("Acceso denegado al módulo '%s'", key)
            QMessageBox.warning(
                self,
                APP_NAME,
                "Permiso denegado: no tiene autorización para abrir este módulo.",
            )
            return
        if key in self._page_index:
            self.stack.setCurrentIndex(self._page_index[key])
            self.sidebar.set_active(key)
