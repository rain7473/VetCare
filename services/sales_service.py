"""Service de ventas: carrito → venta COMPLETED + movimiento SALE atómico.

Flujo (una sola transacción Oracle):

1. Validar líneas, stock y totales.
2. INSERT SALES + SALE_ITEMS.
3. Descontar lotes (FIFO por vencimiento) y registrar STOCK_MOVEMENTS SALE.
4. COMMIT; si algo falla → ROLLBACK (sin venta huérfana ni stock a medias).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import oracledb

from database.connection import connection_scope
from models.sale import PAYMENT_METHODS, Sale
from repositories import (
    audit_repository,
    inventory_repository,
    owner_repository,
    sales_repository,
)
from services import permission_service, session
from services.permission_service import PermissionDeniedError
from utils import validators
from utils.validators import ValidationError

logger = logging.getLogger(__name__)

_MONEY = Decimal("0.01")


@dataclass(frozen=True)
class CartLine:
    product_id: int
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal = Decimal("0")


@dataclass(frozen=True)
class SaleFormData:
    owner_id: int | None
    payment_method: str
    discount_amount: str
    tax_amount: str
    notes: str
    lines: tuple[CartLine, ...]


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _parse_money(raw: str, label: str, *, allow_zero: bool = True) -> Decimal:
    text = (raw or "").strip().replace(",", ".")
    if not text:
        text = "0"
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValidationError(f"{label} no es un número válido.") from exc
    if value < 0:
        raise ValidationError(f"{label} no puede ser negativo.")
    if not allow_zero and value == 0:
        raise ValidationError(f"{label} debe ser mayor que cero.")
    return _money(value)


def list_sales() -> list[Sale]:
    seller_id = _visible_seller_id()
    with connection_scope() as conn:
        return sales_repository.list_sales(conn, sold_by=seller_id)


def get_sale(sale_id: int) -> Sale | None:
    seller_id = _visible_seller_id()
    with connection_scope() as conn:
        sale = sales_repository.get_sale(conn, sale_id)
    if sale is not None and seller_id is not None and sale.sold_by != seller_id:
        raise PermissionDeniedError("SALES_READ")
    return sale


def _visible_seller_id() -> int | None:
    """El vendedor sin permiso de lectura solo consulta sus propias ventas."""
    if permission_service.has_permission("SALES_READ"):
        return None
    permission_service.require_permission("SALES_CREATE")
    current = session.get_current_user()
    if current is None:
        raise PermissionDeniedError("SALES_READ")
    return current.id


def complete_sale(data: SaleFormData) -> int:
    """Registra una venta COMPLETED y descuenta inventario de forma atómica."""
    permission_service.require_permission("SALES_CREATE")
    with connection_scope(commit=True) as conn:
        sale_id = _complete_sale(conn, data)
        sale = sales_repository.get_sale(conn, sale_id)
        current = session.get_current_user()
        audit_repository.insert_event(
            conn,
            user_id=current.id if current else None,
            entity_type="SALE",
            entity_id=sale_id,
            action="COMPLETE",
            new_data={
                "invoice_number": sale.invoice_number if sale else None,
                "total": str(sale.total) if sale else None,
                "payment_method": sale.payment_method if sale else data.payment_method,
            },
        )
        return sale_id


def _complete_sale(conn: oracledb.Connection, data: SaleFormData) -> int:
    current = session.get_current_user()
    if current is None:
        raise ValidationError("No hay una sesión activa.")
    if not data.lines:
        raise ValidationError("Agregue al menos un producto a la venta.")
    if data.payment_method not in PAYMENT_METHODS:
        raise ValidationError("Método de pago no válido.")

    if data.owner_id is not None:
        owner = owner_repository.get_by_id(conn, data.owner_id)
        if owner is None:
            raise ValidationError("El propietario seleccionado no existe.")

    sale_discount = _parse_money(data.discount_amount, "El descuento global")
    tax_amount = _parse_money(data.tax_amount, "El impuesto")
    notes = validators.validate_optional_text(data.notes, "Las notas", 4000)

    # Expandir líneas a asignaciones por lote (FIFO) y calcular subtotal.
    allocations: list[tuple[int, int | None, Decimal, Decimal, Decimal, Decimal]] = []
    # (product_id, lot_id, qty, unit_price, line_discount, line_total)
    subtotal = Decimal("0")

    for line in data.lines:
        if line.quantity <= 0:
            raise ValidationError("La cantidad de cada línea debe ser mayor que cero.")
        if line.unit_price < 0:
            raise ValidationError("El precio unitario no puede ser negativo.")
        if line.discount_amount < 0:
            raise ValidationError("El descuento de línea no puede ser negativo.")

        product = inventory_repository.get_product(conn, line.product_id)
        if product is None or not product.is_active:
            raise ValidationError("Hay un producto inexistente o inactivo en el carrito.")

        qty = _money(line.quantity)
        unit_price = _money(line.unit_price)
        line_discount = _money(line.discount_amount)
        line_gross = _money(qty * unit_price)
        if line_discount > line_gross:
            raise ValidationError(
                f"El descuento de «{product.name}» supera el importe de la línea."
            )
        line_total = _money(line_gross - line_discount)
        subtotal += line_total

        lot_chunks = _allocate_fifo(conn, product.id, qty, product.name)
        remaining_discount = line_discount
        for i, (lot_id, chunk_qty) in enumerate(lot_chunks):
            # Prorratear descuento en el último chunk para cuadrar centavos.
            chunk_gross = _money(chunk_qty * unit_price)
            if i == len(lot_chunks) - 1:
                chunk_discount = remaining_discount
            else:
                share = (chunk_gross / line_gross) if line_gross else Decimal("0")
                chunk_discount = _money(line_discount * share)
                remaining_discount = _money(remaining_discount - chunk_discount)
            chunk_total = _money(chunk_gross - chunk_discount)
            allocations.append(
                (product.id, lot_id, chunk_qty, unit_price, chunk_discount, chunk_total)
            )

    subtotal = _money(subtotal)
    if sale_discount > subtotal:
        raise ValidationError("El descuento global no puede superar el subtotal.")
    total = _money(subtotal - sale_discount + tax_amount)

    invoice = sales_repository.next_invoice_number(conn, datetime.now())
    sale_id = sales_repository.insert_sale(
        conn,
        invoice_number=invoice,
        owner_id=data.owner_id,
        sold_by=current.id,
        subtotal=subtotal,
        discount_amount=sale_discount,
        tax_amount=tax_amount,
        total=total,
        payment_method=data.payment_method,
        status="COMPLETED",
        notes=notes,
    )

    for product_id, lot_id, qty, unit_price, chunk_discount, chunk_total in allocations:
        sales_repository.insert_sale_item(
            conn,
            sale_id=sale_id,
            product_id=product_id,
            lot_id=lot_id,
            quantity=qty,
            unit_price=unit_price,
            discount_amount=chunk_discount,
            line_total=chunk_total,
        )
        if lot_id is None:
            raise ValidationError(
                "No hay lote disponible para descontar stock de un producto."
            )
        lot = inventory_repository.get_lot(conn, lot_id)
        if lot is None:
            raise ValidationError("El lote asignado ya no existe.")
        new_qty = lot.quantity_available - qty
        if new_qty < 0:
            raise ValidationError(
                f"Stock insuficiente en el lote {lot.lot_number or lot_id}."
            )
        inventory_repository.adjust_lot_quantity(conn, lot_id, new_qty)
        inventory_repository.insert_movement(
            conn,
            product_id=product_id,
            lot_id=lot_id,
            movement_type="SALE",
            quantity=qty,
            reference_type="SALE",
            reference_id=sale_id,
            performed_by=current.id,
            notes=f"Venta {invoice}",
        )

    logger.info("Venta completada: id=%s invoice=%s total=%s", sale_id, invoice, total)
    return sale_id


def _allocate_fifo(
    conn: oracledb.Connection,
    product_id: int,
    quantity: Decimal,
    product_name: str,
) -> list[tuple[int, Decimal]]:
    """Asigna cantidad a lotes con stock, FIFO por vencimiento / recepción."""
    lots = inventory_repository.list_lots_for_product(
        conn, product_id, available_only=True
    )
    remaining = quantity
    chunks: list[tuple[int, Decimal]] = []
    for lot in lots:
        if remaining <= 0:
            break
        take = min(lot.quantity_available, remaining)
        if take <= 0:
            continue
        chunks.append((lot.id, _money(take)))
        remaining = _money(remaining - take)
    if remaining > 0:
        raise ValidationError(
            f"Stock insuficiente de «{product_name}» "
            f"(faltan {remaining})."
        )
    return chunks
