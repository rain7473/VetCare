"""Generación de códigos QR (carné digital).

El QR solo debe contener el token público, nunca datos clínicos.
"""

from io import BytesIO

import qrcode
from PySide6.QtGui import QImage, QPixmap


def make_qr_pixmap(payload: str, box_size: int = 6) -> QPixmap:
    """Genera un QPixmap con el QR del payload indicado."""
    qr = qrcode.QRCode(version=None, box_size=box_size, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    qimage = QImage.fromData(buffer.getvalue(), "PNG")
    return QPixmap.fromImage(qimage)


def card_payload(public_token_hex: str) -> str:
    """Payload no sensible para el carné digital."""
    return f"vetcare:pet:{public_token_hex.lower()}"
