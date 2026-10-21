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
from views.audit.audit_page import AuditPage
from views.appointments.appointments_page import AppointmentsPage
from views.consultations.consultations_page import ConsultationsPage
from views.dashboard.dashboard_page import DashboardPage, QUICK_ACTIONS
from views.hospitalization.hospitalization_page import HospitalizationPage
from views.inventory.inventory_page import InventoryPage
from views.owners.owners_page import OwnersPage
from views.pets.pets_page import PetsPage
from views.placeholder_page import PlaceholderPage
from views.sales.sales_page import SalesPage
from views.triage.triage_page import TriagePage
from views.users.users_page import UsersPage
from views.vaccines.vaccines_page import VaccinesPage
from widgets.sidebar import Sidebar
from widgets.topbar import Topbar

logger = logging.getLogger(__name__)

# Módulos placeholder: clave → (título, objetivo en el que se implementa)
_PLACEHOLDER_PAGES: dict[str, tuple[str, int | None]] = {
    "settings": ("Configuración", None),
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
        dashboard = DashboardPage(self._user)
        dashboard.navigated.connect(self.navigate_to)
        dashboard.create_requested.connect(self._create_from_dashboard)
        self.logout_requested.connect(dashboard.deactivate)
        self._add_page("dashboard", dashboard)
        if "owners" in allowed:
            self._add_page("owners", OwnersPage())
        if "pets" in allowed:
            pets_page = PetsPage()
            pets_page.open_consultation_requested.connect(self._open_consultation_for_pet)
            pets_page.open_history_requested.connect(self._open_consultation_history)
            pets_page.open_vaccination_requested.connect(self._open_vaccination_for_pet)
            self._add_page("pets", pets_page)
        if "appointments" in allowed:
            self._add_page("appointments", AppointmentsPage())
        if "triage" in allowed:
            self._add_page("triage", TriagePage())
        if "consultations" in allowed:
            self._add_page("consultations", ConsultationsPage())
        if "vaccines" in allowed:
            self._add_page("vaccines", VaccinesPage())
        if "hospitalization" in allowed:
            self._add_page("hospitalization", HospitalizationPage())
        if "inventory" in allowed:
            self._add_page("inventory", InventoryPage())
        if "sales" in allowed:
            self._add_page("sales", SalesPage())
        if "users" in allowed:
            self._add_page("users", UsersPage())
        if "audit" in allowed:
            self._add_page("audit", AuditPage())
        for key, (title, objective) in _PLACEHOLDER_PAGES.items():
            if key in allowed:
                self._add_page(key, PlaceholderPage(title, objective))
        right.addWidget(self.stack, stretch=1)

        root.addLayout(right, stretch=1)

    def _add_page(self, key: str, page: QWidget) -> None:
        self._page_index[key] = self.stack.addWidget(page)

    def _create_from_dashboard(self, key: str) -> None:
        action = QUICK_ACTIONS.get(key)
        if not action or key not in self._page_index:
            return
        if not permission_service.has_permission(action[1]):
            QMessageBox.warning(self, APP_NAME, "Permiso denegado: no puede crear este registro.")
            return
        self.navigate_to(key)
        self.stack.widget(self._page_index[key])._on_new()

    def closeEvent(self, event):
        self.stack.widget(self._page_index["dashboard"]).deactivate()
        super().closeEvent(event)

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
            page = self.stack.widget(self._page_index[key])
            refresh = getattr(page, "refresh", None)
            if callable(refresh):
                refresh()
            self.stack.setCurrentIndex(self._page_index[key])
            self.sidebar.set_active(key)

    def _open_consultation_for_pet(self, pet_id: int) -> None:
        if not permission_service.can_access_module("consultations"):
            QMessageBox.warning(
                self, APP_NAME, "Permiso denegado: no puede abrir consultas."
            )
            return
        self.navigate_to("consultations")
        page = self.stack.widget(self._page_index["consultations"])
        page.start_for_pet(pet_id)

    def _open_vaccination_for_pet(self, pet_id: int) -> None:
        if not permission_service.can_access_module("vaccines"):
            QMessageBox.warning(
                self, APP_NAME, "Permiso denegado: no puede gestionar vacunas."
            )
            return
        self.navigate_to("vaccines")
        page = self.stack.widget(self._page_index["vaccines"])
        page.start_for_pet(pet_id)

    def _open_consultation_history(self, pet_id: int) -> None:
        if not permission_service.can_access_module("consultations"):
            QMessageBox.warning(
                self, APP_NAME, "Permiso denegado: no puede abrir el historial."
            )
            return
        self.navigate_to("consultations")
        page = self.stack.widget(self._page_index["consultations"])
        page.filter_by_pet_id(pet_id)
