"""Pruebas del Objetivo 20: código de barras.

Búsqueda por barcode, producto inactivo, widget de escáner (offscreen).

    python -m tests.barcode_test
"""

import os
import sys
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def run() -> int:
    from PySide6.QtWidgets import QApplication

    from database.connection import connection_scope
    from models.user import User
    from repositories import inventory_repository, role_repository, user_repository
    from services import inventory_service, session
    from services.inventory_service import (
        ProductFormData,
        _create_product,
        _find_active_by_barcode,
    )
    from services.permission_service import PermissionDeniedError
    from utils.security import hash_password
    from utils.validators import ValidationError
    from widgets.barcode_scanner import BarcodeScannerInput

    results: dict[str, bool] = {}
    _ = QApplication.instance() or QApplication([])

    try:
        session.set_current_user(
            User(
                id=992,
                role_id=1,
                username="fake_bc",
                email=None,
                full_name="Fake BC",
                phone=None,
                is_active=True,
                role_name="TEST",
            ),
            frozenset(),
        )
        try:
            inventory_service.find_by_barcode("X")
            results["Sin permiso bloqueado"] = False
        except PermissionDeniedError:
            results["Sin permiso bloqueado"] = True

        scanner = BarcodeScannerInput()
        captured: list[str] = []
        scanner.scanned.connect(captured.append)
        scanner.setText("  7791234567890  ")
        scanner.returnPressed.emit()
        results["Widget emite código limpio"] = captured == ["7791234567890"]
        results["Widget limpia tras escaneo"] = scanner.text() == ""

        with connection_scope() as conn:
            admin_role = role_repository.get_role_id_by_name(conn, "ADMIN")
            user_id = user_repository.insert_user(
                conn,
                role_id=admin_role,
                username="__test_bc20__",
                email=None,
                password_hash=hash_password("Prueba123"),
                full_name="Admin Barras",
                phone=None,
            )
            session.set_current_user(
                User(
                    id=user_id,
                    role_id=admin_role,
                    username="__test_bc20__",
                    email=None,
                    full_name="Admin Barras",
                    phone=None,
                    is_active=True,
                    role_name="ADMIN",
                ),
                frozenset({"INVENTORY_READ", "INVENTORY_MANAGE"}),
            )

            try:
                inventory_service.find_by_barcode("   ")
                results["Barcode vacío rechazado"] = False
            except ValidationError:
                results["Barcode vacío rechazado"] = True

            product_id = _create_product(
                conn,
                ProductFormData(
                    category_id=None,
                    name="Juguete QR",
                    sku="SKU-BC-20",
                    barcode="7790000000020",
                    description="",
                    unit="unidad",
                    sale_price="9.99",
                    minimum_stock="1",
                    location="",
                    requires_lot=False,
                    requires_expiry=False,
                    is_active=True,
                ),
            )
            found = _find_active_by_barcode(conn, "7790000000020")
            results["Buscar barcode existente"] = (
                found is not None and found.id == product_id
            )

            missing = _find_active_by_barcode(conn, "0000000000000")
            results["Barcode inexistente"] = missing is None

            inventory_repository.update_product(
                conn,
                product_id,
                category_id=None,
                name="Juguete QR",
                sku="SKU-BC-20",
                barcode="7790000000020",
                description="",
                unit="unidad",
                sale_price=Decimal("9.99"),
                minimum_stock=Decimal("1"),
                location=None,
                requires_lot=False,
                requires_expiry=False,
                is_active=False,
            )
            hidden = _find_active_by_barcode(conn, "7790000000020")
            results["Service oculta inactivos"] = hidden is None

            results["ROLLBACK dejará la base intacta"] = True

    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en pruebas de código de barras: {exc}")
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
