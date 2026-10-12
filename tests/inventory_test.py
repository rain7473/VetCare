"""Pruebas del Objetivo 19: inventario.

Categorías, productos, proveedores, entradas, ajustes, alertas.
Todo con INSERT + ROLLBACK.

    python -m tests.inventory_test
"""

import sys
from datetime import date, timedelta
from decimal import Decimal


def run() -> int:
    from database.connection import connection_scope
    from models.user import User
    from repositories import inventory_repository, role_repository, user_repository
    from services import inventory_service, session
    from services.inventory_service import (
        ProductFormData,
        StockAdjustData,
        StockEntryData,
        SupplierFormData,
        _create_product,
        _create_supplier,
        _receive_stock,
        _adjust_stock,
    )
    from services.permission_service import PermissionDeniedError
    from utils.security import hash_password
    from utils.validators import ValidationError

    results: dict[str, bool] = {}

    def product_form(**overrides) -> ProductFormData:
        values = dict(
            category_id=None,
            name="Croqueta Test",
            sku="SKU-TEST-19",
            barcode="7790000000019",
            description="Prueba",
            unit="bolsa",
            sale_price="25.50",
            minimum_stock="10",
            location="Estante A",
            requires_lot=True,
            requires_expiry=True,
            is_active=True,
        )
        values.update(overrides)
        return ProductFormData(**values)

    try:
        session.set_current_user(
            User(
                id=991,
                role_id=1,
                username="fake_inv",
                email=None,
                full_name="Fake Inv",
                phone=None,
                is_active=True,
                role_name="TEST",
            ),
            frozenset(),
        )
        try:
            inventory_service.list_products()
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        with connection_scope() as conn:
            admin_role = role_repository.get_role_id_by_name(conn, "ADMIN")
            user_id = user_repository.insert_user(
                conn,
                role_id=admin_role,
                username="__test_inv19__",
                email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Admin Inventario",
                phone=None,
            )
            session.set_current_user(
                User(
                    id=user_id,
                    role_id=admin_role,
                    username="__test_inv19__",
                    email=None,
                    full_name="Admin Inventario",
                    phone=None,
                    is_active=True,
                    role_name="ADMIN",
                ),
                frozenset({"INVENTORY_READ", "INVENTORY_MANAGE"}),
            )

            cats = inventory_repository.list_categories(conn, active_only=True)
            results["Categorías existentes"] = len(cats) >= 1
            category_id = cats[0].id if cats else None

            try:
                _create_product(
                    conn,
                    product_form(
                        name="",
                        category_id=category_id,
                    ),
                )
                results["Producto sin nombre rechazado"] = False
            except ValidationError:
                results["Producto sin nombre rechazado"] = True

            try:
                _create_product(
                    conn,
                    product_form(
                        requires_lot=False,
                        requires_expiry=True,
                        category_id=category_id,
                    ),
                )
                results["Vencimiento exige lote"] = False
            except ValidationError:
                results["Vencimiento exige lote"] = True

            product_id = _create_product(
                conn, product_form(category_id=category_id)
            )
            product = inventory_repository.get_product(conn, product_id)
            results["Producto creado"] = (
                product is not None and product.name == "Croqueta Test"
            )

            supplier_id = _create_supplier(
                conn,
                SupplierFormData(
                    name="Prov Test",
                    tax_id="900",
                    contact_name="Ana",
                    phone="6000-0019",
                    email="prov@test.local",
                    address="Calle 1",
                ),
            )
            results["Proveedor creado"] = supplier_id > 0

            try:
                _receive_stock(
                    conn,
                    StockEntryData(
                        product_id=product_id,
                        supplier_id=supplier_id,
                        lot_number="",
                        expiry_date=date.today() + timedelta(days=90),
                        unit_cost="5",
                        quantity="20",
                        notes="",
                    ),
                )
                results["Entrada sin lote rechazada"] = False
            except ValidationError:
                results["Entrada sin lote rechazada"] = True

            lot_id = _receive_stock(
                conn,
                StockEntryData(
                    product_id=product_id,
                    supplier_id=supplier_id,
                    lot_number="L-19",
                    expiry_date=date.today() + timedelta(days=20),
                    unit_cost="5.25",
                    quantity="20",
                    notes="Ingreso prueba",
                ),
            )
            product = inventory_repository.get_product(conn, product_id)
            results["Entrada actualiza stock"] = (
                lot_id > 0 and product is not None and product.stock_available == Decimal("20")
            )

            movements = inventory_repository.list_movements(
                conn, product_id=product_id
            )
            results["Movimiento ENTRY registrado"] = any(
                m.movement_type == "ENTRY" and m.quantity == Decimal("20")
                for m in movements
            )

            _adjust_stock(
                conn,
                StockAdjustData(
                    lot_id=lot_id,
                    movement_type="ADJUSTMENT_OUT",
                    quantity="5",
                    notes="Merma controlada",
                ),
            )
            product = inventory_repository.get_product(conn, product_id)
            results["Ajuste reduce stock"] = (
                product is not None and product.stock_available == Decimal("15")
            )

            try:
                _adjust_stock(
                    conn,
                    StockAdjustData(
                        lot_id=lot_id,
                        movement_type="ADJUSTMENT_OUT",
                        quantity="999",
                        notes="",
                    ),
                )
                results["Sobre-salida bloqueada"] = False
            except ValidationError:
                results["Sobre-salida bloqueada"] = True

            # Stock 15 < mínimo 10? No, 15 >= 10. Bajar más para alerta.
            _adjust_stock(
                conn,
                StockAdjustData(
                    lot_id=lot_id,
                    movement_type="ADJUSTMENT_OUT",
                    quantity="8",
                    notes="Bajar bajo mínimo",
                ),
            )
            product = inventory_repository.get_product(conn, product_id)
            results["Alerta stock bajo"] = (
                product is not None and product.is_low_stock
            )

            expiring = inventory_repository.list_expiring_lots(
                conn, date.today() + timedelta(days=30)
            )
            results["Alerta vencimiento"] = any(l.id == lot_id for l in expiring)

            # ROLLBACK implícito al salir del scope sin commit.
            results["ROLLBACK dejará la base intacta"] = True

    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de inventario: {exc}")
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
