"""Búsqueda y avisos asíncronos ligados al ciclo de sesión del shell."""
import logging
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot, QSettings, Qt, QModelIndex
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QMenu, QCompleter, QSystemTrayIcon
from services import global_search_service, dashboard_service, session, permission_service
from utils.icons import icon

logger = logging.getLogger(__name__)


class Signals(QObject):
    done = Signal(str, object, object)


class Job(QRunnable):
    def __init__(self, kind, task):
        super().__init__()
        self.signals = Signals()
        self.kind, self.task = kind, task

    def run(self):
        try:
            result = self.task()
        except Exception:
            logger.exception("Carga de %s", self.kind)
            self.signals.done.emit(self.kind, None, True)
        else:
            self.signals.done.emit(self.kind, result, False)


class GlobalTools(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window, self.user = window, window._user
        self.active = True
        self.jobs = {}
        self.last_query = ""
        self.search_enabled = True
        self.seen = set()
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self.search)
        bar = window.topbar
        bar.search_input.setMaxLength(100)
        bar.search_input.setToolTip("Escriba para ver coincidencias. Seleccione con clic o flechas y Enter.")
        self.search_model = QStandardItemModel(self)
        self.completer = QCompleter(self.search_model, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.completer.setMaxVisibleItems(8)
        self.completer.popup().setObjectName("globalSearchPopup")
        self.completer.popup().setUniformItemSizes(True)
        bar.search_input.setCompleter(self.completer)
        self.completer.activated[QModelIndex].connect(self.open_result)
        bar.search_input.textEdited.connect(self.query_edited)
        self.menu = QMenu(bar.notifications_button)
        bar.notifications_button.setMenu(self.menu)
        self.menu.addAction("Revisando avisos…").setEnabled(False)
        self.tray = QSystemTrayIcon(icon("notifications"), self)
        self.tray.setToolTip("VetCare")
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.tray.messageClicked.connect(lambda: self.menu.popup(bar.notifications_button.mapToGlobal(bar.notifications_button.rect().bottomLeft())))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(60000)
        QTimer.singleShot(0, self.poll)

    def stop(self):
        self.active = False
        self.timer.stop()
        self.search_timer.stop()
        self.completer.popup().hide()
        self.tray.hide()

    def set_search_enabled(self, enabled):
        self.search_enabled = enabled
        self.window.topbar.search_input.setVisible(enabled)
        if not enabled:
            self.search_timer.stop()
            self.completer.popup().hide()
            self.search_model.clear()
            self.window.topbar.search_input.clear()
            self.last_query = ""

    def query_edited(self, text):
        # Retirar coincidencias anteriores evita seleccionar un ID de otra consulta.
        self.search_model.clear()
        self.completer.popup().hide()
        self.search_timer.stop()
        if self.active and self.search_enabled and text.strip():
            self.search_timer.start()

    def launch(self, kind, task):
        if kind in self.jobs:
            return
        job = Job(kind, task)
        job.signals.done.connect(self.finished, Qt.QueuedConnection)
        self.jobs[kind] = job
        QThreadPool.globalInstance().start(job)

    def search(self):
        if not self.active or not self.search_enabled:
            return
        text = self.window.topbar.search_input.text().strip()
        if not text:
            self.completer.popup().hide()
            return
        if "search" in self.jobs:
            self.search_timer.start()
            return
        self.last_query = text
        self.launch("search", lambda: global_search_service.search(self.user, text))

    def poll(self):
        if not self.active:
            return
        prefs = QSettings("VetCare", "VetCare")
        interval = prefs.value(f"notifications/{self.user.id}/interval", 60, type=int)
        self.timer.setInterval(max(30, min(interval, 3600)) * 1000)
        self.launch("notifications", lambda: dashboard_service.load_dashboard(self.user))

    @Slot(str, object, object)
    def finished(self, kind, result, failed):
        self.jobs.pop(kind, None)
        if not self.active or session.get_current_user() != self.user:
            return
        if kind == "search":
            field = self.window.topbar.search_input
            if (not self.search_enabled or not field.hasFocus()
                    or not self.last_query or self.last_query != field.text().strip()):
                return
            self.search_model.clear()
            for module, id_, title, detail in result or []:
                if not permission_service.has_permission(global_search_service.REQUIRED[module]):
                    continue
                label = {"owners": "Propietario", "pets": "Mascota", "appointments": "Cita", "consultations": "Consulta"}[module]
                item = QStandardItem(f"{label} #{id_} · {title} · {detail}")
                item.setData((module, id_), Qt.UserRole)
                self.search_model.appendRow(item)
            if not self.search_model.rowCount():
                item = QStandardItem("No se pudo buscar. Intente de nuevo." if failed else "Sin coincidencias")
                item.setFlags(Qt.NoItemFlags)
                self.search_model.appendRow(item)
            self.completer.complete(field.rect())
            return
        if failed:
            self.window.topbar.notifications_button.setToolTip("No se pudieron actualizar los avisos. Se reintentará automáticamente.")
            return
        entries = [(i.title, i.detail, i.module) for i in (*result.alerts_and_triage, *result.weekly_appointments)]
        for metric in result.metrics:
            if metric.module == "vaccines" and metric.value != "0":
                entries.append((metric.title, metric.value, "vaccines"))
        entries = [e for e in entries if e[2] and permission_service.can_access_module(e[2])]
        self.menu.clear()
        self.menu.addAction("Resumen de avisos · abra el módulo para ver todos").setEnabled(False)
        for title, detail, module in entries:
            action = self.menu.addAction(f"{title} — {detail}".replace('&', '&&'))
            action.triggered.connect(lambda checked=False, key=module: self.window.navigate_to(key))
        if not entries:
            self.menu.addAction("Sin avisos pendientes").setEnabled(False)
        self.menu.addSeparator()
        self.menu.addAction("Actualizar ahora", self.poll)
        self.window.topbar.notifications_button.setToolTip(f"{len(entries)} avisos · revisión automática activa")
        self.window.topbar.notifications_button.set_count(len(entries))
        current = set(entries)
        new = current - self.seen
        prefs = QSettings("VetCare", "VetCare")
        enabled = prefs.value(f"notifications/{self.user.id}/desktop", True, type=bool)
        if new and enabled and self.tray.isVisible():
            self.tray.showMessage("VetCare", f"Hay {len(new)} avisos nuevos. Consulte la campana.", QSystemTrayIcon.Information, 5000)
        self.seen = current

    def open_result(self, item):
        target = item.data(Qt.UserRole)
        if not target or not self.active or not self.search_enabled:
            return
        module, record_id = target
        if not permission_service.has_permission(global_search_service.REQUIRED[module]):
            return
        self.completer.popup().hide()
        self.window.navigate_to(module)
        page = self.window.stack.widget(self.window._page_index[module])
        if hasattr(page, "_pet_filter_id"):
            page._pet_filter_id = None
        page.search_input.clear()
        for name in ("status_filter", "species_filter"):
            if hasattr(page, name):
                getattr(page, name).setCurrentIndex(0)
        if hasattr(page, "all_dates_check"):
            page.all_dates_check.setChecked(True)
        page.refresh()
        model = page.table.model()
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            if index.data(Qt.UserRole) == record_id:
                page.table.selectRow(row)
                page.table.scrollTo(index)
                return
        self.window.statusBar().showMessage("El registro ya no está disponible. Actualice la búsqueda.", 6000)
