"""Ficha de consulta para los productos del inventario."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from models.inventory import Product
from utils.barcodes import barcode_symbol
from utils.icons import icon_label
from utils.validators import ValidationError
from widgets.managed_dialog import ManagedDialog


def _label(text: str, name: str, *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(wrap)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


class BarcodePreview(QWidget):
    """Dibuja el mismo simbolo que se utiliza en la etiqueta del producto."""

    def __init__(self, modules: str, parent=None) -> None:
        super().__init__(parent)
        self._modules = modules
        self.setFixedHeight(58)
        self.setAccessibleName("Vista previa del codigo de barras")

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.white)
        # Conserva una zona blanca a cada lado del simbolo.
        module_width = min(2.0, self.width() / (len(self._modules) + 24))
        left = (self.width() - len(self._modules) * module_width) / 2
        for index, bit in enumerate(self._modules):
            if bit == "1":
                painter.fillRect(QRectF(left + index * module_width, 2, module_width, 54), QColor(Qt.black))
        painter.end()


class ProductDetailDialog(ManagedDialog):
    """Presenta la información del producto sin modificarla."""

    def __init__(self, product: Product, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Detalle del producto")
        self.setMinimumSize(480, 440)
        self.resize(560, 690)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(14)
        symbol = QFrame()
        symbol.setObjectName("productDetailIcon")
        symbol_layout = QHBoxLayout(symbol)
        symbol_layout.setContentsMargins(14, 14, 14, 14)
        symbol_layout.addWidget(icon_label("products", 24))
        header.addWidget(symbol, 0, Qt.AlignTop)
        heading = QVBoxLayout()
        heading.setSpacing(4)
        heading.addWidget(_label("INVENTARIO / PRODUCTO", "productDetailEyebrow"))
        heading.addWidget(_label(product.name, "productDetailTitle", wrap=True))
        heading.addWidget(_label(product.category_name or "Sin categoría", "productDetailMuted", wrap=True))
        header.addLayout(heading, 1)
        status = _label("Activo" if product.is_active else "Inactivo", "productDetailStatus")
        status.setProperty("active", product.is_active)
        header.addWidget(status, 0, Qt.AlignTop)
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setObjectName("productDetailScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setObjectName("productDetailContent")
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(16)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        for title, value, hint in (
            ("PRECIO DE VENTA", f"${product.sale_price:.2f}", "Por unidad"),
            ("STOCK DISPONIBLE", f"{product.stock_available:g} {product.unit}",
             "Stock bajo" if product.is_active and product.is_low_stock else f"Mínimo: {product.minimum_stock:g} {product.unit}"),
        ):
            card = QFrame()
            card.setObjectName("productDetailMetric")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 14)
            card_layout.setSpacing(5)
            card_layout.addWidget(_label(title, "productDetailEyebrow"))
            card_layout.addWidget(_label(value, "productDetailMetricValue", wrap=True))
            hint_label = _label(hint, "productDetailMuted", wrap=True)
            if hint == "Stock bajo":
                hint_label.setObjectName("productDetailWarning")
            card_layout.addWidget(hint_label)
            metrics.addWidget(card, 1)
        body.addLayout(metrics)

        body.addWidget(_label("Información del producto", "productDetailSection"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(15)
        for index, (title, value) in enumerate((
            ("SKU", product.sku or "—"),
            ("Ubicación", product.location or "—"),
            ("Unidad", product.unit or "—"),
        )):
            column, row = index % 2, (index // 2) * 2
            grid.addWidget(_label(title, "productDetailMuted"), row, column)
            grid.addWidget(_label(value, "productDetailValue", wrap=True), row + 1, column)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        body.addLayout(grid)
        body.addWidget(_label("Código de barras", "productDetailSection"))
        barcode_card = QFrame()
        barcode_card.setObjectName("productDetailBarcode")
        barcode_layout = QVBoxLayout(barcode_card)
        barcode_layout.setContentsMargins(14, 10, 14, 10)
        barcode_layout.setSpacing(5)
        if product.barcode:
            try:
                modules = barcode_symbol(product.barcode).build()[0]
            except (ValidationError, ValueError):
                modules = None
            if modules:
                barcode_layout.addWidget(BarcodePreview(modules))
            else:
                barcode_layout.addWidget(_label("No se puede mostrar este código", "productDetailMuted", wrap=True))
        code_label = _label(product.barcode or "Sin código", "productDetailValue", wrap=True)
        code_label.setAlignment(Qt.AlignCenter)
        barcode_layout.addWidget(code_label)
        body.addWidget(barcode_card)
        body.addWidget(_label("Descripción", "productDetailSection"))
        body.addWidget(_label(product.description or "Sin descripción", "productDetailDescription", wrap=True))
        body.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        close = QPushButton("Cerrar")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        layout.addLayout(footer)
