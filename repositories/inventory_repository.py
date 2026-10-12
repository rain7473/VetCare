"""Repository de inventario: categorías, productos, proveedores, lotes y movimientos."""

from datetime import date, datetime
from decimal import Decimal

import oracledb

from models.inventory import (
    InventoryLot,
    Product,
    ProductCategory,
    StockMovement,
    Supplier,
)

MOVEMENT_TYPES = frozenset(
    {
        "ENTRY",
        "SALE",
        "ADJUSTMENT_IN",
        "ADJUSTMENT_OUT",
        "EXPIRED",
        "RETURN_IN",
        "RETURN_OUT",
    }
)

_INBOUND = frozenset({"ENTRY", "ADJUSTMENT_IN", "RETURN_IN"})
_OUTBOUND = frozenset({"SALE", "ADJUSTMENT_OUT", "EXPIRED", "RETURN_OUT"})


def _as_int(value) -> int:
    raw = value.getvalue() if hasattr(value, "getvalue") else value
    return int(raw[0] if isinstance(raw, (list, tuple)) else raw)


def _dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Categorías
# ---------------------------------------------------------------------------


def list_categories(
    conn: oracledb.Connection, *, active_only: bool = False
) -> list[ProductCategory]:
    sql = """
        SELECT id, name, description, is_active
        FROM product_categories
    """
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY name"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [
            ProductCategory(
                id=row[0],
                name=row[1],
                description=row[2],
                is_active=bool(row[3]),
            )
            for row in cur.fetchall()
        ]


def insert_category(
    conn: oracledb.Connection, *, name: str, description: str | None
) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO product_categories (name, description, is_active)
            VALUES (:name, :description, 1)
            RETURNING id INTO :new_id
            """,
            {"name": name, "description": description, "new_id": new_id},
        )
        return _as_int(new_id)


def set_category_active(
    conn: oracledb.Connection, category_id: int, is_active: bool
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE product_categories
            SET is_active = :active
            WHERE id = :id
            """,
            {"active": 1 if is_active else 0, "id": category_id},
        )


# ---------------------------------------------------------------------------
# Proveedores
# ---------------------------------------------------------------------------

_SUPPLIER_SELECT = """
    SELECT id, name, tax_id, contact_name, phone, email, address,
           is_active, created_at, updated_at
    FROM suppliers
"""


def _row_to_supplier(row: tuple) -> Supplier:
    return Supplier(
        id=row[0],
        name=row[1],
        tax_id=row[2],
        contact_name=row[3],
        phone=row[4],
        email=row[5],
        address=row[6],
        is_active=bool(row[7]),
        created_at=row[8],
        updated_at=row[9],
    )


def list_suppliers(
    conn: oracledb.Connection, *, active_only: bool = False
) -> list[Supplier]:
    sql = _SUPPLIER_SELECT
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY name"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [_row_to_supplier(row) for row in cur.fetchall()]


def get_supplier(conn: oracledb.Connection, supplier_id: int) -> Supplier | None:
    with conn.cursor() as cur:
        cur.execute(_SUPPLIER_SELECT + " WHERE id = :id", {"id": supplier_id})
        row = cur.fetchone()
    return _row_to_supplier(row) if row else None


def insert_supplier(
    conn: oracledb.Connection,
    *,
    name: str,
    tax_id: str | None,
    contact_name: str | None,
    phone: str | None,
    email: str | None,
    address: str | None,
) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO suppliers (
                name, tax_id, contact_name, phone, email, address,
                is_active, created_at, updated_at
            ) VALUES (
                :name, :tax_id, :contact_name, :phone, :email, :address,
                1, SYSTIMESTAMP, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "name": name,
                "tax_id": tax_id,
                "contact_name": contact_name,
                "phone": phone,
                "email": email,
                "address": address,
                "new_id": new_id,
            },
        )
        return _as_int(new_id)


def update_supplier(
    conn: oracledb.Connection,
    supplier_id: int,
    *,
    name: str,
    tax_id: str | None,
    contact_name: str | None,
    phone: str | None,
    email: str | None,
    address: str | None,
    is_active: bool,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE suppliers
            SET name = :name,
                tax_id = :tax_id,
                contact_name = :contact_name,
                phone = :phone,
                email = :email,
                address = :address,
                is_active = :is_active,
                updated_at = SYSTIMESTAMP
            WHERE id = :id
            """,
            {
                "id": supplier_id,
                "name": name,
                "tax_id": tax_id,
                "contact_name": contact_name,
                "phone": phone,
                "email": email,
                "address": address,
                "is_active": 1 if is_active else 0,
            },
        )


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------

_PRODUCT_SELECT = """
    SELECT p.id, p.category_id, p.name, p.sku, p.barcode, p.description,
           p.unit, p.sale_price, p.minimum_stock, p.location,
           p.requires_lot, p.requires_expiry, p.is_active,
           c.name AS category_name,
           NVL((
               SELECT SUM(l.quantity_available)
               FROM inventory_lots l
               WHERE l.product_id = p.id
           ), 0) AS stock_available,
           p.created_at, p.updated_at
    FROM products p
    LEFT JOIN product_categories c ON c.id = p.category_id
"""


def _row_to_product(row: tuple) -> Product:
    return Product(
        id=row[0],
        category_id=row[1],
        name=row[2],
        sku=row[3],
        barcode=row[4],
        description=row[5],
        unit=row[6],
        sale_price=_dec(row[7]),
        minimum_stock=_dec(row[8]),
        location=row[9],
        requires_lot=bool(row[10]),
        requires_expiry=bool(row[11]),
        is_active=bool(row[12]),
        category_name=row[13],
        stock_available=_dec(row[14]),
        created_at=row[15],
        updated_at=row[16],
    )


def list_products(
    conn: oracledb.Connection, *, active_only: bool = False
) -> list[Product]:
    sql = _PRODUCT_SELECT
    if active_only:
        sql += " WHERE p.is_active = 1"
    sql += " ORDER BY p.name"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [_row_to_product(row) for row in cur.fetchall()]


def get_product(conn: oracledb.Connection, product_id: int) -> Product | None:
    with conn.cursor() as cur:
        cur.execute(_PRODUCT_SELECT + " WHERE p.id = :id", {"id": product_id})
        row = cur.fetchone()
    return _row_to_product(row) if row else None


def find_by_barcode(conn: oracledb.Connection, barcode: str) -> Product | None:
    with conn.cursor() as cur:
        cur.execute(
            _PRODUCT_SELECT + " WHERE p.barcode = :barcode",
            {"barcode": barcode},
        )
        row = cur.fetchone()
    return _row_to_product(row) if row else None


def sku_exists(
    conn: oracledb.Connection, sku: str, exclude_id: int | None = None
) -> bool:
    sql = "SELECT COUNT(*) FROM products WHERE LOWER(sku) = :sku"
    params: dict = {"sku": sku.lower()}
    if exclude_id is not None:
        sql += " AND id != :exclude_id"
        params["exclude_id"] = exclude_id
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0] > 0


def barcode_exists(
    conn: oracledb.Connection, barcode: str, exclude_id: int | None = None
) -> bool:
    sql = "SELECT COUNT(*) FROM products WHERE barcode = :barcode"
    params: dict = {"barcode": barcode}
    if exclude_id is not None:
        sql += " AND id != :exclude_id"
        params["exclude_id"] = exclude_id
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0] > 0


def insert_product(
    conn: oracledb.Connection,
    *,
    category_id: int | None,
    name: str,
    sku: str | None,
    barcode: str | None,
    description: str | None,
    unit: str,
    sale_price: Decimal,
    minimum_stock: Decimal,
    location: str | None,
    requires_lot: bool,
    requires_expiry: bool,
) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO products (
                category_id, name, sku, barcode, description, unit,
                sale_price, minimum_stock, location,
                requires_lot, requires_expiry, is_active,
                created_at, updated_at
            ) VALUES (
                :category_id, :name, :sku, :barcode, :description, :unit,
                :sale_price, :minimum_stock, :location,
                :requires_lot, :requires_expiry, 1,
                SYSTIMESTAMP, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "category_id": category_id,
                "name": name,
                "sku": sku,
                "barcode": barcode,
                "description": description,
                "unit": unit,
                "sale_price": float(sale_price),
                "minimum_stock": float(minimum_stock),
                "location": location,
                "requires_lot": 1 if requires_lot else 0,
                "requires_expiry": 1 if requires_expiry else 0,
                "new_id": new_id,
            },
        )
        return _as_int(new_id)


def update_product(
    conn: oracledb.Connection,
    product_id: int,
    *,
    category_id: int | None,
    name: str,
    sku: str | None,
    barcode: str | None,
    description: str | None,
    unit: str,
    sale_price: Decimal,
    minimum_stock: Decimal,
    location: str | None,
    requires_lot: bool,
    requires_expiry: bool,
    is_active: bool,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE products
            SET category_id = :category_id,
                name = :name,
                sku = :sku,
                barcode = :barcode,
                description = :description,
                unit = :unit,
                sale_price = :sale_price,
                minimum_stock = :minimum_stock,
                location = :location,
                requires_lot = :requires_lot,
                requires_expiry = :requires_expiry,
                is_active = :is_active,
                updated_at = SYSTIMESTAMP
            WHERE id = :id
            """,
            {
                "id": product_id,
                "category_id": category_id,
                "name": name,
                "sku": sku,
                "barcode": barcode,
                "description": description,
                "unit": unit,
                "sale_price": float(sale_price),
                "minimum_stock": float(minimum_stock),
                "location": location,
                "requires_lot": 1 if requires_lot else 0,
                "requires_expiry": 1 if requires_expiry else 0,
                "is_active": 1 if is_active else 0,
            },
        )


# ---------------------------------------------------------------------------
# Lotes
# ---------------------------------------------------------------------------

_LOT_SELECT = """
    SELECT l.id, l.product_id, l.supplier_id, l.lot_number, l.expiry_date,
           l.unit_cost, l.quantity_received, l.quantity_available,
           l.received_at, l.notes,
           p.name AS product_name,
           s.name AS supplier_name
    FROM inventory_lots l
    JOIN products p ON p.id = l.product_id
    LEFT JOIN suppliers s ON s.id = l.supplier_id
"""


def _row_to_lot(row: tuple) -> InventoryLot:
    return InventoryLot(
        id=row[0],
        product_id=row[1],
        supplier_id=row[2],
        lot_number=row[3],
        expiry_date=row[4].date() if isinstance(row[4], datetime) else row[4],
        unit_cost=_dec(row[5]),
        quantity_received=_dec(row[6]),
        quantity_available=_dec(row[7]),
        received_at=row[8],
        notes=row[9],
        product_name=row[10],
        supplier_name=row[11],
    )


def list_lots_for_product(
    conn: oracledb.Connection, product_id: int, *, available_only: bool = False
) -> list[InventoryLot]:
    sql = _LOT_SELECT + " WHERE l.product_id = :product_id"
    if available_only:
        sql += " AND l.quantity_available > 0"
    sql += " ORDER BY l.expiry_date NULLS LAST, l.received_at"
    with conn.cursor() as cur:
        cur.execute(sql, {"product_id": product_id})
        return [_row_to_lot(row) for row in cur.fetchall()]


def get_lot(conn: oracledb.Connection, lot_id: int) -> InventoryLot | None:
    with conn.cursor() as cur:
        cur.execute(_LOT_SELECT + " WHERE l.id = :id", {"id": lot_id})
        row = cur.fetchone()
    return _row_to_lot(row) if row else None


def list_expiring_lots(
    conn: oracledb.Connection, until: date
) -> list[InventoryLot]:
    with conn.cursor() as cur:
        cur.execute(
            _LOT_SELECT
            + """
            WHERE l.quantity_available > 0
              AND l.expiry_date IS NOT NULL
              AND l.expiry_date <= :until
            ORDER BY l.expiry_date
            """,
            {"until": until},
        )
        return [_row_to_lot(row) for row in cur.fetchall()]


def insert_lot(
    conn: oracledb.Connection,
    *,
    product_id: int,
    supplier_id: int | None,
    lot_number: str | None,
    expiry_date: date | None,
    unit_cost: Decimal,
    quantity_received: Decimal,
    notes: str | None,
) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO inventory_lots (
                product_id, supplier_id, lot_number, expiry_date,
                unit_cost, quantity_received, quantity_available,
                received_at, notes
            ) VALUES (
                :product_id, :supplier_id, :lot_number, :expiry_date,
                :unit_cost, :qty, :qty, SYSTIMESTAMP, :notes
            )
            RETURNING id INTO :new_id
            """,
            {
                "product_id": product_id,
                "supplier_id": supplier_id,
                "lot_number": lot_number,
                "expiry_date": expiry_date,
                "unit_cost": float(unit_cost),
                "qty": float(quantity_received),
                "notes": notes,
                "new_id": new_id,
            },
        )
        return _as_int(new_id)


def adjust_lot_quantity(
    conn: oracledb.Connection, lot_id: int, new_available: Decimal
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE inventory_lots
            SET quantity_available = :qty
            WHERE id = :id
            """,
            {"id": lot_id, "qty": float(new_available)},
        )


# ---------------------------------------------------------------------------
# Movimientos
# ---------------------------------------------------------------------------

_MOVEMENT_SELECT = """
    SELECT m.id, m.product_id, m.lot_id, m.movement_type, m.quantity,
           m.reference_type, m.reference_id, m.performed_by, m.notes,
           m.created_at,
           p.name AS product_name,
           l.lot_number,
           u.full_name AS performed_by_name
    FROM stock_movements m
    JOIN products p ON p.id = m.product_id
    LEFT JOIN inventory_lots l ON l.id = m.lot_id
    LEFT JOIN users u ON u.id = m.performed_by
"""


def _row_to_movement(row: tuple) -> StockMovement:
    return StockMovement(
        id=row[0],
        product_id=row[1],
        lot_id=row[2],
        movement_type=row[3],
        quantity=_dec(row[4]),
        reference_type=row[5],
        reference_id=row[6],
        performed_by=row[7],
        notes=row[8],
        created_at=row[9],
        product_name=row[10],
        lot_number=row[11],
        performed_by_name=row[12],
    )


def list_movements(
    conn: oracledb.Connection,
    *,
    product_id: int | None = None,
    limit: int = 200,
) -> list[StockMovement]:
    sql = _MOVEMENT_SELECT
    params: dict = {"lim": limit}
    if product_id is not None:
        sql += " WHERE m.product_id = :product_id"
        params["product_id"] = product_id
    sql += " ORDER BY m.created_at DESC FETCH FIRST :lim ROWS ONLY"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_movement(row) for row in cur.fetchall()]


def insert_movement(
    conn: oracledb.Connection,
    *,
    product_id: int,
    lot_id: int | None,
    movement_type: str,
    quantity: Decimal,
    reference_type: str | None,
    reference_id: int | None,
    performed_by: int | None,
    notes: str | None,
) -> int:
    if movement_type not in MOVEMENT_TYPES:
        raise ValueError(f"Tipo de movimiento inválido: {movement_type}")
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO stock_movements (
                product_id, lot_id, movement_type, quantity,
                reference_type, reference_id, performed_by, notes, created_at
            ) VALUES (
                :product_id, :lot_id, :movement_type, :quantity,
                :reference_type, :reference_id, :performed_by, :notes,
                SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "product_id": product_id,
                "lot_id": lot_id,
                "movement_type": movement_type,
                "quantity": float(quantity),
                "reference_type": reference_type,
                "reference_id": reference_id,
                "performed_by": performed_by,
                "notes": notes,
                "new_id": new_id,
            },
        )
        return _as_int(new_id)


def is_inbound(movement_type: str) -> bool:
    return movement_type in _INBOUND


def is_outbound(movement_type: str) -> bool:
    return movement_type in _OUTBOUND
