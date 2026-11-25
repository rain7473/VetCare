"""Etiquetas a tamaño real: mismo dibujo para vista previa, PNG, PDF e impresora.

Las barras se dibujan como rectángulos, con módulos de 0.254 mm y zonas mudas
de al menos diez módulos. Nunca se comprime el símbolo para ajustarlo al papel.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from math import ceil

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QFont, QImage, QPainter, QPageSize, QPdfWriter

from utils.barcodes import barcode_symbol
from utils.validators import ValidationError

DPI = 300
HEIGHT = 450


@dataclass(frozen=True)
class BarcodeLabel:
    name: str
    code: str
    price: Decimal

    @property
    def modules(self) -> str:
        return barcode_symbol(self.code).build()[0]

    @property
    def width(self) -> int:
        return max(827, (len(self.modules) + 24) * 3)

    @property
    def size_mm(self) -> QSizeF:
        # Qt redondea el papel a puntos enteros; redondear hacia arriba evita recorte.
        return QSizeF(ceil(self.width * 72 / DPI) * 25.4 / 72,
                      ceil(HEIGHT * 72 / DPI) * 25.4 / 72)


def paint_label(painter: QPainter, label: BarcodeLabel) -> None:
    width = label.width
    painter.fillRect(QRectF(0, 0, width, HEIGHT), Qt.white)
    painter.setPen(Qt.black)
    font = QFont("Arial")
    font.setPixelSize(34)
    painter.setFont(font)
    name_rect = QRectF(30, 12, width - 60, 88)
    flags = Qt.AlignCenter | Qt.TextWordWrap
    while painter.boundingRect(name_rect, flags, label.name).height() > 88 and font.pixelSize() > 18:
        font.setPixelSize(font.pixelSize() - 1)
        painter.setFont(font)
    painter.drawText(name_rect, flags, label.name)
    modules = label.modules
    left = (width - len(modules) * 3) // 2
    # Enteros a 300 DPI: PNG sin interpolación ni bordes grises.
    for offset, bit in enumerate(modules):
        if bit == "1":
            painter.fillRect(QRectF(left + offset * 3, 115, 3, 180), Qt.black)
    font.setPixelSize(26)
    painter.setFont(font)
    painter.drawText(QRectF(20, 302, width - 40, 44), Qt.AlignCenter, label.code)
    font.setPixelSize(38)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRectF(20, 355, width - 40, 65), Qt.AlignCenter, f"${label.price:.2f}")


def label_image(label: BarcodeLabel) -> QImage:
    image = QImage(label.width, HEIGHT, QImage.Format_RGB32)
    image.setDotsPerMeterX(round(DPI / 0.0254))
    image.setDotsPerMeterY(round(DPI / 0.0254))
    painter = QPainter(image)
    try:
        paint_label(painter, label)
    finally:
        painter.end()
    return image


def configure_label_page(device, label: BarcodeLabel) -> None:
    device.setPageSize(QPageSize(label.size_mm, QPageSize.Millimeter, "Etiqueta VetCare"))
    device.setPageMargins(QMarginsF(0, 0, 0, 0))


def print_label(device, label: BarcodeLabel) -> None:
    # Tras el diálogo de impresión el usuario puede haber cambiado el papel.
    rect = device.pageLayout().paintRectPixels(device.resolution())
    scale = device.resolution() / DPI
    if rect.width() + 1 < label.width * scale or rect.height() + 1 < HEIGHT * scale:
        raise ValidationError("El papel es menor que la etiqueta. Seleccione un tamaño mayor; no reduzca las barras.")
    painter = QPainter()
    if not painter.begin(device):
        raise ValidationError("No se pudo abrir el destino de impresión.")
    try:
        painter.scale(scale, scale)
        paint_label(painter, label)
    finally:
        painter.end()


def export_label(label: BarcodeLabel, path: str) -> None:
    suffix = Path(path).suffix.lower()
    if suffix == ".png":
        if not label_image(label).save(path, "PNG"):
            raise ValidationError("No se pudo guardar la imagen de la etiqueta.")
    elif suffix == ".pdf":
        writer = QPdfWriter(path)
        writer.setResolution(DPI)
        writer.setTitle(f"Etiqueta — {label.name}")
        configure_label_page(writer, label)
        print_label(writer, label)
    else:
        raise ValidationError("Guarde la etiqueta como PNG o PDF.")
