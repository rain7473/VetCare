"""Dashboard adaptable, actualizado fuera del hilo gráfico."""

import logging
from datetime import datetime

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot, QDate
from PySide6.QtWidgets import QComboBox, QDateEdit, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from config.constants import ROLE_DISPLAY_NAMES
from models.dashboard import DashboardSeries
from services import dashboard_service, permission_service, session
from utils.icons import icon_label, set_button_icon
from widgets.dashboard_charts import SeriesChart, SpeciesChart
from widgets.stat_card import StatCard

logger = logging.getLogger(__name__)

QUICK_ACTIONS = {
    "pets": ("Nueva mascota", "PETS_WRITE"),
    "appointments": ("Programar cita", "APPOINTMENTS_MANAGE"),
    "consultations": ("Nueva consulta", "CONSULTATIONS_WRITE"),
    "triage": ("Iniciar triaje", "TRIAGE_CREATE"),
}


class _WorkerSignals(QObject):
    finished = Signal(int, object, bool)


class _DashboardWorker(QRunnable):
    def __init__(self, loader, user, period, revision):
        super().__init__()
        self.signals = _WorkerSignals()
        self.loader, self.user, self.period, self.revision = loader, user, period, revision

    def run(self):
        try:
            result = self.loader(self.user, period=self.period)
        except Exception:
            logger.exception("No fue posible cargar el dashboard")
            self.signals.finished.emit(self.revision, None, True)
        else:
            self.signals.finished.emit(self.revision, result, False)


class _DashboardPanel(QFrame):
    navigated = Signal(str)

    def __init__(self, title, empty_text, icon_name, parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._empty_text = empty_text
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        row = QHBoxLayout()
        row.addWidget(icon_label(icon_name))
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        title_label.setWordWrap(True)
        row.addWidget(title_label, 1)
        layout.addLayout(row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("dashboardPanelScroll")
        scroll.setMinimumHeight(200)
        body = QWidget()
        body.setObjectName("dashboardPanelBody")
        self.content = QVBoxLayout(body)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setAlignment(Qt.AlignTop)
        self.content.setSpacing(8)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self.setMinimumHeight(300)
        self.setMaximumHeight(340)
        self.link = QPushButton("Ver auditoría")
        self.link.setProperty("variant", "secondary")
        self.link.hide()
        self.link.clicked.connect(lambda: self.navigated.emit("audit"))
        layout.addWidget(self.link)

    def set_items(self, items):
        while self.content.count():
            child = self.content.takeAt(0).widget()
            child.deleteLater()
        if not items:
            label = QLabel(self._empty_text)
            label.setObjectName("dashboardEmpty")
            label.setWordWrap(True)
            self.content.addWidget(label)
        for item in items:
            frame = QFrame()
            frame.setObjectName("dashboardEvent")
            frame.setProperty("severity", (item.severity or "low").lower())
            box = QVBoxLayout(frame)
            box.setContentsMargins(10, 8, 10, 8)
            title = QLabel(item.title)
            title.setTextFormat(Qt.PlainText)
            title.setWordWrap(True)
            title.setObjectName("dashboardEventTitle")
            box.addWidget(title)
            detail = QLabel(item.detail)
            detail.setTextFormat(Qt.PlainText)
            detail.setWordWrap(True)
            detail.setObjectName("dashboardCaption")
            box.addWidget(detail)
            if item.occurred_at:
                stamp = QLabel(item.occurred_at.strftime("%d/%m/%Y · %H:%M"))
                stamp.setObjectName("dashboardCaption")
                box.addWidget(stamp)
            if item.module and item.module != "audit" and permission_service.can_access_module(item.module):
                button = QPushButton("Abrir módulo")
                button.setObjectName("dashboardLink")
                button.clicked.connect(lambda checked=False, module=item.module: self.navigated.emit(module))
                box.addWidget(button, alignment=Qt.AlignLeft)
            self.content.addWidget(frame)


class DashboardPage(QWidget):
    navigated = Signal(str)
    create_requested = Signal(str)
    loaded = Signal()

    def __init__(self, user, loader=None, *, autoload=True):
        super().__init__()
        self.setObjectName("pageArea")
        self._user = user
        self._loader = loader or dashboard_service.load_dashboard
        self._busy = False
        self._pending = False
        self._active = True
        self._revision = 0
        self._snapshot = None
        self.cards = {}
        self._arranged = {}
        self._build_ui()
        if autoload:
            QTimer.singleShot(0, self.refresh)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        content = QWidget()
        content.setObjectName("pageArea")
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)
        header = QHBoxLayout()
        greeting = QVBoxLayout()
        name = self._user.full_name.split()
        title = QLabel(f"Hola, {name[0] if name else ''}")
        title.setTextFormat(Qt.PlainText)
        title.setObjectName("pageTitle")
        title.setWordWrap(True)
        greeting.addWidget(title)
        self.subtitle = QLabel(ROLE_DISPLAY_NAMES.get(self._user.role_name, ""))
        self.subtitle.setObjectName("dashboardCaption")
        self.subtitle.setWordWrap(True)
        greeting.addWidget(self.subtitle)
        header.addLayout(greeting, 1)
        self.period_combo = QComboBox()
        self.period_combo.setAccessibleName("Período del dashboard")
        for label, key in (("Hoy", "today"), ("Últimos 7 días", "7d"), ("Últimos 30 días", "30d"), ("Este mes", "month"), ("Rango personalizado", "custom")):
            self.period_combo.addItem(label, key)
        self.period_combo.setCurrentIndex(3)
        self.period_combo.currentIndexChanged.connect(self._filter_changed)
        header.addWidget(self.period_combo)
        self.refresh_button = QPushButton("Actualizar")
        set_button_icon(self.refresh_button, "refresh", size=14)
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)
        self.custom_range = QWidget()
        row = QHBoxLayout(self.custom_range)
        row.setContentsMargins(0, 0, 0, 0)
        today = QDate.currentDate()
        self.start_date, self.end_date = QDateEdit(today.addDays(-29)), QDateEdit(today)
        for caption, picker in (("Desde", self.start_date), ("Hasta", self.end_date)):
            picker.setCalendarPopup(True)
            picker.setDisplayFormat("dd/MM/yyyy")
            picker.setDateRange(QDate(2000, 1, 1), today)
            row.addWidget(QLabel(caption))
            row.addWidget(picker)
            picker.dateChanged.connect(self._schedule_filter)
        row.addStretch()
        self.custom_range.hide()
        layout.addWidget(self.custom_range)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(250)
        self._filter_timer.timeout.connect(self.refresh)
        self.period_label = QLabel("Cargando información de Oracle…")
        self.period_label.setObjectName("dashboardCaption")
        self.period_label.setWordWrap(True)
        layout.addWidget(self.period_label)
        self.error_label = QLabel()
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        self.card_grid = QGridLayout()
        self.card_grid.setSpacing(12)
        layout.addLayout(self.card_grid)
        self.quick_grid = QGridLayout()
        self.quick_buttons = []
        for module, (caption, permission) in QUICK_ACTIONS.items():
            if permission_service.has_permission(permission):
                button = QPushButton(caption)
                button.setProperty("variant", "secondary")
                set_button_icon(button, module, size=16, color="#008FA3")
                button.clicked.connect(lambda checked=False, key=module: self.create_requested.emit(key))
                self.quick_buttons.append(button)
        layout.addLayout(self.quick_grid)
        self.chart_grid = QGridLayout()
        self.chart_grid.setSpacing(14)
        self.consultations_chart = SeriesChart("Consultas mensuales", "consultations", monthly=True, parent=content)
        self.revenue_chart = SeriesChart("Ingresos por ventas", "sales", line=True, monthly=True, parent=content)
        self.species_chart = SpeciesChart(parent=content)
        self.states_chart = SeriesChart("Estados de citas", "appointments", parent=content)
        self.charts = [self.consultations_chart, self.revenue_chart, self.species_chart, self.states_chart]
        for chart in self.charts:
            chart.hide()
            self.chart_grid.addWidget(chart)
        layout.addLayout(self.chart_grid)
        self.panel_grid = QGridLayout()
        self.panel_grid.setSpacing(14)
        self.week_panel = _DashboardPanel("Próximas citas · 7 días", "No hay próximas citas programadas.", "appointments", parent=content)
        self.alerts_panel = _DashboardPanel("Alertas y triaje", "Sin alertas pendientes de atención.", "warning", parent=content)
        self.activity_panel = _DashboardPanel("Actividad reciente", "Sin movimientos en este período.", "history", parent=content)
        self.panels = [self.week_panel, self.alerts_panel, self.activity_panel]
        for panel in self.panels:
            panel.navigated.connect(self.navigated.emit)
            panel.hide()
            self.panel_grid.addWidget(panel)
        layout.addLayout(self.panel_grid)
        layout.addStretch()

    def _schedule_filter(self):
        self._revision += 1  # invalida resultados incluso durante el debounce
        self._filter_timer.start()

    def _filter_changed(self):
        self.custom_range.setVisible(self.period_combo.currentData() == "custom")
        self._schedule_filter()

    def refresh(self):
        if not self._active:
            return
        self._revision += 1
        try:
            period = dashboard_service.resolve_period(self.period_combo.currentData(), start=self.start_date.date().toPython(), end=self.end_date.date().toPython())
        except ValueError as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            self._pending = False
            return
        self.error_label.hide()
        if self._busy:
            self._pending = True
            return
        self._busy = True
        self._pending = False
        self.refresh_button.setEnabled(False)
        self._worker = _DashboardWorker(self._loader, self._user, period, self._revision)
        self._worker.signals.finished.connect(self._finished, Qt.QueuedConnection)
        QThreadPool.globalInstance().start(self._worker)

    @Slot(int, object, bool)
    def _finished(self, revision, snapshot, failed):
        self._busy = False
        self._worker = None
        self.refresh_button.setEnabled(True)
        if not self._active or session.get_current_user() != self._user:
            return
        if revision == self._revision:
            if failed:
                self.error_label.setText("No se pudo actualizar. Se conservan los últimos datos cargados; pulse Actualizar para reintentar.")
                self.error_label.show()
                if self._snapshot is None:
                    self.period_label.setText("Sin datos cargados. Verifique la conexión y vuelva a intentarlo.")
            else:
                # _render replaces cards and rebuilds panel contents. Keep Qt
                # from painting the intermediate empty/reflowed layouts, which
                # otherwise appear as a brief flash when opening the dashboard.
                content = self.scroll.widget()
                content.setUpdatesEnabled(False)
                try:
                    self._render(snapshot)
                finally:
                    content.setUpdatesEnabled(True)
                    content.update()
                self.loaded.emit()
        if self._pending:
            self.refresh()

    def deactivate(self):
        """Ignora cargas pendientes al cerrar la ventana o cerrar sesión."""
        self._active = False
        self._pending = False
        self._filter_timer.stop()
        self._revision += 1

    def _render(self, snapshot):
        self._snapshot = snapshot
        old_cards = self.cards
        self.cards = {}
        for metric in snapshot.metrics:
            clickable = bool(metric.module) and permission_service.can_access_module(metric.module)
            card = old_cards.pop(metric.key, None)
            if card is not None and (card._clickable != clickable or card.property("metricModule") != metric.module or card.property("metricIcon") != metric.icon):
                self.card_grid.removeWidget(card)
                card.hide()
                card.deleteLater()
                card = None
            if card is None:
                card = StatCard(metric.title, metric.value, metric.icon, metric.detail, clickable=clickable, parent=self.scroll.widget())
                card.setProperty("metricModule", metric.module)
                card.setProperty("metricIcon", metric.icon)
                if clickable:
                    card.setToolTip(f"Abrir {metric.module}")
                    card.clicked.connect(lambda key=metric.module: self.navigated.emit(key))
            else:
                card.title_label.setText(metric.title)
                card.set_value(metric.value)
                card.set_detail(metric.detail)
                card.setAccessibleName(f"{metric.title}: {metric.value}")
            self.cards[metric.key] = card
        for card in old_cards.values():
            self.card_grid.removeWidget(card)
            card.hide()
            card.deleteLater()
        stamp = snapshot.loaded_at or datetime.now()
        self.subtitle.setText(f"{ROLE_DISPLAY_NAMES.get(snapshot.role_name, snapshot.role_name)} · Actualizado {stamp:%d/%m/%Y %H:%M}")
        period = snapshot.period
        dates = f"{period.start:%d/%m/%Y} – {period.end:%d/%m/%Y}" if period else ""
        self.period_label.setText(f"Período: {dates} · Los indicadores de hoy y de estado actual conservan su alcance.")
        for chart, data in ((self.consultations_chart, snapshot.consultations), (self.revenue_chart, snapshot.revenue), (self.states_chart, snapshot.appointment_states)):
            chart.setVisible(data is not None)
            if data is not None:
                description = f"Selección: {dates}"
                if chart != self.states_chart:
                    description = f"{len(data.labels)} meses de contexto · selección: {dates}"
                chart.set_series(data, description)
        self.species_chart.setVisible(snapshot.species is not None)
        if snapshot.species is not None:
            self.species_chart.set_series(snapshot.species)
        self.week_panel.setVisible(snapshot.appointment_states is not None)
        self.alerts_panel.setVisible(bool(snapshot.alerts_and_triage) or any(m.module in {"hospitalization", "triage", "inventory"} for m in snapshot.metrics))
        self.activity_panel.show()
        self.activity_panel.link.setVisible(permission_service.can_access_module("audit"))
        self.week_panel.set_items(snapshot.weekly_appointments)
        self.alerts_panel.set_items(snapshot.alerts_and_triage)
        self.activity_panel.set_items(snapshot.recent_activity[:5])
        self._reflow()

    def _arrange(self, grid, widgets, columns):
        state = (tuple(widgets), columns)
        if self._arranged.get(grid) == state:
            return
        self._arranged[grid] = state
        while grid.count():
            grid.takeAt(0)
        for col in range(max(grid.columnCount(), columns)):
            grid.setColumnStretch(col, 1 if col < columns else 0)
        for i, widget in enumerate(widgets):
            grid.addWidget(widget, i // columns, i % columns)

    def _reflow(self):
        width = self.scroll.viewport().width() - 48
        kpi_cols = max(1, min(6, width // 230))
        self._arrange(self.card_grid, list(self.cards.values()), kpi_cols)
        self._arrange(self.quick_grid, self.quick_buttons, min(4, max(1, width // 225)))
        self._arrange(self.chart_grid, [c for c in self.charts if not c.isHidden()], 2 if width >= 760 else 1)
        self._arrange(self.panel_grid, [p for p in self.panels if not p.isHidden()], 3 if width >= 1020 else 2 if width >= 700 else 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()
