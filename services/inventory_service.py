"""Service de inventario: productos, proveedores, lotes y movimientos.

El stock disponible se calcula como la suma de QUANTITY_AVAILABLE de
lotes. Las entradas crean lote + movimiento ENTRY de forma atómica.
Las salidas/ajustes actualizan el lote y registran el movimiento.
Las ventas registran movimientos SALE y descuentan lotes desde sales_service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import oracledb

from database.connection import connection_scope
from models.inventory import (
    InventoryLot,
    Product,
    ProductCategory,
    StockMovement,
    Supplier,
)
from repositories import audit_repository, inventory_repository
from services import permission_service, session
from utils import validators
from utils.validators import ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CategoryFormData:
    name: str
    description: str


@dataclass(frozen=True)
class SupplierFormData:
    name: str
    tax_id: str
    contact_name: str
    phone: str
    email: str
    address: str
    is_active: bool = True


@dataclass(frozen=True)
class ProductFormData:
    category_id: int | None
    name: str
    sku: str
    barcode: str
    description: str
    unit: str
    sale_price: str
    minimum_stock: str
    location: str
    requires_lot: bool
    requires_expiry: bool
    is_active: bool = True


@dataclass(frozen=True)
class StockEntryData:
    product_id: int | None
    supplier_id: int | None
    lot_number: str
    expiry_date: date | None
    unit_cost: str
    quantity: str
    notes: str


@dataclass(frozen=True)
class StockAdjustData:
    lot_id: int | None
    movement_type: str  # ADJUSTMENT_IN | ADJUSTMENT_OUT | EXPIRED
    quantity: str
    notes: str


def _parse_decimal(raw: str, label: str, *, allow_zero: bool = False) -> Decimal:
    text = (raw or "").strip().replace(",", ".")
    if not text:
        raise ValidationError(f"{label} es obligatorio.")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValidationError(f"{label} no es un número válido.") from exc
    if value < 0:
        raise ValidationError(f"{label} no puede ser negativo.")
    if not allow_zero and value == 0:
        raise ValidationError(f"{label} debe ser mayor que cero.")
    return value


def list_categories(*, active_only: bool = False) -> list[ProductCategory]:
    permission_service.require_permission("INVENTORY_READ")
    with connection_scope() as conn:
        return inventory_repository.list_categories(conn, active_only=active_only)


def create_category(data: CategoryFormData) -> int:
    permission_service.require_permission("INVENTORY_MANAGE")
    name = validators.validate_required_text(data.name, "El nombre de la categoría", 100)
    with connection_scope(commit=True) as conn:
        return inventory_repository.insert_category(
            conn,
            name=name,
            description=validators.validate_optional_text(
                data.description, "La descripción", 4000
            ),
        )


def list_suppliers(*, active_only: bool = False) -> list[Supplier]:
    permission_service.require_permission("INVENTORY_READ")
    with connection_scope() as conn:
        return inventory_repository.list_suppliers(conn, active_only=active_only)


def create_supplier(data: SupplierFormData) -> int:
    permission_service.require_permission("INVENTORY_MANAGE")
    with connection_scope(commit=True) as conn:
        return _save_supplier(conn, None, data)


def update_supplier(supplier_id: int, data: SupplierFormData) -> None:
    permission_service.require_permission("INVENTORY_MANAGE")
    with connection_scope(commit=True) as conn:
        if inventory_repository.get_supplier(conn, supplier_id) is None:
            raise ValidationError("El proveedor no existe.")
        _save_supplier(conn, supplier_id, data)


def _save_supplier(
    conn: oracledb.Connection, supplier_id: int | None, data: SupplierFormData
) -> int:
    name = validators.validate_required_text(data.name, "El nombre del proveedor", 150)
    tax_id = validators.validate_optional_text(data.tax_id, "El NIT/RUC", 50)
    contact = validators.validate_optional_text(
        data.contact_name, "El contacto", 150
    )
    phone = validators.validate_phone_optional(data.phone) if data.phone.strip() else None
    email = validators.validate_email_optional(data.email)
    address = validators.validate_optional_text(data.address, "La dirección", 4000)
    if supplier_id is None:
        return inventory_repository.insert_supplier(
            conn,
            name=name,
            tax_id=tax_id,
            contact_name=contact,
            phone=phone,
            email=email,
            address=address,
        )
    inventory_repository.update_supplier(
        conn,
        supplier_id,
        name=name,
        tax_id=tax_id,
        contact_name=contact,
        phone=phone,
        email=email,
        address=address,
        is_active=data.is_active,
    )
    return supplier_id


def list_products(*, active_only: bool = False) -> list[Product]:
    permission_service.require_permission("INVENTORY_READ")
    with connection_scope() as conn:
        return inventory_repository.list_products(conn, active_only=active_only)


def get_product(product_id: int) -> Product | None:
    permission_service.require_permission("INVENTORY_READ")
    with connection_scope() as conn:
        return inventory_repository.get_product(conn, product_id)


def find_by_barcode(barcode: str) -> Product | None:
    """Busca un producto activo por código de barras exacto."""
    permission_service.require_permission("INVENTORY_READ")
    code = validators.validate_required_text(
        barcode, "El código de barras", 100
    )
    with connection_scope() as conn:
        return _find_active_by_barcode(conn, code)


def _find_active_by_barcode(
    conn, barcode: str
) -> Product | None:
    product = inventory_repository.find_by_barcode(conn, barcode)
    if product is None or not product.is_active:
        return None
    return product


def create_product(data: ProductFormData) -> int:
    permission_service.require_permission("INVENTORY_MANAGE")
    with connection_scope(commit=True) as conn:
        return _save_product(conn, None, data)


def update_product(product_id: int, data: ProductFormData) -> None:
    permission_service.require_permission("INVENTORY_MANAGE")
    with connection_scope(commit=True) as conn:
        if inventory_repository.get_product(conn, product_id) is None:
            raise ValidationError("El producto no existe.")
        _save_product(conn, product_id, data)


def _save_product(
    conn: oracledb.Connection, product_id: int | None, data: ProductFormData
) -> int:
    name = validators.validate_required_text(data.name, "El nombre del producto", 150)
    unit = validators.validate_required_text(data.unit, "La unidad", 30)
    sku = validators.validate_optional_text(data.sku, "El SKU", 80)
    barcode = validators.validate_optional_text(data.barcode, "El código de barras", 100)
    description = validators.validate_optional_text(
        data.description, "La descripción", 4000
    )
    location = validators.validate_optional_text(data.location, "La ubicación", 100)
    sale_price = _parse_decimal(data.sale_price, "El precio de venta", allow_zero=True)
    minimum_stock = _parse_decimal(
        data.minimum_stock, "El stock mínimo", allow_zero=True
    )

    if data.category_id is not None:
        cats = {
            c.id
            for c in inventory_repository.list_categories(conn, active_only=False)
        }
        if data.category_id not in cats:
            raise ValidationError("La categoría seleccionada no existe.")

    if sku and inventory_repository.sku_exists(conn, sku, exclude_id=product_id):
        raise ValidationError("Ya existe un producto con ese SKU.")
    if barcode and inventory_repository.barcode_exists(
        conn, barcode, exclude_id=product_id
    ):
        raise ValidationError("Ya existe un producto con ese código de barras.")

    if data.requires_expiry and not data.requires_lot:
        raise ValidationError(
            "Si el producto requiere vencimiento, también debe requerir lote."
        )

    if product_id is None:
        product_id = inventory_repository.insert_product(
            conn,
            category_id=data.category_id,
            name=name,
            sku=sku,
            barcode=barcode,
            description=description,
            unit=unit,
            sale_price=sale_price,
            minimum_stock=minimum_stock,
            location=location,
            requires_lot=data.requires_lot,
            requires_expiry=data.requires_expiry,
        )
        logger.info("Producto creado: id=%s", product_id)
        return product_id

    inventory_repository.update_product(
        conn,
        product_id,
        category_id=data.category_id,
        name=name,
        sku=sku,
        barcode=barcode,
        description=description,
        unit=unit,
        sale_price=sale_price,
        minimum_stock=minimum_stock,
        location=location,
        requires_lot=data.requires_lot,
        requires_expiry=data.requires_expiry,
        is_active=data.is_active,
    )
    logger.info("Producto actualizado: id=%s", product_id)
    return product_id


def list_lots(product_id: int, *, available_only: bool = False) -> list[InventoryLot]:
    permission_service.require_permission("INVENTORY_READ")
    with connection_scope() as conn:
        return inventory_repository.list_lots_for_product(
            conn, product_id, available_only=available_only
        )


def list_low_stock() -> list[Product]:
    permission_service.require_permission("INVENTORY_READ")
    with connection_scope() as conn:
        return [
            p
            for p in inventory_repository.list_products(conn, active_only=True)
            if p.is_low_stock
        ]


def list_expiring(days: int = 30) -> list[InventoryLot]:
    permission_service.require_permission("INVENTORY_READ")
    until = date.today() + timedelta(days=days)
    with connection_scope() as conn:
        return inventory_repository.list_expiring_lots(conn, until)


def list_movements(product_id: int | None = None) -> list[StockMovement]:
    permission_service.require_permission("INVENTORY_READ")
    with connection_scope() as conn:
        return inventory_repository.list_movements(conn, product_id=product_id)


def receive_stock(data: StockEntryData) -> int:
    """Entrada de inventario: crea lote + movimiento ENTRY (atómico)."""
    permission_service.require_permission("INVENTORY_MANAGE")
    with connection_scope(commit=True) as conn:
        lot_id = _receive_stock(conn, data)
        current = session.get_current_user()
        audit_repository.insert_event(
            conn,
            user_id=current.id if current else None,
            entity_type="INVENTORY_LOT",
            entity_id=lot_id,
            action="STOCK_ENTRY",
            new_data={
                "product_id": data.product_id,
                "quantity": data.quantity,
                "lot_number": data.lot_number,
            },
        )
        return lot_id


def _receive_stock(conn: oracledb.Connection, data: StockEntryData) -> int:
    current = session.get_current_user()
    if current is None:
        raise ValidationError("No hay una sesión activa.")
    if data.product_id is None:
        raise ValidationError("Seleccione el producto.")

    product = inventory_repository.get_product(conn, data.product_id)
    if product is None:
        raise ValidationError("El producto no existe.")
    if not product.is_active:
        raise ValidationError("No se puede recibir stock de un producto inactivo.")

    quantity = _parse_decimal(data.quantity, "La cantidad")
    unit_cost = _parse_decimal(data.unit_cost, "El costo unitario", allow_zero=True)
    lot_number = validators.validate_optional_text(data.lot_number, "El lote", 100)
    notes = validators.validate_optional_text(data.notes, "Las notas", 4000)

    if product.requires_lot and not lot_number:
        raise ValidationError("Este producto requiere número de lote.")
    if product.requires_expiry and data.expiry_date is None:
        raise ValidationError("Este producto requiere fecha de vencimiento.")
    if data.expiry_date is not None and data.expiry_date < date.today():
        raise ValidationError("No se puede recibir un lote ya vencido.")

    if data.supplier_id is not None:
        supplier = inventory_repository.get_supplier(conn, data.supplier_id)
        if supplier is None or not supplier.is_active:
            raise ValidationError("El proveedor no existe o está inactivo.")

    lot_id = inventory_repository.insert_lot(
        conn,
        product_id=product.id,
        supplier_id=data.supplier_id,
        lot_number=lot_number,
        expiry_date=data.expiry_date,
        unit_cost=unit_cost,
        quantity_received=quantity,
        notes=notes,
    )
    inventory_repository.insert_movement(
        conn,
        product_id=product.id,
        lot_id=lot_id,
        movement_type="ENTRY",
        quantity=quantity,
        reference_type="INVENTORY_LOT",
        reference_id=lot_id,
        performed_by=current.id,
        notes=notes,
    )
    logger.info(
        "Entrada de stock: product=%s lot=%s qty=%s", product.id, lot_id, quantity
    )
    return lot_id


def adjust_stock(data: StockAdjustData) -> int:
    """Ajuste de lote: ADJUSTMENT_IN / ADJUSTMENT_OUT / EXPIRED."""
    permission_service.require_permission("INVENTORY_MANAGE")
    with connection_scope(commit=True) as conn:
        movement_id = _adjust_stock(conn, data)
        current = session.get_current_user()
        audit_repository.insert_event(
            conn,
            user_id=current.id if current else None,
            entity_type="STOCK_MOVEMENT",
            entity_id=movement_id,
            action=data.movement_type,
            new_data={"lot_id": data.lot_id, "quantity": data.quantity},
        )
        return movement_id


def _adjust_stock(conn: oracledb.Connection, data: StockAdjustData) -> int:
    current = session.get_current_user()
    if current is None:
        raise ValidationError("No hay una sesión activa.")
    if data.lot_id is None:
        raise ValidationError("Seleccione el lote.")
    if data.movement_type not in {"ADJUSTMENT_IN", "ADJUSTMENT_OUT", "EXPIRED"}:
        raise ValidationError("Tipo de ajuste no permitido.")

    lot = inventory_repository.get_lot(conn, data.lot_id)
    if lot is None:
        raise ValidationError("El lote no existe.")

    quantity = _parse_decimal(data.quantity, "La cantidad")
    notes = validators.validate_optional_text(data.notes, "Las notas", 4000)

    if data.movement_type == "ADJUSTMENT_IN":
        new_qty = lot.quantity_available + quantity
    else:
        if quantity > lot.quantity_available:
            raise ValidationError(
                "La cantidad supera el disponible del lote "
                f"({lot.quantity_available})."
            )
        new_qty = lot.quantity_available - quantity

    inventory_repository.adjust_lot_quantity(conn, lot.id, new_qty)
    movement_id = inventory_repository.insert_movement(
        conn,
        product_id=lot.product_id,
        lot_id=lot.id,
        movement_type=data.movement_type,
        quantity=quantity,
        reference_type="INVENTORY_LOT",
        reference_id=lot.id,
        performed_by=current.id,
        notes=notes,
    )
    logger.info(
        "Ajuste stock: lot=%s type=%s qty=%s → %s",
        lot.id,
        data.movement_type,
        quantity,
        new_qty,
    )
    return movement_id


# Helpers para pruebas con ROLLBACK (sin commit del scope).
def _create_product(conn: oracledb.Connection, data: ProductFormData) -> int:
    return _save_product(conn, None, data)


def _create_supplier(conn: oracledb.Connection, data: SupplierFormData) -> int:
    return _save_supplier(conn, None, data)
