"""Repository de ventas (SALES / SALE_ITEMS) y descuento de stock asociado."""

from datetime import datetime
from decimal import Decimal

import oracledb

from models.sale import Sale, SaleItem


def _as_int(value) -> int:
    raw = value.getvalue() if hasattr(value, "getvalue") else value
    return int(raw[0] if isinstance(raw, (list, tuple)) else raw)


def _dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


_SALE_SELECT = """
    SELECT s.id, s.invoice_number, s.owner_id, s.sold_by,
           s.subtotal, s.discount_amount, s.tax_amount, s.total,
           s.payment_method, s.status, s.notes, s.sold_at,
           CASE
               WHEN o.id IS NULL THEN NULL
               ELSE o.first_name || ' ' || o.last_name
           END AS owner_name,
           u.full_name AS sold_by_name
    FROM sales s
    LEFT JOIN owners o ON o.id = s.owner_id
    JOIN users u ON u.id = s.sold_by
"""


def _row_to_sale(row: tuple, items: tuple[SaleItem, ...] = ()) -> Sale:
    return Sale(
        id=row[0],
        invoice_number=row[1],
        owner_id=row[2],
        sold_by=row[3],
        subtotal=_dec(row[4]),
        discount_amount=_dec(row[5]),
        tax_amount=_dec(row[6]),
        total=_dec(row[7]),
        payment_method=row[8],
        status=row[9],
        notes=row[10],
        sold_at=row[11],
        owner_name=row[12],
        sold_by_name=row[13],
        items=items,
    )


_ITEM_SELECT = """
    SELECT i.id, i.sale_id, i.product_id, i.lot_id, i.quantity,
           i.unit_price, i.discount_amount, i.line_total,
           p.name AS product_name,
           l.lot_number
    FROM sale_items i
    JOIN products p ON p.id = i.product_id
    LEFT JOIN inventory_lots l ON l.id = i.lot_id
    WHERE i.sale_id = :sale_id
    ORDER BY i.id
"""


def _row_to_item(row: tuple) -> SaleItem:
    return SaleItem(
        id=row[0],
        sale_id=row[1],
        product_id=row[2],
        lot_id=row[3],
        quantity=_dec(row[4]),
        unit_price=_dec(row[5]),
        discount_amount=_dec(row[6]),
        line_total=_dec(row[7]) if row[7] is not None else None,
        product_name=row[8],
        lot_number=row[9],
    )


def list_sales(
    conn: oracledb.Connection, *, limit: int = 200, sold_by: int | None = None
) -> list[Sale]:
    sql = _SALE_SELECT
    params = {"lim": limit}
    if sold_by is not None:
        sql += " WHERE s.sold_by = :sold_by"
        params["sold_by"] = sold_by
    sql += " ORDER BY s.sold_at DESC, s.id DESC FETCH FIRST :lim ROWS ONLY"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_sale(row) for row in cur.fetchall()]


def get_sale(conn: oracledb.Connection, sale_id: int) -> Sale | None:
    with conn.cursor() as cur:
        cur.execute(_SALE_SELECT + " WHERE s.id = :id", {"id": sale_id})
        row = cur.fetchone()
    if row is None:
        return None
    items = list_items(conn, sale_id)
    return _row_to_sale(row, tuple(items))


def list_items(conn: oracledb.Connection, sale_id: int) -> list[SaleItem]:
    with conn.cursor() as cur:
        cur.execute(_ITEM_SELECT, {"sale_id": sale_id})
        return [_row_to_item(row) for row in cur.fetchall()]


def next_invoice_number(conn: oracledb.Connection, when: datetime) -> str:
    """Genera un número único VC-YYYYMMDD-NNNN dentro de la transacción."""
    prefix = f"VC-{when.strftime('%Y%m%d')}-"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT NVL(MAX(TO_NUMBER(SUBSTR(invoice_number, :start_pos))), 0)
            FROM sales
            WHERE invoice_number LIKE :prefix
            """,
            {"start_pos": len(prefix) + 1, "prefix": prefix + "%"},
        )
        last = int(cur.fetchone()[0] or 0)
    return f"{prefix}{last + 1:04d}"


def insert_sale(
    conn: oracledb.Connection,
    *,
    invoice_number: str,
    owner_id: int | None,
    sold_by: int,
    subtotal: Decimal,
    discount_amount: Decimal,
    tax_amount: Decimal,
    total: Decimal,
    payment_method: str,
    status: str,
    notes: str | None,
) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO sales (
                invoice_number, owner_id, sold_by,
                subtotal, discount_amount, tax_amount, total,
                payment_method, status, notes, sold_at
            ) VALUES (
                :invoice_number, :owner_id, :sold_by,
                :subtotal, :discount_amount, :tax_amount, :total,
                :payment_method, :status, :notes, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "invoice_number": invoice_number,
                "owner_id": owner_id,
                "sold_by": sold_by,
                "subtotal": float(subtotal),
                "discount_amount": float(discount_amount),
                "tax_amount": float(tax_amount),
                "total": float(total),
                "payment_method": payment_method,
                "status": status,
                "notes": notes,
                "new_id": new_id,
            },
        )
        return _as_int(new_id)


def insert_sale_item(
    conn: oracledb.Connection,
    *,
    sale_id: int,
    product_id: int,
    lot_id: int | None,
    quantity: Decimal,
    unit_price: Decimal,
    discount_amount: Decimal,
    line_total: Decimal | None = None,
) -> int:
    # LINE_TOTAL es columna virtual en Oracle: no se inserta.
    _ = line_total
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO sale_items (
                sale_id, product_id, lot_id, quantity,
                unit_price, discount_amount
            ) VALUES (
                :sale_id, :product_id, :lot_id, :quantity,
                :unit_price, :discount_amount
            )
            RETURNING id INTO :new_id
            """,
            {
                "sale_id": sale_id,
                "product_id": product_id,
                "lot_id": lot_id,
                "quantity": float(quantity),
                "unit_price": float(unit_price),
                "discount_amount": float(discount_amount),
                "new_id": new_id,
            },
        )
        return _as_int(new_id)
