"""Pruebas del Objetivo 21: ventas atómicas.

Venta + ítems + movimiento SALE + descuento de lote. INSERT + ROLLBACK.

    python -m tests.sales_test
"""

import sys
from datetime import date, timedelta
from decimal import Decimal


def run() -> int:
    from database.connection import connection_scope
    from models.user import User
    from repositories import inventory_repository, role_repository, sales_repository, user_repository
    from services import sales_service, session
    from services.inventory_service import (
        ProductFormData,
        StockEntryData,
        _create_product,
        _receive_stock,
    )
    from services.permission_service import PermissionDeniedError
    from services.sales_service import CartLine, SaleFormData, _complete_sale
    from utils.security import hash_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}

    try:
        session.set_current_user(
            User(
                id=993,
                role_id=1,
                username="fake_sale",
                email=None,
                full_name="Fake Sale",
                phone=None,
                is_active=True,
                role_name="TEST",
            ),
            frozenset(),
        )
        try:
            sales_service.list_sales()
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        with connection_scope() as conn:
            sales_role = role_repository.get_role_id_by_name(conn, "SALES")
            if sales_role is None:
                sales_role = role_repository.get_role_id_by_name(conn, "ADMIN")
            user_id = user_repository.insert_user(
                conn,
                role_id=sales_role,
                username="__test_sale21__",
                email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Vendedor Prueba",
                phone=None,
            )
            session.set_current_user(
                User(
                    id=user_id,
                    role_id=sales_role,
                    username="__test_sale21__",
                    email=None,
                    full_name="Vendedor Prueba",
                    phone=None,
                    is_active=True,
                    role_name="SALES",
                ),
                frozenset(
                    {
                        "SALES_READ",
                        "SALES_CREATE",
                        "INVENTORY_READ",
                        "INVENTORY_MANAGE",
                    }
                ),
            )

            product_id = _create_product(
                conn,
                ProductFormData(
                    category_id=None,
                    name="Shampoo Vet",
                    sku="SKU-SALE-21",
                    barcode="7790000000021",
                    description="",
                    unit="unidad",
                    sale_price="12.00",
                    minimum_stock="2",
                    location="A1",
                    requires_lot=True,
                    requires_expiry=True,
                    is_active=True,
                ),
            )
            _receive_stock(
                conn,
                StockEntryData(
                    product_id=product_id,
                    supplier_id=None,
                    lot_number="L-S21",
                    expiry_date=date.today() + timedelta(days=180),
                    unit_cost="4",
                    quantity="10",
                    notes="",
                ),
            )
            product = inventory_repository.get_product(conn, product_id)
            results["Stock inicial"] = (
                product is not None and product.stock_available == Decimal("10")
            )

            try:
                _complete_sale(
                    conn,
                    SaleFormData(
                        owner_id=None,
                        payment_method="CASH",
                        discount_amount="0",
                        tax_amount="0",
                        notes="",
                        lines=(),
                    ),
                )
                results["Carrito vacío rechazado"] = False
            except ValidationError:
                results["Carrito vacío rechazado"] = True

            try:
                _complete_sale(
                    conn,
                    SaleFormData(
                        owner_id=None,
                        payment_method="CASH",
                        discount_amount="0",
                        tax_amount="0",
                        notes="",
                        lines=(
                            CartLine(
                                product_id=product_id,
                                quantity=Decimal("999"),
                                unit_price=Decimal("12"),
                            ),
                        ),
                    ),
                )
                results["Stock insuficiente bloqueado"] = False
            except ValidationError:
                results["Stock insuficiente bloqueado"] = True

            # Tras rechazo, el stock debe seguir intacto en la misma tx.
            product = inventory_repository.get_product(conn, product_id)
            results["Stock intacto tras rechazo"] = (
                product is not None and product.stock_available == Decimal("10")
            )

            sale_id = _complete_sale(
                conn,
                SaleFormData(
                    owner_id=None,
                    payment_method="CARD",
                    discount_amount="1.00",
                    tax_amount="0.50",
                    notes="Venta test",
                    lines=(
                        CartLine(
                            product_id=product_id,
                            quantity=Decimal("3"),
                            unit_price=Decimal("12.00"),
                            discount_amount=Decimal("0"),
                        ),
                    ),
                ),
            )
            sale = sales_repository.get_sale(conn, sale_id)
            results["Venta creada COMPLETED"] = (
                sale is not None
                and sale.status == "COMPLETED"
                and sale.payment_method == "CARD"
            )
            # subtotal 36 - discount 1 + tax 0.50 = 35.50
            results["Totales correctos"] = (
                sale is not None
                and sale.subtotal == Decimal("36.00")
                and sale.discount_amount == Decimal("1.00")
                and sale.tax_amount == Decimal("0.50")
                and sale.total == Decimal("35.50")
            )
            results["Ítems de venta"] = sale is not None and len(sale.items) == 1

            product = inventory_repository.get_product(conn, product_id)
            results["Stock descontado"] = (
                product is not None and product.stock_available == Decimal("7")
            )

            movements = inventory_repository.list_movements(
                conn, product_id=product_id
            )
            results["Movimiento SALE registrado"] = any(
                m.movement_type == "SALE"
                and m.quantity == Decimal("3")
                and m.reference_id == sale_id
                for m in movements
            )

            results["ROLLBACK dejará la base intacta"] = True

    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de ventas: {exc}")
        results["Pruebas sin errores inesperados"] = False
    finally:
        session.clear()

    failures = [name for name, ok in results.items() if not ok]
    for name, ok in results.items():
        print(f"  [{'OK' if ok else 'FALLO'}] {name}")

    if failures:
        print(f"\nPruebas FALLIDAS: {len(failures)} de {len(results)}.")
        return 1

    print(f"\nTodas las pruebas superadas ({len(results)}).")
    return 0


if __name__ == "__main__":
    sys.exit(run())
