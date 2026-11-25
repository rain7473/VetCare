"""Vista e impresión de la etiqueta del producto guardado en Oracle."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout

from models.inventory import Product
from utils.barcode_label import BarcodeLabel, configure_label_page, export_label, label_image, print_label
from utils.icons import set_button_icon
from utils.validators import ValidationError
from widgets.managed_dialog import ManagedDialog


class BarcodeLabelDialog(ManagedDialog):
    def __init__(self, product: Product, parent=None) -> None:
        super().__init__(parent)
        self.label = BarcodeLabel(product.name, product.barcode or "", product.sale_price)
        self.setWindowTitle("Etiqueta del producto")
        self.resize(740, 420)
        layout = QVBoxLayout(self)
        image = label_image(self.label)
        preview = QLabel()
        preview.setAlignment(Qt.AlignCenter)
        preview.setPixmap(QPixmap.fromImage(image).scaled(
            660, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(preview)
        layout.addWidget(scroll, stretch=1)
        size = self.label.size_mm
        layout.addWidget(QLabel(f"Tamaño real: {size.width():.1f} × {size.height():.1f} mm. Imprimir al 100 %."))
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        actions = QHBoxLayout()
        for title, icon, callback in (
            ("Exportar PNG / PDF", "download", self._export),
            ("Imprimir", "print", self._print),
            ("Cerrar", "view", self.accept),
        ):
            button = QPushButton(title)
            set_button_icon(button, icon, color="#008FA3")
            button.setProperty("variant", "secondary")
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)

    def _export(self) -> None:
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Exportar etiqueta", "etiqueta.png", "Imagen PNG (*.png);;Documento PDF (*.pdf)"
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".pdf" if "PDF" in selected_filter else ".png"
        try:
            export_label(self.label, path)
        except (ValidationError, OSError) as exc:
            self.message.setText(str(exc))
            return
        self.message.setText(f"Etiqueta guardada: {path}")

    def _print(self) -> None:
        printer = QPrinter(QPrinter.HighResolution)
        configure_label_page(printer, self.label)
        if QPrintDialog(printer, self).exec() != self.Accepted:
            return
        try:
            print_label(printer, self.label)
        except ValidationError as exc:
            self.message.setText(str(exc))
