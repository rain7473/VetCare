"""Modelos lógicos del módulo de inventario."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class ProductCategory:
    id: int
    name: str
    description: str | None
    is_active: bool


@dataclass(frozen=True)
class Supplier:
    id: int
    name: str
    tax_id: str | None
    contact_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Product:
    id: int
    category_id: int | None
    name: str
    sku: str | None
    barcode: str | None
    description: str | None
    unit: str
    sale_price: Decimal
    minimum_stock: Decimal
    location: str | None
    requires_lot: bool
    requires_expiry: bool
    is_active: bool
    category_name: str | None = None
    stock_available: Decimal = Decimal("0")
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_low_stock(self) -> bool:
        return self.stock_available < self.minimum_stock


@dataclass(frozen=True)
class InventoryLot:
    id: int
    product_id: int
    supplier_id: int | None
    lot_number: str | None
    expiry_date: date | None
    unit_cost: Decimal
    quantity_received: Decimal
    quantity_available: Decimal
    received_at: datetime
    notes: str | None
    product_name: str | None = None
    supplier_name: str | None = None


@dataclass(frozen=True)
class StockMovement:
    id: int
    product_id: int
    lot_id: int | None
    movement_type: str
    quantity: Decimal
    reference_type: str | None
    reference_id: int | None
    performed_by: int | None
    notes: str | None
    created_at: datetime
    product_name: str | None = None
    lot_number: str | None = None
    performed_by_name: str | None = None
