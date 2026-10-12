"""Diálogos del módulo de inventario."""

from __future__ import annotations

from datetime import date

from utils.icons import set_button_icon

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from database.connection import DatabaseConnectionError
from models.inventory import InventoryLot, Product, Supplier
from services import inventory_service
from services.inventory_service import (
    CategoryFormData,
    ProductFormData,
    StockAdjustData,
    StockEntryData,
    SupplierFormData,
)
from services.permission_service import PermissionDeniedError
from utils.validators import ValidationError
from widgets.dynamic_selector import DynamicEntitySelector, SelectorItem
from widgets.managed_dialog import ManagedDialog


class CategoryDialog(ManagedDialog):
    """Alta rápida de categoría para creación encadenada de productos."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.created_id: int | None = None
        self.setWindowTitle("Nueva categoría")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()
        self.name_input = QLineEdit()
        form.addRow("Nombre", self.name_input)
        self.description_input = QTextEdit()
        self.description_input.setFixedHeight(52)
        form.addRow("Descripción", self.description_input)
        layout.addLayout(form)
        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("variant", "secondary")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Guardar")
        save.clicked.connect(self._on_save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _on_save(self) -> None:
        try:
            self.created_id = inventory_service.create_category(
                CategoryFormData(
                    name=self.name_input.text(),
                    description=self.description_input.toPlainText(),
                )
            )
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        self.accept()


class ProductDialog(ManagedDialog):
    """Crear / editar producto."""

    def __init__(self, product: Product | None = None, parent=None) -> None:
        super().__init__(parent)
        self._product = product
        self.created_id: int | None = None
        self.setWindowTitle("Editar producto" if product else "Nuevo producto")
        self.setMinimumWidth(520)
        self._categories: list[tuple[int | None, str]] = [(None, "— Sin categoría —")]
        self._build_ui()
        self._load_categories()
        if product is not None:
            self._load_product()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.name_input = QLineEdit()
        form.addRow("Nombre", self.name_input)

        self.category_selector = DynamicEntitySelector(
            placeholder="Buscar categoría…",
            add_tooltip="Crear categoría",
            allow_empty=True,
            empty_label="— Sin categoría —",
        )
        self.category_selector.add_requested.connect(self._create_category)
        form.addRow("Categoría", self.category_selector)

        self.sku_input = QLineEdit()
        self.sku_input.setPlaceholderText("Opcional")
        form.addRow("SKU", self.sku_input)

        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Opcional")
        form.addRow("Código de barras", self.barcode_input)

        self.unit_input = QLineEdit()
        self.unit_input.setPlaceholderText("ej. unidad, caja, ml")
        form.addRow("Unidad", self.unit_input)

        self.price_input = QDoubleSpinBox()
        self.price_input.setRange(0, 1_000_000)
        self.price_input.setDecimals(2)
        self.price_input.setPrefix("$ ")
        form.addRow("Precio venta", self.price_input)

        self.min_stock_input = QDoubleSpinBox()
        self.min_stock_input.setRange(0, 1_000_000)
        self.min_stock_input.setDecimals(2)
        form.addRow("Stock mínimo", self.min_stock_input)

        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("Opcional")
        form.addRow("Ubicación", self.location_input)

        self.description_input = QTextEdit()
        self.description_input.setFixedHeight(60)
        form.addRow("Descripción", self.description_input)

        self.requires_lot = QCheckBox("Requiere lote")
        self.requires_expiry = QCheckBox("Requiere vencimiento")
        form.addRow("", self.requires_lot)
        form.addRow("", self.requires_expiry)

        self.active_check = QCheckBox("Producto activo")
        self.active_check.setChecked(True)
        if self._product is None:
            self.active_check.setVisible(False)
        form.addRow("", self.active_check)

        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("variant", "secondary")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        save = QPushButton("Guardar")
        save.clicked.connect(self._on_save)
        actions.addWidget(save)
        layout.addLayout(actions)

    def _load_categories(self) -> None:
        try:
            cats = inventory_service.list_categories(active_only=True)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Inventario", str(exc))
            return
        self._categories = [(None, "— Sin categoría —")] + [
            (c.id, c.name) for c in cats
        ]
        self.category_selector.set_items(
            [SelectorItem(cid, label) for cid, label in self._categories if cid is not None],
            selected_id=None,
        )

    def _load_product(self) -> None:
        p = self._product
        assert p is not None
        self.name_input.setText(p.name)
        self.sku_input.setText(p.sku or "")
        self.barcode_input.setText(p.barcode or "")
        self.unit_input.setText(p.unit)
        self.price_input.setValue(float(p.sale_price))
        self.min_stock_input.setValue(float(p.minimum_stock))
        self.location_input.setText(p.location or "")
        self.description_input.setPlainText(p.description or "")
        self.requires_lot.setChecked(p.requires_lot)
        self.requires_expiry.setChecked(p.requires_expiry)
        self.active_check.setChecked(p.is_active)
        self.category_selector.select_id(p.category_id)

    def _form_data(self) -> ProductFormData:
        return ProductFormData(
            category_id=self.category_selector.current_id(),
            name=self.name_input.text(),
            sku=self.sku_input.text(),
            barcode=self.barcode_input.text(),
            description=self.description_input.toPlainText(),
            unit=self.unit_input.text(),
            sale_price=str(self.price_input.value()),
            minimum_stock=str(self.min_stock_input.value()),
            location=self.location_input.text(),
            requires_lot=self.requires_lot.isChecked(),
            requires_expiry=self.requires_expiry.isChecked(),
            is_active=self.active_check.isChecked(),
        )

    def _on_save(self) -> None:
        self.error_label.setVisible(False)
        data = self._form_data()
        try:
            if self._product is None:
                self.created_id = inventory_service.create_product(data)
            else:
                inventory_service.update_product(self._product.id, data)
        except ValidationError as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Inventario", str(exc))
            return
        self.accept()

    def _create_category(self) -> None:
        dialog = CategoryDialog(parent=self)
        if not dialog.exec() or dialog.created_id is None:
            return
        self._load_categories()
        self.category_selector.select_id(dialog.created_id)


class SupplierDialog(ManagedDialog):
    """Crear / editar proveedor."""

    def __init__(self, supplier: Supplier | None = None, parent=None) -> None:
        super().__init__(parent)
        self._supplier = supplier
        self.created_id: int | None = None
        self.setWindowTitle("Editar proveedor" if supplier else "Nuevo proveedor")
        self.setMinimumWidth(480)
        self._build_ui()
        if supplier is not None:
            self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.name_input = QLineEdit()
        form.addRow("Nombre", self.name_input)
        self.tax_input = QLineEdit()
        form.addRow("NIT / RUC", self.tax_input)
        self.contact_input = QLineEdit()
        form.addRow("Contacto", self.contact_input)
        self.phone_input = QLineEdit()
        form.addRow("Teléfono", self.phone_input)
        self.email_input = QLineEdit()
        form.addRow("Email", self.email_input)
        self.address_input = QTextEdit()
        self.address_input.setFixedHeight(60)
        form.addRow("Dirección", self.address_input)
        self.active_check = QCheckBox("Proveedor activo")
        self.active_check.setChecked(True)
        if self._supplier is None:
            self.active_check.setVisible(False)
        form.addRow("", self.active_check)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("variant", "secondary")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        save = QPushButton("Guardar")
        save.clicked.connect(self._on_save)
        actions.addWidget(save)
        layout.addLayout(actions)

    def _load(self) -> None:
        s = self._supplier
        assert s is not None
        self.name_input.setText(s.name)
        self.tax_input.setText(s.tax_id or "")
        self.contact_input.setText(s.contact_name or "")
        self.phone_input.setText(s.phone or "")
        self.email_input.setText(s.email or "")
        self.address_input.setPlainText(s.address or "")
        self.active_check.setChecked(s.is_active)

    def _on_save(self) -> None:
        data = SupplierFormData(
            name=self.name_input.text(),
            tax_id=self.tax_input.text(),
            contact_name=self.contact_input.text(),
            phone=self.phone_input.text(),
            email=self.email_input.text(),
            address=self.address_input.toPlainText(),
            is_active=self.active_check.isChecked(),
        )
        try:
            if self._supplier is None:
                self.created_id = inventory_service.create_supplier(data)
            else:
                inventory_service.update_supplier(self._supplier.id, data)
        except ValidationError as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Inventario", str(exc))
            return
        self.accept()


class SuppliersDialog(ManagedDialog):
    """Listado simple de proveedores con alta/edición."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Proveedores")
        self.setMinimumSize(640, 420)
        self._suppliers: list[Supplier] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)

        header = QHBoxLayout()
        header.addWidget(QLabel("Proveedores"))
        header.addStretch()
        add = QPushButton("Nuevo")
        set_button_icon(add, "add")
        add.clicked.connect(self._on_new)
        header.addWidget(add)
        layout.addLayout(header)

        from PySide6.QtGui import QStandardItem, QStandardItemModel
        from PySide6.QtWidgets import QHeaderView, QTableView

        self.model = QStandardItemModel(0, 4)
        self.model.setHorizontalHeaderLabels(["Nombre", "Contacto", "Teléfono", "Estado"])
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(lambda _: self._on_edit())
        layout.addWidget(self.table, stretch=1)

        actions = QHBoxLayout()
        actions.addStretch()
        edit = QPushButton("Editar")
        edit.setProperty("variant", "secondary")
        edit.clicked.connect(self._on_edit)
        actions.addWidget(edit)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        layout.addLayout(actions)

    def refresh(self) -> None:
        from PySide6.QtGui import QStandardItem

        try:
            self._suppliers = inventory_service.list_suppliers()
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Inventario", str(exc))
            return
        self.model.setRowCount(0)
        for s in self._suppliers:
            self.model.appendRow(
                [
                    QStandardItem(s.name),
                    QStandardItem(s.contact_name or "—"),
                    QStandardItem(s.phone or "—"),
                    QStandardItem("Activo" if s.is_active else "Inactivo"),
                ]
            )

    def _selected(self) -> Supplier | None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return None
        return self._suppliers[indexes[0].row()]

    def _on_new(self) -> None:
        if SupplierDialog(parent=self).exec() == QDialog.Accepted:
            self.refresh()

    def _on_edit(self) -> None:
        supplier = self._selected()
        if supplier is None:
            QMessageBox.information(self, "Proveedores", "Seleccione un proveedor.")
            return
        if SupplierDialog(supplier, parent=self).exec() == QDialog.Accepted:
            self.refresh()


class StockEntryDialog(ManagedDialog):
    """Entrada de stock (crea lote + movimiento ENTRY)."""

    def __init__(self, product: Product | None = None, parent=None) -> None:
        super().__init__(parent)
        self._preset_product = product
        self.created_lot_id: int | None = None
        self.setWindowTitle("Entrada de stock")
        self.setMinimumWidth(480)
        self._products: list[Product] = []
        self._suppliers: list[Supplier] = []
        self._build_ui()
        self._load_lists()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.product_selector = DynamicEntitySelector(
            placeholder="Buscar producto, SKU o código…",
            add_tooltip="Crear producto",
        )
        self.product_selector.add_requested.connect(self._create_product)
        form.addRow("Producto", self.product_selector)

        self.supplier_selector = DynamicEntitySelector(
            placeholder="Buscar proveedor, RUC o contacto…",
            add_tooltip="Crear proveedor",
            allow_empty=True,
            empty_label="— Sin proveedor —",
        )
        self.supplier_selector.add_requested.connect(self._create_supplier)
        form.addRow("Proveedor", self.supplier_selector)

        self.lot_input = QLineEdit()
        form.addRow("Nº lote", self.lot_input)

        self.expiry_input = QDateEdit()
        self.expiry_input.setCalendarPopup(True)
        self.expiry_input.setDisplayFormat("dd/MM/yyyy")
        self.expiry_input.setDate(QDate.currentDate().addYears(1))
        self.expiry_input.setSpecialValueText("Sin vencimiento")
        form.addRow("Vencimiento", self.expiry_input)

        self.qty_input = QDoubleSpinBox()
        self.qty_input.setRange(0.01, 1_000_000)
        self.qty_input.setDecimals(2)
        self.qty_input.setValue(1)
        form.addRow("Cantidad", self.qty_input)

        self.cost_input = QDoubleSpinBox()
        self.cost_input.setRange(0, 1_000_000)
        self.cost_input.setDecimals(2)
        self.cost_input.setPrefix("$ ")
        form.addRow("Costo unitario", self.cost_input)

        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(50)
        form.addRow("Notas", self.notes_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("variant", "secondary")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        save = QPushButton("Registrar entrada")
        save.clicked.connect(self._on_save)
        actions.addWidget(save)
        layout.addLayout(actions)

    def _load_lists(self) -> None:
        try:
            self._products = inventory_service.list_products(active_only=True)
            self._suppliers = inventory_service.list_suppliers(active_only=True)
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Inventario", str(exc))
            return
        self.product_selector.set_items(
            [
                SelectorItem(
                    p.id,
                    f"{p.name} ({p.unit})",
                    " ".join(filter(None, [p.sku, p.barcode, p.location])),
                )
                for p in self._products
            ],
            selected_id=self._preset_product.id if self._preset_product else None,
        )
        self.supplier_selector.set_items(
            [
                SelectorItem(
                    s.id,
                    s.name,
                    " ".join(filter(None, [s.tax_id, s.contact_name, s.phone, s.email])),
                )
                for s in self._suppliers
            ],
            selected_id=None,
        )

    def _on_save(self) -> None:
        product_id = self.product_selector.current_id()
        supplier_id = self.supplier_selector.current_id()
        expiry_qdate = self.expiry_input.date()
        expiry: date | None = date(
            expiry_qdate.year(), expiry_qdate.month(), expiry_qdate.day()
        )
        # Si el usuario limpia o no quiere vencimiento, permitir None vía checkbox implícito:
        # usamos fecha solo si el producto lo requiere; si no, aún enviamos la fecha del control
        # salvo que se deje en "pasado lejano" — mejor: siempre enviar la fecha del control;
        # el service valida requires_expiry.
        data = StockEntryData(
            product_id=product_id,
            supplier_id=supplier_id,
            lot_number=self.lot_input.text(),
            expiry_date=expiry,
            unit_cost=str(self.cost_input.value()),
            quantity=str(self.qty_input.value()),
            notes=self.notes_input.toPlainText(),
        )
        try:
            self.created_lot_id = inventory_service.receive_stock(data)
        except ValidationError as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Inventario", str(exc))
            return
        self.accept()

    def _create_product(self) -> None:
        dialog = ProductDialog(parent=self)
        if not dialog.exec() or dialog.created_id is None:
            return
        self._load_lists()
        self.product_selector.select_id(dialog.created_id)

    def _create_supplier(self) -> None:
        dialog = SupplierDialog(parent=self)
        if not dialog.exec() or dialog.created_id is None:
            return
        self._load_lists()
        self.supplier_selector.select_id(dialog.created_id)


class StockAdjustDialog(ManagedDialog):
    """Ajuste / merma / vencido sobre un lote."""

    def __init__(self, product: Product, parent=None) -> None:
        super().__init__(parent)
        self._product = product
        self.setWindowTitle(f"Ajuste de stock — {product.name}")
        self.setMinimumWidth(460)
        self._lots: list[InventoryLot] = []
        self._build_ui()
        self._load_lots()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.lot_selector = DynamicEntitySelector(
            placeholder="Buscar lote o proveedor…",
            add_tooltip="Registrar entrada / lote",
        )
        self.lot_selector.add_requested.connect(self._create_lot)
        form.addRow("Lote", self.lot_selector)

        self.type_combo = QComboBox()
        self.type_combo.addItem("Ajuste entrada (+)", "ADJUSTMENT_IN")
        self.type_combo.addItem("Ajuste salida (−)", "ADJUSTMENT_OUT")
        self.type_combo.addItem("Vencido / merma", "EXPIRED")
        form.addRow("Tipo", self.type_combo)

        self.qty_input = QDoubleSpinBox()
        self.qty_input.setRange(0.01, 1_000_000)
        self.qty_input.setDecimals(2)
        self.qty_input.setValue(1)
        form.addRow("Cantidad", self.qty_input)

        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(50)
        form.addRow("Motivo", self.notes_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("variant", "secondary")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        save = QPushButton("Aplicar")
        save.clicked.connect(self._on_save)
        actions.addWidget(save)
        layout.addLayout(actions)

    def _load_lots(self) -> None:
        try:
            self._lots = inventory_service.list_lots(
                self._product.id, available_only=False
            )
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Inventario", str(exc))
            return
        self.lot_selector.set_items(
            [
                SelectorItem(
                    lot.id,
                    (
                        f"{lot.lot_number or 'Sin nº'} · disp. {lot.quantity_available}"
                        f"{' · vence ' + lot.expiry_date.strftime('%d/%m/%Y') if lot.expiry_date else ''}"
                    ),
                    lot.supplier_name or "",
                )
                for lot in self._lots
            ]
        )

    def _on_save(self) -> None:
        data = StockAdjustData(
            lot_id=self.lot_selector.current_id(),
            movement_type=self.type_combo.currentData(),
            quantity=str(self.qty_input.value()),
            notes=self.notes_input.toPlainText(),
        )
        try:
            inventory_service.adjust_stock(data)
        except ValidationError as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            return
        except (PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Inventario", str(exc))
            return
        self.accept()

    def _create_lot(self) -> None:
        dialog = StockEntryDialog(self._product, parent=self)
        if not dialog.exec() or dialog.created_lot_id is None:
            return
        self._load_lots()
        self.lot_selector.select_id(dialog.created_lot_id)
