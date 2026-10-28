"""Página de ventas: punto de venta con escáner, carrito e historial."""

from __future__ import annotations

from decimal import Decimal

from utils.icons import set_button_icon

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database.connection import DatabaseConnectionError
from models.inventory import Product
from models.sale import PAYMENT_LABELS, STATUS_LABELS, Sale
from services import inventory_service, owner_service, sales_service
from services.permission_service import PermissionDeniedError, has_permission
from services.sales_service import CartLine, SaleFormData
from utils.validators import ValidationError
from views.inventory.inventory_dialogs import ProductDialog
from views.owners.owner_dialog import OwnerDialog
from views.sales.sale_detail_dialog import SaleDetailDialog
from widgets.barcode_scanner import BarcodeScannerInput
from widgets.dynamic_selector import DynamicEntitySelector, SelectorItem

_CART_COLS = ["Producto", "Cant.", "Precio", "Desc.", "Total", "Acción"]
_HIST_COLS = [
    "Factura", "Fecha", "Cliente", "Total", "Pago", "Estado", "Vendedor",
    "Detalle",
]


class SalesPage(QWidget):
    """POS simple: escanear/agregar → totales → confirmar → historial."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pageArea")
        self._can_create = has_permission("SALES_CREATE")
        self._cart: list[dict] = []  # product, qty, unit_price, discount
        self._products: list[Product] = []
        self._owners: list[tuple[int | None, str]] = [(None, "— Mostrador —")]
        self._sales: list[Sale] = []
        self._loaded = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Ventas")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        self.history_panel = self._build_history_panel()
        self.sale_dialog = QDialog(self)
        self.sale_dialog.setWindowTitle("Registrar venta")
        self.sale_dialog.setModal(True)
        self.sale_dialog.resize(980, 760)
        self.sale_dialog.setMinimumSize(760, 600)
        dialog_layout = QVBoxLayout(self.sale_dialog)
        dialog_layout.setContentsMargins(16, 16, 16, 16)
        self.pos_panel = self._build_pos_panel()
        dialog_layout.addWidget(self.pos_panel)

        layout.addWidget(self.history_panel, stretch=1)

    def _build_pos_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.addWidget(QLabel("Registrar venta"))
        head.addStretch()
        back = QPushButton("Cerrar")
        back.setProperty("variant", "secondary")
        back.clicked.connect(self.sale_dialog.accept)
        head.addWidget(back)
        layout.addLayout(head)

        scan_row = QHBoxLayout()
        self.scanner = BarcodeScannerInput()
        self.scanner.setPlaceholderText("Escanear producto…")
        self.scanner.scanned.connect(self._on_scan)
        self.scanner.setEnabled(self._can_create)
        scan_row.addWidget(self.scanner, stretch=1)

        self.product_selector = DynamicEntitySelector(
            placeholder="Buscar producto, SKU o código…",
            add_tooltip="Crear producto",
        )
        self.product_selector.setEnabled(self._can_create)
        self.product_selector.set_add_enabled(
            self._can_create and has_permission("INVENTORY_MANAGE"),
            "Crear producto" if has_permission("INVENTORY_MANAGE")
            else "Sin permiso para crear productos",
        )
        self.product_selector.add_requested.connect(self._create_product)
        scan_row.addWidget(self.product_selector, stretch=1)

        add_btn = QPushButton("Agregar")
        set_button_icon(add_btn, "add")
        add_btn.clicked.connect(self._on_add_selected)
        add_btn.setEnabled(self._can_create)
        scan_row.addWidget(add_btn)
        layout.addLayout(scan_row)

        self.cart_model = QStandardItemModel(0, len(_CART_COLS))
        self.cart_model.setHorizontalHeaderLabels(_CART_COLS)
        self.cart_table = QTableView()
        self.cart_table.setModel(self.cart_model)
        self.cart_table.setSelectionBehavior(QTableView.SelectRows)
        self.cart_table.setEditTriggers(QTableView.NoEditTriggers)
        self.cart_table.verticalHeader().setVisible(False)
        cart_header = self.cart_table.horizontalHeader()
        cart_header.setSectionResizeMode(QHeaderView.Stretch)
        cart_header.setSectionResizeMode(
            len(_CART_COLS) - 1, QHeaderView.ResizeToContents
        )
        layout.addWidget(self.cart_table, stretch=1)

        cart_actions = QHBoxLayout()
        clear = QPushButton("Vaciar")
        set_button_icon(clear, "delete", color="#008FA3")
        clear.setProperty("variant", "secondary")
        clear.clicked.connect(self._clear_cart)
        clear.setEnabled(self._can_create)
        cart_actions.addWidget(clear)
        cart_actions.addStretch()
        layout.addLayout(cart_actions)

        form = QFormLayout()
        self.owner_selector = DynamicEntitySelector(
            placeholder="Buscar cliente, identificación o teléfono…",
            add_tooltip="Crear propietario / cliente",
            allow_empty=True,
            empty_label="— Mostrador —",
        )
        self.owner_selector.setEnabled(self._can_create)
        self.owner_selector.set_add_enabled(
            self._can_create and has_permission("OWNERS_WRITE"),
            "Crear propietario" if has_permission("OWNERS_WRITE")
            else "Sin permiso para crear propietarios",
        )
        self.owner_selector.add_requested.connect(self._create_owner)
        form.addRow("Cliente", self.owner_selector)

        self.payment_combo = QComboBox()
        for code, label in PAYMENT_LABELS.items():
            self.payment_combo.addItem(label, code)
        self.payment_combo.setEnabled(self._can_create)
        form.addRow("Pago", self.payment_combo)

        self.discount_input = QDoubleSpinBox()
        self.discount_input.setRange(0, 1_000_000)
        self.discount_input.setDecimals(2)
        self.discount_input.setPrefix("$ ")
        self.discount_input.valueChanged.connect(self._refresh_totals)
        self.discount_input.setEnabled(self._can_create)
        form.addRow("Descuento", self.discount_input)

        self.tax_input = QDoubleSpinBox()
        self.tax_input.setRange(0, 1_000_000)
        self.tax_input.setDecimals(2)
        self.tax_input.setPrefix("$ ")
        self.tax_input.valueChanged.connect(self._refresh_totals)
        self.tax_input.setEnabled(self._can_create)
        form.addRow("Impuesto", self.tax_input)

        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(48)
        self.notes_input.setEnabled(self._can_create)
        form.addRow("Notas", self.notes_input)
        layout.addLayout(form)

        self.totals_label = QLabel("Subtotal: $0.00   Total: $0.00")
        self.totals_label.setObjectName("pageTitle")
        layout.addWidget(self.totals_label)

        confirm = QPushButton("Confirmar venta")
        set_button_icon(confirm, "sales")
        confirm.clicked.connect(self._on_confirm)
        confirm.setEnabled(self._can_create)
        layout.addWidget(confirm)

        if not self._can_create:
            hint = QLabel("Solo lectura: su rol puede consultar ventas, no crearlas.")
            hint.setObjectName("versionLabel")
            layout.addWidget(hint)

        return panel

    def _build_history_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)

        head = QHBoxLayout()
        head.addWidget(QLabel("Historial de ventas"))
        head.addStretch()
        if self._can_create:
            add_sale = QPushButton("Agregar venta")
            set_button_icon(add_sale, "add")
            add_sale.clicked.connect(self._show_pos)
            head.addWidget(add_sale)
        refresh = QPushButton("Actualizar")
        set_button_icon(refresh, "refresh", color="#008FA3")
        refresh.setProperty("variant", "secondary")
        refresh.clicked.connect(lambda _checked=False: self.refresh_history())
        head.addWidget(refresh)
        layout.addLayout(head)

        self.hist_model = QStandardItemModel(0, len(_HIST_COLS))
        self.hist_model.setHorizontalHeaderLabels(_HIST_COLS)
        self.hist_table = QTableView()
        self.hist_table.setModel(self.hist_model)
        self.hist_table.setSelectionBehavior(QTableView.SelectRows)
        self.hist_table.setEditTriggers(QTableView.NoEditTriggers)
        self.hist_table.verticalHeader().setVisible(False)
        history_header = self.hist_table.horizontalHeader()
        history_header.setSectionResizeMode(QHeaderView.Stretch)
        history_header.setSectionResizeMode(
            len(_HIST_COLS) - 1, QHeaderView.ResizeToContents
        )
        self.hist_table.doubleClicked.connect(lambda _: self._on_view_sale())
        layout.addWidget(self.hist_table, stretch=1)
        return panel

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loaded:
            self.refresh()

    def _show_pos(self) -> None:
        if self._can_create:
            self.sale_dialog.exec()

    def refresh(self) -> None:
        self.refresh_catalog()
        self.refresh_history()
        self._loaded = True

    def refresh_catalog(self) -> None:
        try:
            self._products = inventory_service.list_products(active_only=True)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Ventas", str(exc))
            return

        owners = []
        if has_permission("OWNERS_READ"):
            try:
                owners = [o for o in owner_service.list_owners() if o.is_active]
            except (PermissionDeniedError, DatabaseConnectionError):
                owners = []

        self.product_selector.set_items(
            [
                SelectorItem(
                    p.id,
                    f"{p.name} · stock {p.stock_available:g} · ${p.sale_price:.2f}",
                    " ".join(filter(None, [p.sku, p.barcode, p.location])),
                )
                for p in self._products
            ]
        )
        self._owners = [(None, "— Mostrador —")] + [(o.id, o.full_name) for o in owners]
        self.owner_selector.set_items(
            [
                SelectorItem(
                    o.id,
                    o.full_name,
                    " ".join(filter(None, [o.identification, o.phone, o.email])),
                )
                for o in owners
            ],
            selected_id=None,
        )

    def refresh_history(self, selected_id: int | None = None) -> None:
        if selected_id is None:
            rows = self.hist_table.selectionModel().selectedRows()
            if rows:
                selected_id = self.hist_model.item(rows[0].row(), 0).data(Qt.UserRole)
        try:
            self._sales = sales_service.list_sales()
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Ventas", str(exc))
            return
        detail_column = len(_HIST_COLS) - 1
        for row in range(self.hist_model.rowCount()):
            self.hist_table.setIndexWidget(
                self.hist_model.index(row, detail_column), None
            )
        self.hist_model.setRowCount(0)
        selected_row = None
        for index, sale in enumerate(self._sales):
            invoice_item = QStandardItem(sale.invoice_number)
            invoice_item.setData(sale.id, Qt.UserRole)
            self.hist_model.appendRow(
                [
                    invoice_item,
                    QStandardItem(sale.sold_at.strftime("%d/%m/%Y %H:%M")),
                    QStandardItem(sale.owner_name or "Mostrador"),
                    QStandardItem(f"${sale.total:.2f}"),
                    QStandardItem(PAYMENT_LABELS.get(sale.payment_method, sale.payment_method)),
                    QStandardItem(STATUS_LABELS.get(sale.status, sale.status)),
                    QStandardItem(sale.sold_by_name or "—"),
                    QStandardItem(),
                ]
            )
            detail_button = QPushButton("Ver")
            set_button_icon(detail_button, "view", color="#008FA3")
            detail_button.setProperty("variant", "secondary")
            detail_button.setStyleSheet("padding: 3px 8px; border-radius: 6px;")
            detail_button.setFixedHeight(30)
            detail_button.setToolTip("Ver detalle de la venta")
            detail_button.clicked.connect(
                lambda _checked=False, sale_id=sale.id: self._show_sale_detail(sale_id)
            )
            self.hist_table.setIndexWidget(
                self.hist_model.index(index, detail_column), detail_button
            )
            self.hist_table.setRowHeight(index, 36)
            if sale.id == selected_id:
                selected_row = index
        if selected_row is not None:
            self.hist_table.selectRow(selected_row)
            self.hist_table.scrollTo(self.hist_model.index(selected_row, 0))

    def _find_product(self, product_id: int) -> Product | None:
        for p in self._products:
            if p.id == product_id:
                return p
        return None

    def _on_scan(self, code: str) -> None:
        try:
            product = inventory_service.find_by_barcode(code)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Escáner", str(exc))
            return
        if product is None:
            QMessageBox.information(
                self, "Escáner", f"No se encontró el código «{code}»."
            )
            return
        self._add_product(product)

    def _on_add_selected(self) -> None:
        product_id = self.product_selector.current_id()
        product = self._find_product(product_id) if product_id else None
        if product is None:
            QMessageBox.information(self, "Ventas", "Seleccione un producto.")
            return
        self._add_product(product)

    def _add_product(self, product: Product) -> None:
        if product.stock_available <= 0:
            QMessageBox.warning(
                self, "Ventas", f"«{product.name}» no tiene stock disponible."
            )
            return
        for row in self._cart:
            if row["product"].id == product.id:
                new_qty = row["qty"] + Decimal("1")
                if new_qty > product.stock_available:
                    QMessageBox.warning(
                        self,
                        "Ventas",
                        f"Stock insuficiente de «{product.name}» "
                        f"(disponible {product.stock_available:g}).",
                    )
                    return
                row["qty"] = new_qty
                self._render_cart()
                return
        self._cart.append(
            {
                "product": product,
                "qty": Decimal("1"),
                "unit_price": product.sale_price,
                "discount": Decimal("0"),
            }
        )
        self._render_cart()

    def _remove_cart_line(self, row: int) -> None:
        if not 0 <= row < len(self._cart):
            return
        del self._cart[row]
        self._render_cart()

    def _clear_cart(self) -> None:
        self._cart.clear()
        self.discount_input.setValue(0)
        self.tax_input.setValue(0)
        self.notes_input.clear()
        self._render_cart()

    def _render_cart(self) -> None:
        action_column = len(_CART_COLS) - 1
        for row in range(self.cart_model.rowCount()):
            self.cart_table.setIndexWidget(
                self.cart_model.index(row, action_column), None
            )
        self.cart_model.setRowCount(0)
        for index, row in enumerate(self._cart):
            product: Product = row["product"]
            qty: Decimal = row["qty"]
            price: Decimal = row["unit_price"]
            disc: Decimal = row["discount"]
            total = qty * price - disc
            self.cart_model.appendRow(
                [
                    QStandardItem(product.name),
                    QStandardItem(f"{qty:g}"),
                    QStandardItem(f"${price:.2f}"),
                    QStandardItem(f"${disc:.2f}"),
                    QStandardItem(f"${total:.2f}"),
                    QStandardItem(),
                ]
            )
            remove_button = QPushButton("Quitar")
            set_button_icon(remove_button, "delete", color="#008FA3")
            remove_button.setProperty("variant", "secondary")
            remove_button.setStyleSheet("padding: 3px 8px; border-radius: 6px;")
            remove_button.setFixedHeight(30)
            remove_button.setToolTip(f"Quitar {product.name} de la venta")
            remove_button.setEnabled(self._can_create)
            remove_button.clicked.connect(
                lambda _checked=False, row_index=index: self._remove_cart_line(row_index)
            )
            self.cart_table.setIndexWidget(
                self.cart_model.index(index, action_column), remove_button
            )
            self.cart_table.setRowHeight(index, 36)
        self._refresh_totals()

    def _cart_subtotal(self) -> Decimal:
        total = Decimal("0")
        for row in self._cart:
            total += row["qty"] * row["unit_price"] - row["discount"]
        return total.quantize(Decimal("0.01"))

    def _refresh_totals(self) -> None:
        subtotal = self._cart_subtotal()
        discount = Decimal(str(self.discount_input.value()))
        tax = Decimal(str(self.tax_input.value()))
        total = subtotal - discount + tax
        self.totals_label.setText(
            f"Subtotal: ${subtotal:.2f}   Total: ${total:.2f}"
        )

    def _on_confirm(self) -> None:
        if not self._cart:
            QMessageBox.information(self, "Ventas", "El carrito está vacío.")
            return
        lines = tuple(
            CartLine(
                product_id=row["product"].id,
                quantity=row["qty"],
                unit_price=row["unit_price"],
                discount_amount=row["discount"],
            )
            for row in self._cart
        )
        data = SaleFormData(
                owner_id=self.owner_selector.current_id(),
            payment_method=self.payment_combo.currentData(),
            discount_amount=str(self.discount_input.value()),
            tax_amount=str(self.tax_input.value()),
            notes=self.notes_input.toPlainText(),
            lines=lines,
        )
        try:
            sale_id = sales_service.complete_sale(data)
        except ValidationError as exc:
            QMessageBox.warning(self, "Ventas", str(exc))
            return
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Ventas", str(exc))
            return
        self._clear_cart()
        self.refresh_catalog()
        self.refresh_history(selected_id=sale_id)
        self.sale_dialog.accept()
        sale = next((item for item in self._sales if item.id == sale_id), None)
        invoice = sale.invoice_number if sale else str(sale_id)
        QMessageBox.information(
            self, "Venta registrada", f"Venta completada.\nFactura: {invoice}"
        )

    def _create_product(self) -> None:
        dialog = ProductDialog(parent=self)
        if not dialog.exec() or dialog.created_id is None:
            return
        self.refresh_catalog()
        self.product_selector.select_id(dialog.created_id)

    def _create_owner(self) -> None:
        dialog = OwnerDialog(parent=self)
        if not dialog.exec() or dialog.created_id is None:
            return
        self.refresh_catalog()
        self.owner_selector.select_id(dialog.created_id)

    def _on_view_sale(self) -> None:
        indexes = self.hist_table.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(self, "Ventas", "Seleccione una venta.")
            return
        sale = self._sales[indexes[0].row()]
        self._show_sale_detail(sale.id)

    def _show_sale_detail(self, sale_id: int) -> None:
        try:
            detail = sales_service.get_sale(sale_id)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Ventas", str(exc))
            return
        if detail is None:
            return
        SaleDetailDialog(detail, parent=self).exec()
