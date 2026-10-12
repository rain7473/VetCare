"""Página de inventario: productos, stock, alertas, entradas y ajustes."""

from __future__ import annotations

from utils.icons import set_button_icon

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from config.constants import Colors
from database.connection import DatabaseConnectionError
from models.inventory import Product
from services import inventory_service, permission_service
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError
from views.inventory.inventory_dialogs import (
    ProductDialog,
    StockAdjustDialog,
    StockEntryDialog,
    SuppliersDialog,
)
from widgets.barcode_scanner import BarcodeScannerInput

_COLUMNS = [
    "Producto",
    "Categoría",
    "SKU",
    "Stock",
    "Mínimo",
    "Precio",
    "Ubicación",
    "Estado",
]


class InventoryPage(QWidget):
    """Listado de productos con alertas de stock bajo y vencimientos."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageArea")
        self._products: list[Product] = []
        self._loaded = False
        self._can_manage = permission_service.has_permission("INVENTORY_MANAGE")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Inventario")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar producto, SKU o ubicación...")
        self.search_input.setFixedWidth(220)
        self.search_input.textChanged.connect(self._apply_filters)
        header.addWidget(self.search_input)

        self.scanner_input = BarcodeScannerInput()
        self.scanner_input.setFixedWidth(200)
        self.scanner_input.scanned.connect(self._on_barcode_scanned)
        header.addWidget(self.scanner_input)

        suppliers = QPushButton("Proveedores", self)
        set_button_icon(suppliers, "supplier", color="#008FA3")
        suppliers.setProperty("variant", "secondary")
        suppliers.clicked.connect(self._on_suppliers)
        header.addWidget(suppliers)
        suppliers.setVisible(self._can_manage)

        entry = QPushButton("Entrada", self)
        set_button_icon(entry, "add", color="#008FA3")
        entry.setProperty("variant", "secondary")
        entry.clicked.connect(self._on_entry)
        header.addWidget(entry)
        entry.setVisible(self._can_manage)

        new_btn = QPushButton("Producto", self)
        set_button_icon(new_btn, "add")
        new_btn.clicked.connect(self._on_new)
        header.addWidget(new_btn)
        new_btn.setVisible(self._can_manage)
        layout.addLayout(header)

        self.alert_label = QLabel("")
        self.alert_label.setObjectName("errorLabel")
        self.alert_label.setWordWrap(True)
        self.alert_label.setVisible(False)
        layout.addWidget(self.alert_label)

        self.model = QStandardItemModel(0, len(_COLUMNS))
        self.model.setHorizontalHeaderLabels(_COLUMNS)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        if self._can_manage:
            self.table.doubleClicked.connect(lambda _: self._on_edit())
        layout.addWidget(self.table, stretch=1)

        actions = QHBoxLayout()
        actions.addStretch()

        self.edit_button = QPushButton("Editar", self)
        set_button_icon(self.edit_button, "edit", color="#008FA3")
        self.edit_button.setProperty("variant", "secondary")
        self.edit_button.clicked.connect(self._on_edit)
        actions.addWidget(self.edit_button)
        self.edit_button.setVisible(self._can_manage)

        self.adjust_button = QPushButton("Ajustar stock", self)
        set_button_icon(self.adjust_button, "stock", color="#008FA3")
        self.adjust_button.setProperty("variant", "secondary")
        self.adjust_button.clicked.connect(self._on_adjust)
        actions.addWidget(self.adjust_button)
        self.adjust_button.setVisible(self._can_manage)

        self.lots_button = QPushButton("Ver lotes")
        set_button_icon(self.lots_button, "inventory", color="#008FA3")
        self.lots_button.setProperty("variant", "secondary")
        self.lots_button.clicked.connect(self._on_lots)
        actions.addWidget(self.lots_button)

        layout.addLayout(actions)

        note = QLabel(
            "El stock se calcula por lotes; las ventas descuentan inventario con FIFO."
        )
        note.setObjectName("versionLabel")
        layout.addWidget(note)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loaded:
            self.refresh()

    def refresh(self) -> None:
        try:
            self._products = inventory_service.list_products()
            low = inventory_service.list_low_stock()
            expiring = inventory_service.list_expiring(30)
            self._loaded = True
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Inventario", str(exc))
            return

        parts: list[str] = []
        if low:
            names = ", ".join(p.name for p in low[:5])
            extra = "" if len(low) <= 5 else f" y {len(low) - 5} más"
            parts.append(f"Stock bajo: {names}{extra}")
        if expiring:
            names = ", ".join(
                f"{l.product_name} ({l.lot_number or 'sin lote'})"
                for l in expiring[:5]
            )
            extra = "" if len(expiring) <= 5 else f" y {len(expiring) - 5} más"
            parts.append(f"Próximos a vencer (30 días): {names}{extra}")
        if parts:
            self.alert_label.setText(" · ".join(parts))
            self.alert_label.setVisible(True)
        else:
            self.alert_label.setVisible(False)
        self._apply_filters()

    def _apply_filters(self) -> None:
        text = self.search_input.text().strip().lower()
        self.model.setRowCount(0)
        self.table.setSortingEnabled(False)
        for product in self._products:
            haystack = (
                f"{product.name} {product.sku or ''} {product.barcode or ''} "
                f"{product.category_name or ''} {product.location or ''}"
            ).lower()
            if text and text not in haystack:
                continue
            row = [
                QStandardItem(product.name),
                QStandardItem(product.category_name or "—"),
                QStandardItem(product.sku or "—"),
                QStandardItem(f"{product.stock_available:g}"),
                QStandardItem(f"{product.minimum_stock:g}"),
                QStandardItem(f"${product.sale_price:.2f}"),
                QStandardItem(product.location or "—"),
                QStandardItem("Activo" if product.is_active else "Inactivo"),
            ]
            for item in row:
                item.setData(product.id, Qt.UserRole)
            if product.is_low_stock and product.is_active:
                row[3].setForeground(QColor(Colors.ERROR))
            if not product.is_active:
                for item in row:
                    item.setForeground(QColor(Colors.MUTED))
            self.model.appendRow(row)
        self.table.setSortingEnabled(True)

    def _selected_product(self) -> Product | None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return None
        product_id = self.model.item(indexes[0].row(), 0).data(Qt.UserRole)
        for product in self._products:
            if product.id == product_id:
                return product
        return None

    def _on_barcode_scanned(self, code: str) -> None:
        try:
            product = inventory_service.find_by_barcode(code)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Código de barras", str(exc))
            return
        if product is None:
            QMessageBox.information(
                self,
                "Código de barras",
                f"No hay un producto activo con el código «{code}».",
            )
            return
        self.search_input.setText(product.sku or product.name)
        self._select_product_id(product.id)
        QMessageBox.information(
            self,
            "Producto encontrado",
            (
                f"{product.name}\n"
                f"SKU: {product.sku or '—'}\n"
                f"Stock: {product.stock_available:g} {product.unit}\n"
                f"Precio: ${product.sale_price:.2f}\n\n"
                "En el módulo de Ventas (Obj. 21) el escaneo podrá "
                "agregar el producto al carrito."
            ),
        )

    def _select_product_id(self, product_id: int) -> None:
        self._apply_filters()
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            if item is not None and item.data(Qt.UserRole) == product_id:
                self.table.selectRow(row)
                self.table.scrollTo(
                    self.model.index(row, 0), QTableView.PositionAtCenter
                )
                return

    def _on_new(self) -> None:
        if ProductDialog(parent=self).exec():
            self.refresh()

    def _on_edit(self) -> None:
        product = self._selected_product()
        if product is None:
            QMessageBox.information(self, "Inventario", "Seleccione un producto.")
            return
        if ProductDialog(product, parent=self).exec():
            self.refresh()

    def _on_entry(self) -> None:
        product = self._selected_product()
        if StockEntryDialog(product, parent=self).exec():
            self.refresh()

    def _on_adjust(self) -> None:
        product = self._selected_product()
        if product is None:
            QMessageBox.information(self, "Inventario", "Seleccione un producto.")
            return
        if StockAdjustDialog(product, parent=self).exec():
            self.refresh()

    def _on_suppliers(self) -> None:
        SuppliersDialog(parent=self).exec()

    def _on_lots(self) -> None:
        product = self._selected_product()
        if product is None:
            QMessageBox.information(self, "Inventario", "Seleccione un producto.")
            return
        try:
            lots = inventory_service.list_lots(product.id)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Inventario", str(exc))
            return
        if not lots:
            QMessageBox.information(
                self, "Lotes", f"«{product.name}» no tiene lotes registrados."
            )
            return
        lines = []
        for lot in lots:
            exp = (
                lot.expiry_date.strftime("%d/%m/%Y")
                if lot.expiry_date
                else "sin vencimiento"
            )
            lines.append(
                f"• {lot.lot_number or 'Sin nº'} — disp. {lot.quantity_available:g} "
                f"/ recibido {lot.quantity_received:g} — {exp}"
            )
        QMessageBox.information(
            self, f"Lotes — {product.name}", "\n".join(lines)
        )
