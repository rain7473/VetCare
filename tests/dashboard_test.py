"""Dashboard: Oracle, filtros, autorización, gráficos y concurrencia Qt."""

import os
import threading
import time
import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QEvent, QObject, QThreadPool, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QVBoxLayout, QWidget
from main import create_app
from models.dashboard import DashboardMetric, DashboardPeriod, DashboardSeries, DashboardSnapshot
from models.user import User
from services import dashboard_service as service, permission_service, session
from repositories import dashboard_repository as repo
from database.connection import connection_scope
from views.dashboard.dashboard_page import DashboardPage
from widgets.dashboard_charts import SeriesChart, SpeciesChart, pg

ALL_PERMISSIONS = frozenset(c for codes in permission_service.MODULE_PERMISSIONS.values() for c in codes)


def user(role="ADMIN", user_id=0):
    return User(user_id, 1, "dashboard_test", None, "Prueba Dashboard", None, True, role_name=role)


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app([])

    def setUp(self):
        self.user = user()
        session.set_current_user(self.user, ALL_PERMISSIONS)
        self.pages = []

    def tearDown(self):
        for page in self.pages:
            page.deactivate()
            page.close()
        QThreadPool.globalInstance().waitForDone(5000)
        self.app.processEvents()
        session.clear()

    def page(self, loader):
        page = DashboardPage(self.user, loader=loader, autoload=False)
        self.pages.append(page)
        return page

    def wait(self, predicate, timeout=5):
        end = time.monotonic() + timeout
        while not predicate() and time.monotonic() < end:
            QTest.qWait(10)
        self.assertTrue(predicate(), "La carga no terminó dentro del plazo")

    def test_periods_and_validation(self):
        today = date(2026, 10, 12)
        self.assertEqual(service.resolve_period("today", today).start, today)
        self.assertEqual(service.resolve_period("7d", today).start, date(2026, 10, 6))
        self.assertEqual(service.resolve_period("30d", today).start, date(2026, 9, 13))
        self.assertEqual(service.resolve_period("month", today).start, date(2026, 10, 1))
        p = service.resolve_period("custom", today, date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual((p.previous.end-p.previous.start).days, 29)
        with self.assertRaises(ValueError):
            service.resolve_period("custom", today, today, date(2026, 10, 1))
        with self.assertRaises(ValueError):
            service.resolve_period("custom", today, today, date(2027, 1, 1))
        self.assertEqual(service.shift_month(date(2024, 2, 29), -12), date(2023, 2, 28))
        self.assertIn("Sin base", service.comparison_text(5, 0))

    def test_session_required_before_oracle(self):
        session.clear()
        with patch.object(service, "connection_scope") as connect:
            with self.assertRaises(permission_service.PermissionDeniedError):
                service.load_dashboard(self.user)
            connect.assert_not_called()

    def test_roles_real_oracle(self):
        expected = {"ADMIN": 11, "RECEPTION": 5, "VETERINARIAN": 5, "SALES": 5}
        for role, count in expected.items():
            with self.subTest(role=role):
                u = user(role)
                session.set_current_user(u, ALL_PERMISSIONS)
                snapshot = service.load_dashboard(u)
                self.assertEqual(len(snapshot.metrics), count)
                self.assertLessEqual(len(snapshot.recent_activity), 5)
                if role == "SALES":
                    self.assertIsNone(snapshot.consultations)
                    self.assertIsNone(snapshot.species)
                    self.assertIsNone(snapshot.appointment_states)
                    self.assertIsNotNone(snapshot.revenue)

    def test_permission_removal_applies_in_service(self):
        session.set_current_user(self.user, frozenset({"PETS_READ"}))
        snapshot = service.load_dashboard(self.user)
        self.assertEqual([m.key for m in snapshot.metrics], ["pets"])
        self.assertIsNone(snapshot.revenue)
        self.assertIsNone(snapshot.consultations)

    def test_filters_and_current_metrics_oracle(self):
        previous = None
        for key in ("today", "7d", "30d", "month"):
            p = service.resolve_period(key)
            s = service.load_dashboard(self.user, period=p)
            metrics = {m.key: m.value for m in s.metrics}
            self.assertEqual(sum(s.consultations.selected), int(metrics["period_consultations"]))
            self.assertAlmostEqual(sum(s.revenue.selected), float(metrics["period_revenue"].replace("$", "").replace(",", "")))
            current = {k: v for k, v in metrics.items() if not k.startswith("period_")}
            if previous is not None:
                self.assertEqual(current, previous)
            previous = current

    def test_aggregate_boundaries_status_and_scope_rollback(self):
        p = DashboardPeriod(date(2026, 9, 1), date(2026, 9, 30))
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("ALTER SESSION SET TIME_ZONE = '-05:00'")
                cur.execute("SELECT MIN(id) FROM users")
                uid = cur.fetchone()[0]
                cur.execute("SELECT MIN(id) FROM pets")
                pet_id = cur.fetchone()[0]
                if uid is None or pet_id is None:
                    self.skipTest("La prueba transaccional requiere un usuario y una mascota existentes")
                before = repo.period_summary(conn, "sales", p, uid)
                before_consults = repo.period_summary(conn, "consultations", p, uid)
                for status, stamp in (("COMPLETED", datetime(2026,9,1)), ("CANCELLED", datetime(2026,9,15)), ("COMPLETED", datetime(2026,10,1))):
                    cur.execute("""INSERT INTO sales(invoice_number,sold_by,subtotal,discount_amount,tax_amount,total,payment_method,status,sold_at)
                        VALUES(:invoice,:actor_id,12.34,0,0,12.34,'CASH',:status,:stamp)""",
                        {"invoice": "TEST-DASH-" + uuid4().hex, "actor_id": uid, "status": status, "stamp": stamp})
                cur.execute("""INSERT INTO consultations(pet_id,veterinarian_id,reason,status,started_at)
                    VALUES(:pet,:actor_id,'Prueba agregados rollback','DRAFT',:stamp)""",
                    {"pet": pet_id, "actor_id": uid, "stamp": datetime(2026,9,30,23,59,59)})
                self.assertEqual(repo.period_summary(conn, "sales", p, uid), before + Decimal("12.34"))
                self.assertEqual(repo.period_summary(conn, "consultations", p, uid), before_consults + 1)
                self.assertEqual(repo.period_summary(conn, "sales", p, -1), 0)
                self.assertAlmostEqual(repo.monthly_totals(conn,"sales",p.start,p.end,uid)["2026-09"], float(before + Decimal("12.34")))
            conn.rollback()

    def test_empty_and_populated_charts(self):
        self.assertEqual(pg.Qt.QT_LIB, "PySide6")
        for line in (False, True):
            chart = SeriesChart("Prueba", "sales", line=line, monthly=True)
            chart.set_series(DashboardSeries(), "Vacío")
            self.assertFalse(chart.empty.isHidden())
            chart.set_series(DashboardSeries(("Sep", "Oct"), (10,20), (0,15), (5,7)), "Prueba")
            self.assertTrue(chart.empty.isHidden())
            self.assertIn("15", chart.tooltip_at(1))
            chart.compare.setChecked(False)
            self.assertNotIn("año anterior", chart.tooltip_at(1))
            chart.close()
        donut = SpeciesChart()
        donut.set_series(DashboardSeries(("Canino", "Felino"), (3,1)))
        self.assertIn("75%", donut.legend.text())
        donut.set_series(DashboardSeries())
        self.assertIn("Sin mascotas", donut.legend.text())

    def test_dashboard_render_never_opens_auxiliary_windows(self):
        """Los gráficos y paneles deben vivir dentro del shell desde su creación."""
        unexpected_shows = []

        class WindowWatcher(QObject):
            def eventFilter(self, obj, event):
                if (
                    event.type() == QEvent.Show
                    and isinstance(obj, QWidget)
                    and obj.isWindow()
                    and obj is not shell
                ):
                    unexpected_shows.append(type(obj).__name__)
                return False

        shell = QWidget()
        watcher = WindowWatcher()
        self.app.installEventFilter(watcher)
        try:
            layout = QVBoxLayout(shell)
            page = self.page(lambda u, **kw: None)
            layout.addWidget(page)
            shell.show()
            self.app.processEvents()

            series = DashboardSeries(("Sep", "Oct"), (3, 5), (2, 4), (1, 2))
            populated = DashboardSnapshot(
                "ADMIN",
                (DashboardMetric("pets", "Mascotas", "3", "pets", module="pets"),),
                consultations=series,
                revenue=series,
                species=series,
                appointment_states=series,
            )
            page._render(populated)
            self.app.processEvents()
            page._render(DashboardSnapshot("ADMIN", ()))
            page._render(populated)
            self.app.processEvents()

            self.assertEqual(unexpected_shows, [])
            self.assertEqual(
                [w for w in self.app.topLevelWidgets() if w.isVisible()], [shell]
            )
            self.assertTrue(all(not w.isWindow() for w in page.charts + page.panels))
        finally:
            self.app.removeEventFilter(watcher)
            shell.close()

    def test_main_window_construction_never_shows_orphan_controls(self):
        """La carga del shell no debe mostrar botones de otras páginas."""
        from views.main_window import MainWindow

        unexpected_shows = []
        window = None

        class WindowWatcher(QObject):
            def eventFilter(self, obj, event):
                if (
                    event.type() == QEvent.Show
                    and isinstance(obj, QWidget)
                    and obj.isWindow()
                    and obj is not window
                ):
                    unexpected_shows.append(type(obj).__name__)
                return False

        watcher = WindowWatcher()
        self.app.installEventFilter(watcher)
        try:
            window = MainWindow(self.user)
            dashboard = window.stack.widget(window._page_index["dashboard"])
            dashboard.deactivate()  # Esta prueba inspecciona la construcción Qt.
            window.show()
            self.app.processEvents()
            self.assertEqual(unexpected_shows, [])
        finally:
            self.app.removeEventFilter(watcher)
            if window is not None:
                window.close()

    def test_async_load_and_card_navigation(self):
        snapshot = DashboardSnapshot("ADMIN", (DashboardMetric("pets","Mascotas","3","pets",module="pets"),))
        page = self.page(lambda u, **kw: snapshot)
        destinations = []
        page.navigated.connect(destinations.append)
        page.refresh()
        self.wait(lambda: bool(page.cards))
        self.assertEqual(page.cards["pets"].value_label.text(), "3")
        QTest.keyClick(page.cards["pets"], Qt.Key_Return)
        self.assertEqual(destinations, ["pets"])

    def test_slow_query_does_not_block_and_latest_filter_wins(self):
        gate = threading.Event()
        calls = []
        def loader(u, *, period):
            calls.append(period)
            gate.wait(2)
            return DashboardSnapshot("ADMIN", (), period=period)
        page = self.page(loader)
        ticks = []
        try:
            started = time.monotonic()
            page.refresh()
            self.assertLess(time.monotonic()-started, .15)
            QTimer.singleShot(0, lambda: ticks.append(True))
            self.wait(lambda: bool(ticks))
            page.period_combo.setCurrentIndex(0)
            page._filter_timer.stop()
            page.refresh()
        finally:
            gate.set()
        self.wait(lambda: not page._busy and page._snapshot is not None)
        self.assertEqual(page._snapshot.period.label, "Hoy")
        self.assertEqual(len(calls), 2)

    def test_error_preserves_last_snapshot_and_recovers(self):
        snapshot = DashboardSnapshot("ADMIN", ())
        page = self.page(lambda u, **kw: snapshot)
        page.refresh()
        self.wait(lambda: page._snapshot is not None)
        def fail(*args, **kw):
            raise RuntimeError("Fallo simulado")
        page._loader = fail
        with self.assertLogs("views.dashboard.dashboard_page", level="ERROR"):
            page.refresh()
            self.wait(lambda: not page._busy)
        self.assertIs(page._snapshot, snapshot)
        self.assertFalse(page.error_label.isHidden())
        page._loader = lambda u, **kw: snapshot
        page.refresh()
        self.wait(lambda: not page._busy)
        self.assertTrue(page.error_label.isHidden())

    def test_logout_discards_inflight_result(self):
        page = self.page(lambda u, **kw: DashboardSnapshot("ADMIN", ()))
        page.refresh()
        page.deactivate()
        self.wait(lambda: not page._busy)
        self.assertIsNone(page._snapshot)

    def test_custom_filter_reaches_oracle(self):
        page = self.page(service.load_dashboard)
        page.period_combo.setCurrentIndex(4)
        page.start_date.setDate(QDate(2026, 9, 1))
        page.end_date.setDate(QDate(2026, 9, 30))
        self.wait(lambda: page._snapshot is not None)
        self.assertEqual(page._snapshot.period.start, date(2026,9,1))
        self.assertEqual(page._snapshot.period.end, date(2026,9,30))
        self.assertFalse(page.custom_range.isHidden())
        previous = page._snapshot
        page.start_date.setDate(QDate(2026,10,1))
        self.wait(lambda: not page.error_label.isHidden())
        self.assertIs(page._snapshot, previous)

    def test_responsive_layout(self):
        snapshot = service.load_dashboard(self.user)
        page = self.page(lambda u, **kw: snapshot)
        page._render(snapshot)
        page.show()
        for width, height in ((1100,680), (1650,990), (700,600)):
            page.resize(width,height)
            QTest.qWait(40)
            self.assertEqual(page.scroll.horizontalScrollBar().maximum(), 0, f"ancho={width}, mínimo={page.scroll.widget().minimumSizeHint().width()}")
            for card in page.cards.values():
                self.assertGreater(card.width(), 180)

    def test_main_window_routes_and_quick_actions(self):
        from views.main_window import MainWindow
        from views.pets.pets_page import PetsPage
        from PySide6.QtWidgets import QMessageBox
        window = MainWindow(self.user)
        page = window.stack.widget(window._page_index["dashboard"])
        page.deactivate()  # Esta prueba comprueba rutas, no inicia otro worker.
        page._render(service.load_dashboard(self.user))
        try:
            for metric in page._snapshot.metrics:
                page.cards[metric.key].clicked.emit()
                self.assertEqual(window.stack.currentIndex(), window._page_index[metric.module])
            with patch.object(PetsPage, "_on_new") as create:
                window._create_from_dashboard("pets")
                create.assert_called_once()
                session.set_current_user(self.user, frozenset({"PETS_READ"}))
                with patch.object(QMessageBox, "warning") as denied:
                    window._create_from_dashboard("pets")
                    denied.assert_called_once()
                    self.assertEqual(create.call_count, 1)
        finally:
            window.close()

    def test_vaccine_latest_application_only_rollback(self):
        from repositories import vaccine_repository
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT MIN(id) FROM users")
                actor_id = cur.fetchone()[0]
                cur.execute("SELECT MIN(id) FROM pets WHERE status='ACTIVE'")
                pet_id = cur.fetchone()[0]
                if actor_id is None or pet_id is None:
                    self.skipTest("Requiere usuario y mascota activa")
            end = date(2026,10,31)
            baseline = repo.pending_vaccines(conn, end)
            vaccine_id = vaccine_repository.insert_vaccine(conn, name="DASH-"+uuid4().hex, manufacturer=None, description="Prueba con rollback")
            for applied, due in ((date(2026,1,1),date(2026,2,1)), (date(2026,3,1),date(2027,3,1))):
                vaccine_repository.insert_application(conn, pet_id=pet_id, vaccine_id=vaccine_id,
                    consultation_id=None, applied_by=actor_id, applied_at=applied,
                    lot_number=None, expiry_date=None, next_due_date=due, notes=None)
            self.assertEqual(repo.pending_vaccines(conn, end), baseline)
            conn.rollback()

    def test_alerts_priority_and_permissions_rollback(self):
        with connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT MIN(id) FROM pets")
                pet_id = cur.fetchone()[0]
                if pet_id is None:
                    self.skipTest("Requiere mascota existente")
                for severity in ("LOW", "CRITICAL", "HIGH"):
                    cur.execute("""INSERT INTO clinical_alerts(pet_id,alert_type,severity,message,status)
                        VALUES(:pet,'TEST',:severity,'Prueba dashboard rollback','OPEN')""",
                        {"pet": pet_id, "severity": severity})
            alerts = repo.list_alerts_and_triage(conn, date.today(), limit=100)
            ranks = {"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3}
            self.assertEqual([ranks[a.severity] for a in alerts], sorted(ranks[a.severity] for a in alerts))
            hidden = repo.list_alerts_and_triage(conn,date.today(),clinical=False,triage=False)
            self.assertEqual(hidden, [])
            conn.rollback()


if __name__ == "__main__":
    unittest.main(verbosity=2)
