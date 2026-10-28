"""Vista de factura y acciones de salida para el detalle de una venta."""

from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from config.constants import APP_FOOTER_MOTTO, APP_NAME, APP_TAGLINE
from models.sale import PAYMENT_LABELS, STATUS_LABELS, Sale
from widgets.managed_dialog import ManagedDialog
from utils.icons import set_button_icon


class SaleDetailDialog(ManagedDialog):
    """Factura legible en pantalla, lista para guardar o imprimir."""

    def __init__(self, sale: Sale, parent=None) -> None:
        super().__init__(parent)
        self.sale = sale
        self._html = _invoice_html(sale)
        self.setWindowTitle(sale.invoice_number)
        self.resize(1060, 820)
        self.setMinimumSize(760, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.preview.setHtml(self._html)
        self.preview.setMinimumWidth(700)
        layout.addWidget(self.preview, stretch=1)

        actions = QHBoxLayout()
        actions.addStretch()
        export_button = QPushButton("Exportar PDF")
        set_button_icon(export_button, "download")
        export_button.clicked.connect(self._export_pdf)
        actions.addWidget(export_button)

        print_button = QPushButton("Imprimir")
        set_button_icon(print_button, "print")
        print_button.clicked.connect(self._print)
        actions.addWidget(print_button)

        close_button = QPushButton("Cerrar")
        close_button.setProperty("variant", "secondary")
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)
        layout.addLayout(actions)

    def _document(self, printer: QPrinter) -> QTextDocument:
        document = QTextDocument(self)
        document.setHtml(self._html)
        page = printer.pageRect(QPrinter.DevicePixel)
        document.setPageSize(page.size())
        return document

    def _export_pdf(self) -> None:
        default_name = f"{self.sale.invoice_number}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar detalle de venta",
            default_name,
            "Documento PDF (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        printer.setPageMargins(QMarginsF(14, 14, 14, 14))
        self._document(printer).print_(printer)
        if not Path(path).is_file() or Path(path).stat().st_size == 0:
            QMessageBox.warning(self, "Exportar PDF", "No se pudo crear el archivo PDF.")
            return
        QMessageBox.information(self, "Exportar PDF", f"PDF guardado en:\n{path}")

    def _print(self) -> None:
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageMargins(QMarginsF(14, 14, 14, 14))
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Imprimir detalle de venta")
        if dialog.exec():
            self._document(printer).print_(printer)


def _invoice_html(sale: Sale) -> str:
    invoice = escape(sale.invoice_number)
    date = escape(sale.sold_at.strftime("%d/%m/%Y %H:%M"))
    customer = escape(sale.owner_name or "Mostrador")
    payment = escape(PAYMENT_LABELS.get(sale.payment_method, sale.payment_method))
    status = escape(STATUS_LABELS.get(sale.status, sale.status))
    seller = escape(sale.sold_by_name or "—")

    rows = []
    for index, item in enumerate(sale.items, start=1):
        name = escape(item.product_name or "Producto")
        quantity = f"{item.quantity:g}"
        price = f"${item.unit_price:,.2f}"
        discount = f"${item.discount_amount:,.2f}"
        total = item.line_total
        if total is None:
            total = item.quantity * item.unit_price - item.discount_amount
        rows.append(
            "<tr>"
            f"<td class='center'>{index}</td>"
            f"<td>{name}</td>"
            f"<td class='center'>{quantity}</td>"
            f"<td class='right'>{price}</td>"
            f"<td class='right'>{discount}</td>"
            f"<td class='right'>{f'${total:,.2f}'}</td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='6' class='empty'>Sin productos registrados</td></tr>")

    notes = ""
    if sale.notes and sale.notes.strip():
        notes = (
            "<div class='notes'><strong>Notas</strong><br>"
            f"{escape(sale.notes).replace(chr(10), '<br>')}</div>"
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #17324d; font-size: 10pt; }}
table {{ border-collapse: collapse; width: 100%; }}
.top td {{ vertical-align: top; padding: 5px 4px 14px; }}
.brand-mark {{ color: #008fa3; font-size: 22pt; font-weight: bold; }}
.brand {{ color: #102a43; font-size: 23pt; font-weight: bold; letter-spacing: 1px; }}
.subtitle {{ color: #6b8194; font-size: 9pt; }}
.doc-title {{ color: #102a43; font-size: 20pt; font-weight: bold; text-align: right; }}
.invoice {{ color: #008fa3; font-size: 13pt; font-weight: bold; text-align: right; padding-top: 6px; }}
.rule {{ border-top: 2px solid #008fa3; margin: 7px 0 15px; }}
.meta {{ background: #f1f6f8; border: 1px solid #dce7ec; border-radius: 5px; }}
.meta td {{ padding: 7px 9px; }}
.label {{ color: #6b8194; font-weight: bold; }}
.value {{ color: #17324d; }}
.section-title {{ font-size: 12pt; font-weight: bold; color: #102a43; padding: 13px 0 8px; }}
.items th {{ background: #e5f1f5; color: #102a43; padding: 9px 7px; border: 1px solid #c9dce4; }}
.items td {{ padding: 9px 7px; border: 1px solid #d8e4e9; }}
.center {{ text-align: center; }} .right {{ text-align: right; }}
.empty {{ text-align: center; color: #6b8194; padding: 18px !important; }}
.bottom {{ margin-top: 18px; }}
.thanks {{ color: #102a43; font-size: 13pt; font-weight: bold; padding-top: 20px; }}
.motto {{ color: #6b8194; padding-top: 5px; }}
.totals {{ width: 100%; background: #f1f6f8; border: 1px solid #dce7ec; }}
.totals td {{ padding: 7px 10px; }}
.total-row td {{ background: #d9eff5; color: #064c75; font-size: 16pt; font-weight: bold; padding-top: 11px; padding-bottom: 11px; }}
.notes {{ color: #526779; background: #f7fafb; border: 1px solid #e1e9ed; padding: 9px; margin-top: 16px; }}
.footer {{ color: #8294a1; font-size: 8pt; text-align: center; padding-top: 18px; }}
</style></head><body>
<table class="top"><tr>
<td width="52%"><span class="brand-mark">VC</span>&nbsp;&nbsp;<span class="brand">{escape(APP_NAME)}</span><br>
<span class="subtitle">CLÍNICA VETERINARIA · {escape(APP_TAGLINE)}</span></td>
<td width="48%"><div class="doc-title">DETALLE DE VENTA</div><div class="invoice">No. {invoice}</div></td>
</tr></table>
<div class="rule"></div>
<table class="meta">
<tr><td width="18%" class="label">Fecha</td><td width="32%" class="value">{date}</td><td width="18%" class="label">Cliente</td><td width="32%" class="value">{customer}</td></tr>
<tr><td class="label">Método de pago</td><td class="value">{payment}</td><td class="label">Estado</td><td class="value">{status}</td></tr>
<tr><td class="label">Vendedor</td><td colspan="3" class="value">{seller}</td></tr>
</table>
<div class="section-title">Productos y servicios</div>
<table class="items"><thead><tr>
<th width="6%">#</th><th width="40%">Producto / Servicio</th><th width="12%">Cant.</th>
<th width="15%">Precio unit.</th><th width="12%">Desc.</th><th width="15%">Subtotal</th>
</tr></thead><tbody>{''.join(rows)}</tbody></table>
{notes}
<table class="bottom"><tr><td width="49%" class="thanks">¡Gracias por su compra!<br><span class="motto">{escape(APP_FOOTER_MOTTO)}</span></td>
<td width="51%"><table class="totals">
<tr><td>Subtotal</td><td class="right">${sale.subtotal:,.2f}</td></tr>
<tr><td>Descuento</td><td class="right">${sale.discount_amount:,.2f}</td></tr>
<tr><td>Impuestos</td><td class="right">${sale.tax_amount:,.2f}</td></tr>
<tr class="total-row"><td>Total</td><td class="right">${sale.total:,.2f}</td></tr>
</table></td></tr></table>
<div class="footer">{escape(APP_NAME)} · {escape(APP_TAGLINE)}</div>
</body></html>"""
