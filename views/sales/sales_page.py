"""Página de ventas: punto de venta con escáner, carrito e historial."""

from __future__ import annotations

from decimal import Decimal

from utils.icons import set_button_icon

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
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
from widgets.barcode_scanner import BarcodeScannerInput
from widgets.dynamic_selector import DynamicEntitySelector, SelectorItem

_CART_COLS = ["Producto", "Cant.", "Precio", "Desc.", "Total"]
_HIST_COLS = ["Factura", "Fecha", "Cliente", "Total", "Pago", "Estado", "Vendedor"]


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

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_pos_panel())
        splitter.addWidget(self._build_history_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, stretch=1)

    def _build_pos_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Punto de venta"))

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
        self.cart_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.cart_table, stretch=1)

        cart_actions = QHBoxLayout()
        remove = QPushButton("Quitar línea")
        set_button_icon(remove, "delete", color="#008FA3")
        remove.setProperty("variant", "secondary")
        remove.clicked.connect(self._on_remove_line)
        remove.setEnabled(self._can_create)
        cart_actions.addWidget(remove)
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
        head.addWidget(QLabel("Historial reciente"))
        head.addStretch()
        refresh = QPushButton("Actualizar")
        set_button_icon(refresh, "refresh", color="#008FA3")
        refresh.setProperty("variant", "secondary")
        refresh.clicked.connect(self.refresh_history)
        head.addWidget(refresh)
        layout.addLayout(head)

        self.hist_model = QStandardItemModel(0, len(_HIST_COLS))
        self.hist_model.setHorizontalHeaderLabels(_HIST_COLS)
        self.hist_table = QTableView()
        self.hist_table.setModel(self.hist_model)
        self.hist_table.setSelectionBehavior(QTableView.SelectRows)
        self.hist_table.setEditTriggers(QTableView.NoEditTriggers)
        self.hist_table.verticalHeader().setVisible(False)
        self.hist_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hist_table.doubleClicked.connect(lambda _: self._on_view_sale())
        layout.addWidget(self.hist_table, stretch=1)

        view = QPushButton("Ver detalle")
        set_button_icon(view, "view", color="#008FA3")
        view.setProperty("variant", "secondary")
        view.clicked.connect(self._on_view_sale)
        layout.addWidget(view)
        return panel

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loaded:
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

    def refresh_history(self) -> None:
        try:
            self._sales = sales_service.list_sales()
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Ventas", str(exc))
            return
        self.hist_model.setRowCount(0)
        for sale in self._sales:
            self.hist_model.appendRow(
                [
                    QStandardItem(sale.invoice_number),
                    QStandardItem(sale.sold_at.strftime("%d/%m/%Y %H:%M")),
                    QStandardItem(sale.owner_name or "Mostrador"),
                    QStandardItem(f"${sale.total:.2f}"),
                    QStandardItem(PAYMENT_LABELS.get(sale.payment_method, sale.payment_method)),
                    QStandardItem(STATUS_LABELS.get(sale.status, sale.status)),
                    QStandardItem(sale.sold_by_name or "—"),
                ]
            )

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

    def _on_remove_line(self) -> None:
        indexes = self.cart_table.selectionModel().selectedRows()
        if not indexes:
            return
        del self._cart[indexes[0].row()]
        self._render_cart()

    def _clear_cart(self) -> None:
        self._cart.clear()
        self.discount_input.setValue(0)
        self.tax_input.setValue(0)
        self.notes_input.clear()
        self._render_cart()

    def _render_cart(self) -> None:
        self.cart_model.setRowCount(0)
        for row in self._cart:
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
                ]
            )
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
            sale = sales_service.get_sale(sale_id)
        except ValidationError as exc:
            QMessageBox.warning(self, "Ventas", str(exc))
            return
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Ventas", str(exc))
            return
        invoice = sale.invoice_number if sale else str(sale_id)
        QMessageBox.information(
            self, "Venta registrada", f"Venta completada.\nFactura: {invoice}"
        )
        self._clear_cart()
        self.refresh_catalog()
        self.refresh_history()

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
        try:
            detail = sales_service.get_sale(sale.id)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Ventas", str(exc))
            return
        if detail is None:
            return
        lines = "\n".join(
            f"• {i.product_name} × {i.quantity:g} = ${i.line_total or 0:.2f}"
            for i in detail.items
        ) or "(sin líneas)"
        QMessageBox.information(
            self,
            detail.invoice_number,
            (
                f"Cliente: {detail.owner_name or 'Mostrador'}\n"
                f"Total: ${detail.total:.2f}\n"
                f"Pago: {PAYMENT_LABELS.get(detail.payment_method, detail.payment_method)}\n"
                f"Estado: {STATUS_LABELS.get(detail.status, detail.status)}\n\n"
                f"{lines}"
            ),
        )
