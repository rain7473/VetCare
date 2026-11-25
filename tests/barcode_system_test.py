"""Integración Oracle + Qt + lectura independiente de etiquetas.

python -m tests.barcode_system_test
Dependencias adicionales: requirements-test.txt.
Las ventas se prueban con ROLLBACK. La prueba de reinicio crea únicamente un
producto temporal confirmado y lo elimina por ID y SKU en un bloque finally.
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pymupdf
import zxingcpp
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QPdfWriter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QVBoxLayout

from database.connection import connection_scope, get_connection, DatabaseConnectionError
from models.user import User
from repositories import inventory_repository, sales_repository
from services import inventory_service, sales_service, session
from services.inventory_service import ProductFormData, StockEntryData
from services.sales_service import CartLine, SaleFormData
from utils.barcode_label import BarcodeLabel, configure_label_page, export_label, print_label
from utils.barcodes import barcode_symbol, new_internal_code, validate_barcode
from utils.validators import ValidationError
from views.inventory.barcode_label_dialog import BarcodeLabelDialog
from views.inventory.inventory_dialogs import ProductDialog
from views.inventory.inventory_page import InventoryPage
from views.sales.sales_page import SalesPage
from widgets.barcode_scanner import BarcodeScannerInput

APP = QApplication.instance() or QApplication([])


def form(code="", **changes):
    return replace(ProductFormData(
        category_id=None, name="Producto prueba barras", sku="", barcode=code,
        description="", unit="unidad", sale_price="12.00", minimum_stock="1",
        location="A1", requires_lot=False, requires_expiry=False,
    ), **changes)


class BarcodeSystemTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_connection()
        with self.conn.cursor() as cur:
            cur.execute("SELECT id, role_id, username, full_name FROM users WHERE is_active = 1 ORDER BY id FETCH FIRST 1 ROWS ONLY")
            row = cur.fetchone()
        self.assertIsNotNone(row, "Se necesita un usuario activo para probar ventas")
        session.set_current_user(User(
            id=row[0], role_id=row[1], username=row[2], full_name=row[3], email=None,
            phone=None, is_active=True, role_name="ADMIN",
        ), frozenset({"INVENTORY_READ", "INVENTORY_MANAGE", "SALES_READ", "SALES_CREATE"}))
        self.code = new_internal_code()
        self.product_id = inventory_service._create_product(self.conn, form(self.code))
        self.lot_id = inventory_service._receive_stock(self.conn, StockEntryData(
            product_id=self.product_id, supplier_id=None, lot_number="",
            expiry_date=None, unit_cost="4", quantity="3", notes="Prueba con rollback",
        ))

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()
        session.clear()
        APP.processEvents()

    def product(self):
        return inventory_repository.get_product(self.conn, self.product_id)

    def sale_data(self, quantity="1"):
        return SaleFormData(None, "CASH", "0", "0", "", (
            CartLine(self.product_id, Decimal(quantity), Decimal("12")),
        ))

    @contextmanager
    def scope(self, *, commit=False):
        # Aísla incluso los fallos después de escribir sin confirmar fixtures.
        with self.conn.cursor() as cur:
            cur.execute("SAVEPOINT barcode_test_scope")
        try:
            yield self.conn
        except Exception:
            with self.conn.cursor() as cur:
                cur.execute("ROLLBACK TO barcode_test_scope")
            raise

    def test_manual_code_duplicates_update_and_inactive(self):
        data = form("0012345678905")
        product_id = inventory_service._create_product(self.conn, data)
        self.assertEqual(inventory_repository.find_by_barcode(self.conn, data.barcode).id, product_id)
        with self.assertRaisesRegex(ValidationError, "código de barras"):
            inventory_service._create_product(self.conn, data)
        inventory_service._save_product(self.conn, product_id, replace(data, is_active=False))
        self.assertIsNone(inventory_service._find_active_by_barcode(self.conn, data.barcode))
        with self.assertRaises(ValidationError):
            inventory_service._save_product(self.conn, self.product_id, data)

    def test_generation_and_manufacturer_not_overwritten(self):
        with patch.object(inventory_service, "connection_scope", self.scope):
            code = inventory_service.generate_barcode()
            self.assertTrue(code.startswith("VC"))
            self.assertEqual(barcode_symbol(code).name, "Code 128")
            dialog = ProductDialog(self.product())
            self.assertFalse(dialog.generate_barcode_button.isEnabled())
            dialog._generate_barcode()
            self.assertEqual(dialog.barcode_input.text(), self.code)
            dialog.barcode_input.clear()
            self.assertFalse(dialog.generate_barcode_button.isEnabled())
            dialog.close()
            dialog.deleteLater()

    def test_generate_save_and_lookup(self):
        with patch.object(inventory_service, "connection_scope", self.scope):
            dialog = ProductDialog()
            dialog.name_input.setText("Producto generado")
            dialog.unit_input.setText("unidad")
            dialog._generate_barcode()
            code = dialog.barcode_input.text()
            self.assertTrue(code.startswith("VC"))
            self.assertFalse(dialog.barcode_preview.pixmap().isNull())
            dialog._on_save()
            self.assertIsNotNone(dialog.created_id)
            self.assertEqual(inventory_service.find_by_barcode(code).id, dialog.created_id)
            dialog.close()
            dialog.deleteLater()

    def test_database_unique_constraint_translates_concurrent_duplicate(self):
        # Simula que otra conexión guardó el mismo código tras la prevalidación.
        with patch.object(inventory_service, "connection_scope", self.scope), \
             patch.object(inventory_repository, "barcode_exists", return_value=False):
            with self.assertRaisesRegex(ValidationError, "código de barras o SKU"):
                inventory_service.create_product(form(self.code))
        self.assertEqual(self.product().stock_available, 3)

    def test_concurrent_checkouts_wait_and_rollback_without_lost_stock(self):
        # Usa un producto existente de solo lectura como fixture compartido.
        # Ambas ventas hacen ROLLBACK; no quedan ventas ni auditorías de prueba.
        real = next((p for p in inventory_repository.list_products(self.conn, active_only=True)
                     if p.id != self.product_id and p.stock_available >= 1), None)
        self.assertIsNotNone(real, "Se necesita un producto existente con stock")
        data = SaleFormData(None, "CASH", "0", "0", "", (
            CartLine(real.id, Decimal("1"), real.sale_price),
        ))
        sales_service._complete_sale(self.conn, data)
        started, finished = threading.Event(), threading.Event()
        result = []
        def checkout():
            try:
                with connection_scope() as other:
                    started.set()
                    sales_service._complete_sale(other, replace(data, request_key=uuid4().hex))
                    result.append(inventory_repository.get_product(other, real.id).stock_available)
            except Exception as exc:
                result.append(exc)
            finally:
                finished.set()
        thread = threading.Thread(target=checkout, daemon=True)
        thread.start()
        try:
            self.assertTrue(started.wait(3))
            self.assertFalse(finished.wait(0.15), "La segunda venta debe esperar la primera transacción")
        finally:
            self.conn.rollback()
            thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [real.stock_available - 1])
        self.assertEqual(inventory_repository.get_product(self.conn, real.id).stock_available, real.stock_available)

    def test_usb_enter_in_product_does_not_save(self):
        with patch.object(inventory_service, "connection_scope", self.scope):
            dialog = ProductDialog()
        dialog.show()
        dialog.barcode_input.setFocus()
        with patch.object(inventory_service, "create_product") as create:
            QTest.keyClicks(dialog.barcode_input, "036000291452")
            QTest.keyClick(dialog.barcode_input, Qt.Key_Return)
            self.assertEqual(dialog.barcode_input.text(), "036000291452")
            create.assert_not_called()
        dialog.close()
        dialog.deleteLater()

    def test_scanner_consumes_enter_and_reentrant_or_empty_reads(self):
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        scanner = BarcodeScannerInput()
        layout.addWidget(scanner)
        button = QPushButton("Guardar")
        button.setDefault(True)
        layout.addWidget(button)
        captured, clicks = [], []
        button.clicked.connect(lambda: clicks.append(True))
        scanner.scanned.connect(captured.append)
        scanner.scanned.connect(lambda _: scanner._emit_scan())
        dialog.show()
        dialog.activateWindow()
        APP.processEvents()
        scanner.setFocus()
        QTest.keyClicks(scanner, "036000291452")
        QTest.keyClick(scanner, Qt.Key_Return)
        QTest.keyClick(scanner, Qt.Key_Return)
        self.assertEqual(captured, ["036000291452"])
        self.assertEqual(clicks, [])
        self.assertEqual(scanner.text(), "")
        self.assertTrue(scanner.hasFocus())
        dialog.close()

    def test_cart_scans_stock_total_and_keyboard_confirmation(self):
        page = SalesPage()
        # Solo las lecturas de catálogo se redirigen a la transacción real temporal.
        page._loaded = True
        page._products = [self.product()]
        page.sale_dialog.show()
        page.sale_dialog.activateWindow()
        APP.processEvents()
        page.scanner.setFocus()
        with patch.object(inventory_service, "connection_scope", self.scope):
            for _ in range(3):
                page.scanner.setText(self.code)
                QTest.keyClick(page.scanner, Qt.Key_Return)
            self.assertEqual(len(page._cart), 1)
            self.assertEqual(page._cart[0]["qty"], 3)
            self.assertEqual(page._cart_subtotal(), Decimal("36.00"))
            self.assertEqual(self.product().stock_available, 3)
            page.scanner.setText(self.code)
            QTest.keyClick(page.scanner, Qt.Key_Return)
            self.assertEqual(page._cart[0]["qty"], 3)
            self.assertIn("Stock insuficiente", page.scan_status.text())
            page._on_scan("NO-EXISTE")
            self.assertIn("No se encontró", page.scan_status.text())
        with patch.object(sales_service, "connection_scope", self.scope), \
             patch.object(page, "refresh_catalog"), patch.object(page, "refresh_history"):
            # La llamada reentrante simula una segunda confirmación durante la primera.
            real_complete = sales_service.complete_sale
            def reentrant(data):
                page._on_confirm()
                return real_complete(data)
            with patch.object(sales_service, "complete_sale", side_effect=reentrant) as complete:
                QTest.keyClick(page.scanner, Qt.Key_F4)
                self.assertEqual(complete.call_count, 1)
        self.assertEqual(self.product().stock_available, 0)
        self.assertEqual(page._cart, [])
        self.assertTrue(page.sale_dialog.isVisible())
        self.assertTrue(page.scanner.hasFocus())
        page.sale_dialog.close()
        page.deleteLater()

    def test_manual_cart_and_fractional_stock(self):
        page = SalesPage()
        page._products = [self.product()]
        with patch.object(page.product_selector, "current_id", return_value=self.product_id):
            page._on_add_selected()
        self.assertEqual(page._cart[0]["qty"], 1)
        page._clear_cart()
        page._add_product(replace(self.product(), stock_available=Decimal("0.5")))
        self.assertFalse(page._cart)
        page.deleteLater()

    def test_inventory_search_and_label_dialog(self):
        page = InventoryPage()
        page._products = [self.product()]
        page.search_input.setText(self.code)
        self.assertEqual(page.model.rowCount(), 1)
        page._select_product_id(self.product_id)
        self.assertEqual(page._selected_product().id, self.product_id)
        dialog = BarcodeLabelDialog(self.product())
        self.assertEqual(dialog.label.code, self.code)
        dialog.close()
        dialog.deleteLater()
        page.deleteLater()

    def test_sale_replay_no_second_stock_or_audit(self):
        data = self.sale_data("2")
        sale_id = sales_service._complete_sale(self.conn, data)
        self.assertEqual(sales_service._complete_sale(self.conn, data), sale_id)
        self.assertEqual(self.product().stock_available, 1)
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM stock_movements WHERE reference_type = 'SALE' AND reference_id = :id", {"id": sale_id})
            self.assertEqual(cur.fetchone()[0], 1)
            cur.execute("SELECT COUNT(*) FROM audit_log WHERE entity_type = 'SALE' AND entity_id = :id AND action = 'COMPLETE'", {"id": sale_id})
            self.assertEqual(cur.fetchone()[0], 1)
        with self.assertRaisesRegex(ValidationError, "otra venta"):
            sales_service._complete_sale(self.conn, replace(data, notes="Otro carrito"))

    def test_stock_validation_and_duplicate_lines_leave_stock_intact(self):
        for data in (self.sale_data("4"), replace(self.sale_data(), lines=self.sale_data().lines * 2),
                     self.sale_data("0.001"), self.sale_data("NaN")):
            with self.assertRaises(ValidationError):
                sales_service._complete_sale(self.conn, data)
            self.assertEqual(self.product().stock_available, 3)

    def test_failure_after_stock_write_rolls_back_sale_items_movement(self):
        data = self.sale_data()
        with patch.object(sales_service, "connection_scope", self.scope), \
             patch.object(inventory_repository, "insert_movement", side_effect=RuntimeError("Fallo inducido")):
            with self.assertRaisesRegex(RuntimeError, "inducido"):
                sales_service.complete_sale(data)
        self.assertEqual(self.product().stock_available, 3)
        self.assertIsNone(sales_repository.find_request(self.conn, data.request_key))

    def test_failed_confirmation_keeps_request_key(self):
        page = SalesPage()
        page._add_product(self.product())
        key = page._request_key
        with patch.object(sales_service, "complete_sale", side_effect=DatabaseConnectionError("Reintentar")) as complete:
            page._on_confirm()
            page._on_confirm()
            self.assertEqual([call.args[0].request_key for call in complete.call_args_list], [key, key])
        self.assertTrue(page.confirm_button.isEnabled())
        self.assertEqual(len(page._cart), 1)
        page.deleteLater()

    def test_export_png_pdf_independently_decodes_original_values(self):
        for code in (self.code, "4006381333931", "036000291452", "7790000111001", "A" * 100):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as folder:
                label = BarcodeLabel("Shampoo hipoalergénico", code, Decimal("12.50"))
                png, pdf = Path(folder) / "label.png", Path(folder) / "label.pdf"
                export_label(label, str(png))
                formats = (zxingcpp.BarcodeFormat.UPCA if code == "036000291452" else
                           zxingcpp.BarcodeFormat.EAN13 if code == "4006381333931" else
                           zxingcpp.BarcodeFormat.Code128)
                decoded = zxingcpp.read_barcode(Image.open(png), formats=formats)
                self.assertIsNotNone(decoded)
                # ZXing 3 representa UPC-A con el cero EAN incluso en modo UPCA.
                expected = "0" + code if formats == zxingcpp.BarcodeFormat.UPCA else code
                self.assertEqual(decoded.text, expected)
                export_label(label, str(pdf))
                with pymupdf.open(pdf) as document:
                    page = document[0]
                    self.assertIn("shampoo", page.get_text().lower())
                    self.assertIn("12.50", page.get_text())
                    self.assertAlmostEqual(page.rect.width * 25.4 / 72, label.size_mm.width(), delta=0.5)
                    pix = page.get_pixmap(dpi=300)
                    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    decoded = zxingcpp.read_barcode(image, formats=formats)
                    self.assertIsNotNone(decoded)
                    self.assertEqual(decoded.text, expected)

    def test_upc_reader_ean_representation_keeps_stored_code(self):
        product_id = inventory_service._create_product(self.conn, form("036000291452"))
        found = inventory_service._find_active_by_barcode(self.conn, "0036000291452")
        self.assertEqual(found.id, product_id)
        self.assertEqual(found.barcode, "036000291452")

    def test_print_rejects_small_paper(self):
        with tempfile.TemporaryDirectory() as folder:
            writer = QPdfWriter(str(Path(folder) / "small.pdf"))
            small = BarcodeLabel("Producto", "1234", Decimal("1"))
            configure_label_page(writer, small)
            with self.assertRaisesRegex(ValidationError, "menor"):
                print_label(writer, BarcodeLabel("Producto", "X" * 100, Decimal("1")))

    def test_printable_validation_preserves_leading_zeroes(self):
        self.assertEqual(validate_barcode("  001234  "), "001234")
        for code in ("A\x00B", "á", "X" * 101):
            with self.assertRaises(ValidationError):
                validate_barcode(code)

    def test_persistence_in_new_process(self):
        # No hace commit de los fixtures anteriores ni de ninguna venta.
        sku = "__BC_RESTART_" + uuid4().hex
        code = new_internal_code()
        product_id = None
        try:
            with connection_scope(commit=True) as conn:
                product_id = inventory_service._create_product(conn, form(code, sku=sku))
            source = (
                "import sys; from database.connection import connection_scope; "
                "from repositories.inventory_repository import find_by_barcode; "
                "conn=connection_scope(); c=conn.__enter__(); "
                "p=find_by_barcode(c,sys.argv[1]); "
                "assert p is not None and p.id==int(sys.argv[2]) and p.barcode==sys.argv[1]; "
                "conn.__exit__(None,None,None)"
            )
            result = subprocess.run([sys.executable, "-c", source, code, str(product_id)],
                                    cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            if product_id is not None:
                with connection_scope(commit=True) as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM products WHERE id = :id AND sku = :sku", {"id": product_id, "sku": sku})


if __name__ == "__main__":
    unittest.main(verbosity=2)
