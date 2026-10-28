"""Configuración, búsqueda, avisos y calendario (Oracle con rollback)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from contextlib import contextmanager
from unittest.mock import patch, Mock
from PySide6.QtWidgets import QWidget, QCalendarWidget, QVBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from main import create_app
from models.user import User
from models.dashboard import DashboardSnapshot, DashboardItem
from services import session, settings_service, global_search_service, permission_service
from database.connection import connection_scope
from repositories import global_search_repository, settings_repository
from widgets.topbar import Topbar
from widgets.global_tools import GlobalTools


class GlobalToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app([])

    def setUp(self):
        self.user = User(0, 1, "test", None, "Prueba", None, True, role_name="ADMIN")
        session.set_current_user(self.user, frozenset({"SETTINGS_MANAGE", "PETS_READ"}))

    def tearDown(self):
        session.clear()

    def test_search_permissions_and_literal_patterns(self):
        with patch.object(global_search_repository, "search", return_value=[]) as query:
            global_search_service.search(self.user, "Luna")
            self.assertEqual(query.call_args.args[2], ["pets"])
        with connection_scope() as conn:
            for module in global_search_repository.QUERIES:
                self.assertIsInstance(global_search_repository.search(conn, "a", [module]), list)
            self.assertEqual(global_search_repository.search(conn, "%' OR 1=1 --", ["pets"]), [])
            self.assertTrue(global_search_repository.search(conn, "maria", ["owners"]))
        session.clear()
        with patch.object(global_search_service, "connection_scope") as connect:
            self.assertEqual(global_search_service.search(self.user, "Luna"), [])
            connect.assert_not_called()

    def test_settings_atomic_rollback(self):
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT MIN(id) FROM users")
                user_id = cur.fetchone()[0]
            if user_id is None:
                self.skipTest("Requiere un usuario existente para la auditoría")
            u = User(user_id, 1, "test", None, "Prueba", None, True, role_name="ADMIN")
            session.set_current_user(u, frozenset({"SETTINGS_MANAGE"}))
            before = settings_repository.read_settings(conn)
            @contextmanager
            def transaction(**kwargs):
                yield conn
            with patch.object(settings_service, "connection_scope", transaction):
                settings_service.save({k: "Clínica prueba" if k == "CLINIC_NAME" else "" for k in settings_service.FIELDS})
                self.assertEqual(settings_service.load()["CLINIC_NAME"], "Clínica prueba")
            conn.rollback()
            self.assertEqual(settings_repository.read_settings(conn), before)
        session.clear()
        with self.assertRaises(permission_service.PermissionDeniedError):
            settings_service.load()

    def test_calendar_cells_fit(self):
        calendar = QCalendarWidget()
        calendar.show()
        self.app.processEvents()
        self.assertEqual(calendar.horizontalHeaderFormat(), QCalendarWidget.ShortDayNames)
        self.assertGreaterEqual(calendar.width(), 350)
        calendar.close()

    def test_notifications_deduplicate_and_stop(self):
        window = QWidget()
        window._user = self.user
        window.topbar = Topbar(self.user)
        window.navigate_to = Mock()
        controller = GlobalTools(window)
        snapshot = DashboardSnapshot("ADMIN", (), alerts_and_triage=(DashboardItem("Aviso", "Detalle", module="pets"),))
        with patch.object(controller.tray, "isVisible", return_value=True), patch.object(controller.tray, "showMessage") as notify:
            controller.finished("notifications", snapshot, False)
            controller.finished("notifications", snapshot, False)
            self.assertEqual(notify.call_count, 1)
            controller.stop()
            controller.finished("notifications", snapshot, False)
            self.assertEqual(notify.call_count, 1)
        window.close()

    def test_dashboard_autocomplete_preserves_typing_and_discards_late_results(self):
        window = QWidget()
        window._user = self.user
        window.topbar = Topbar(self.user)
        QVBoxLayout(window).addWidget(window.topbar)
        with patch.object(GlobalTools, "poll"):
            controller = GlobalTools(window)
            try:
                window.show()
                field = window.topbar.search_input
                field.setFocus()
                self.app.processEvents()
                rows = [("pets", 7, "Luna", "Propietario")]
                with patch.object(controller, "launch", side_effect=lambda *_: controller.finished("search", rows, False)):
                    QTest.keyClicks(field, "l")
                    QTest.qWait(350)
                    self.assertTrue(controller.completer.popup().isVisible())
                    self.assertEqual(field.text(), "l")
                    self.assertEqual(controller.search_model.index(0, 0).data(Qt.UserRole), ("pets", 7))
                    QTest.keyClicks(field, "u")
                    QTest.qWait(350)
                    self.assertEqual(field.text(), "lu")
                    self.assertTrue(controller.completer.popup().isVisible())
                    controller.set_search_enabled(False)
                    controller.finished("search", rows, False)
                    self.assertTrue(field.isHidden())
                    self.assertFalse(controller.completer.popup().isVisible())
                    self.assertEqual(controller.search_model.rowCount(), 0)
                    controller.set_search_enabled(True)
                    self.assertEqual(field.text(), "")
            finally:
                controller.stop()
                window.close()

    def test_dashboard_search_is_case_insensitive(self):
        window = QWidget()
        window._user = self.user
        window.topbar = Topbar(self.user)
        with patch.object(GlobalTools, "poll"):
            controller = GlobalTools(window)
            try:
                self.assertEqual(controller.completer.caseSensitivity(), Qt.CaseInsensitive)
            finally:
                controller.stop()
                window.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
