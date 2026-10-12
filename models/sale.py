"""Modelos lógicos del módulo de ventas."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


PAYMENT_METHODS = ("CASH", "CARD", "TRANSFER", "OTHER")
SALE_STATUSES = ("DRAFT", "COMPLETED", "CANCELLED", "REFUNDED")

PAYMENT_LABELS = {
    "CASH": "Efectivo",
    "CARD": "Tarjeta",
    "TRANSFER": "Transferencia",
    "OTHER": "Otro",
}

STATUS_LABELS = {
    "DRAFT": "Borrador",
    "COMPLETED": "Completada",
    "CANCELLED": "Cancelada",
    "REFUNDED": "Reembolsada",
}


@dataclass(frozen=True)
class SaleItem:
    id: int
    sale_id: int
    product_id: int
    lot_id: int | None
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    line_total: Decimal | None
    product_name: str | None = None
    lot_number: str | None = None


@dataclass(frozen=True)
class Sale:
    id: int
    invoice_number: str
    owner_id: int | None
    sold_by: int
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total: Decimal
    payment_method: str
    status: str
    notes: str | None
    sold_at: datetime
    owner_name: str | None = None
    sold_by_name: str | None = None
    items: tuple[SaleItem, ...] = field(default_factory=tuple)
