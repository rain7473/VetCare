"""Gráficos reutilizables: PyQtGraph/PySide6 y dona nativa sin OpenGL."""

import os
import math

os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolTip, QVBoxLayout, QWidget
import pyqtgraph as pg

from config.constants import Colors
from models.dashboard import DashboardSeries
from utils.icons import icon_label

CHART_COLORS = (Colors.PRIMARY, Colors.MINT, Colors.INFO, Colors.WARNING, "#887AC7", "#E78390")


class ChartCard(QFrame):
    def __init__(self, title, icon_name, subtitle, parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.layout_box = QVBoxLayout(self)
        self.layout_box.setContentsMargins(18, 16, 18, 14)
        row = QHBoxLayout()
        row.addWidget(icon_label(icon_name))
        label = QLabel(title)
        label.setObjectName("cardTitle")
        label.setWordWrap(True)
        row.addWidget(label, 1)
        self.layout_box.addLayout(row)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setWordWrap(True)
        self.subtitle.setObjectName("dashboardCaption")
        self.layout_box.addWidget(self.subtitle)


class _MoneyAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [f"${v:,.0f}" if spacing >= 1 else f"${v:,.2f}" for v in values]


class SeriesChart(ChartCard):
    def __init__(self, title, icon_name, *, line=False, monthly=False, parent=None):
        super().__init__(title, icon_name, "Esperando datos de Oracle…", parent)
        self._line = line
        self._monthly = monthly
        self.series = DashboardSeries()
        axes = {"left": _MoneyAxis(orientation="left")} if line else {}
        self.plot = pg.PlotWidget(background=Colors.CARD, axisItems=axes)
        self.plot.setMinimumWidth(0)
        self.plot.setFixedHeight(190)
        self.plot.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.plot.setMenuEnabled(False)
        self.plot.setAntialiasing(True)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.showGrid(x=False, y=True, alpha=0.12)
        for name in ("bottom", "left"):
            axis = self.plot.getAxis(name)
            axis.setPen(pg.mkPen("#DCE8EE"))
            axis.setTextPen(pg.mkPen(Colors.MUTED))
            font = self.font()
            font.setPixelSize(10)
            axis.setStyle(tickFont=font)
            axis.enableAutoSIPrefix(False)
        if not line:
            self.plot.getAxis("left").setLabel("Cantidad", color=Colors.MUTED)
        self.plot.scene().sigMouseMoved.connect(self._hover)
        self.layout_box.addWidget(self.plot)
        self.empty = QLabel("Sin registros en el intervalo mostrado.\nPuede seleccionar otro período para consultar el histórico.")
        self.empty.setObjectName("dashboardEmptyChart")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setFixedHeight(190)
        self.layout_box.addWidget(self.empty)
        self.empty.hide()
        self.legend = QLabel("Gris: histórico · Turquesa: período seleccionado" if monthly else "Citas dentro del período seleccionado")
        self.legend.setObjectName("dashboardCaption")
        self.legend.setWordWrap(True)
        self.layout_box.addWidget(self.legend)
        self.compare = QCheckBox("Comparar con los mismos meses del año anterior", self)
        self.compare.setChecked(True)
        self.compare.toggled.connect(self._draw)
        self.layout_box.addWidget(self.compare)
        self.compare.setVisible(line)

    def set_series(self, series, description):
        self.series = series
        self.subtitle.setText(description)
        self._draw()

    def _draw(self):
        data = self.series
        self.plot.clear()
        x = list(range(len(data.labels)))
        populated = any(data.values) or (self.compare.isChecked() and any(data.previous))
        self.plot.setVisible(populated)
        self.empty.setVisible(not populated)
        if not populated:
            return
        # En rangos extensos solo se espacian etiquetas, nunca se descartan datos.
        step = max(1, math.ceil(len(x) / 8))
        self.plot.getAxis("bottom").setTicks([[(i, label) for i, label in enumerate(data.labels) if i % step == 0]])
        if self._line:
            self.plot.plot(x, data.values, pen=pg.mkPen("#A0B7C2", width=2), symbol="o", symbolSize=5, symbolBrush="#A0B7C2")
            self.plot.plot(x, data.selected, pen=pg.mkPen(Colors.PRIMARY, width=3), symbol="o", symbolSize=8, symbolBrush=Colors.PRIMARY, symbolPen="w")
            if self.compare.isChecked() and data.previous:
                self.plot.plot(x, data.previous, pen=pg.mkPen(Colors.MINT, width=2, style=Qt.DashLine), symbol="s", symbolSize=5, symbolBrush=Colors.MINT)
            self.legend.setText("Gris: histórico · Turquesa: selección (USD)" + (" · Mint: año anterior" if self.compare.isChecked() else ""))
        elif self._monthly:
            self.plot.addItem(pg.BarGraphItem(x=x, height=data.values, width=0.65, brush="#D6E5EB", pen=None))
            self.plot.addItem(pg.BarGraphItem(x=x, height=data.selected, width=0.42, brush=Colors.PRIMARY, pen=None))
        else:
            self.plot.addItem(pg.BarGraphItem(x=x, height=data.values, width=0.55, brushes=[CHART_COLORS[i % len(CHART_COLORS)] for i in x], pen=None))
        maximum = max((*data.values, *data.selected, *(data.previous if self.compare.isChecked() else ()), 1))
        if not self._line:
            step = max(1, math.ceil(maximum / 4))
            self.plot.getAxis("left").setTicks([[(v, str(v)) for v in range(0, math.ceil(maximum) + 1, step)]])
        self.plot.setYRange(0, maximum * 1.2, padding=0)
        self.plot.setXRange(-0.6, max(len(x)-0.4, 0.6), padding=0)

    def tooltip_at(self, index):
        d = self.series
        if not 0 <= index < len(d.labels):
            return ""
        fmt = (lambda v: f"${v:,.2f}") if self._line else (lambda v: f"{v:,.0f}")
        text = f"{d.labels[index]} · {fmt(d.values[index])}"
        if d.selected:
            text += f"\nDentro de la selección: {fmt(d.selected[index])}"
        if d.previous and self.compare.isChecked():
            text += f"\nMismo mes, año anterior: {fmt(d.previous[index])}"
        return text

    def _hover(self, point):
        if self.plot.sceneBoundingRect().contains(point):
            index = round(self.plot.plotItem.vb.mapSceneToView(point).x())
            tip = self.tooltip_at(index)
            if tip:
                QToolTip.showText(QCursor.pos(), tip, self)


class _Donut(QWidget):
    def __init__(self):
        super().__init__()
        self.series = DashboardSeries()
        self.setMinimumSize(170, 190)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height()) - 38
        rect = QRectF((self.width()-side)/2, (self.height()-side)/2, side, side)
        total = sum(self.series.values)
        painter.setPen(QPen(QColor("#E7F1F4"), 23))
        painter.drawEllipse(rect)
        start = 90.0
        for i, value in enumerate(self.series.values):
            angle = 360 * value / total if total else 0
            painter.setPen(QPen(QColor(CHART_COLORS[i % len(CHART_COLORS)]), 23))
            painter.drawArc(rect, round(start*16), -round(angle*16))
            start -= angle
        painter.setPen(QColor(Colors.TEXT_DARK))
        font = self.font()
        font.setPixelSize(28)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect.adjusted(0, -8, 0, -8), Qt.AlignCenter, f"{total:,.0f}")
        font.setPixelSize(11)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(Colors.MUTED))
        painter.drawText(rect.adjusted(0, 45, 0, 0), Qt.AlignCenter, "mascotas activas")

    def mouseMoveEvent(self, event):
        total = sum(self.series.values)
        if not total:
            return
        angle = (math.degrees(math.atan2(event.position().y()-self.height()/2, event.position().x()-self.width()/2)) + 90) % 360
        cumulative = 0
        for label, value in zip(self.series.labels, self.series.values):
            cumulative += value / total * 360
            if angle <= cumulative:
                QToolTip.showText(event.globalPosition().toPoint(), f"{label}: {value:g} ({value/total:.1%})", self)
                break


class SpeciesChart(ChartCard):
    def __init__(self, parent=None):
        super().__init__("Distribución de mascotas", "pets", "Mascotas activas por especie · estado actual", parent)
        self.donut = _Donut()
        self.layout_box.addWidget(self.donut)
        self.legend = QLabel()
        self.legend.setObjectName("dashboardCaption")
        self.legend.setWordWrap(True)
        self.legend.setTextFormat(Qt.PlainText)
        self.layout_box.addWidget(self.legend)

    def set_series(self, series):
        self.donut.series = series
        total = sum(series.values)
        self.legend.setText("  ·  ".join(f"{label}: {value:g} ({value/total:.0%})" for label, value in zip(series.labels, series.values)) if total else "Sin mascotas activas registradas.")
        self.donut.update()
