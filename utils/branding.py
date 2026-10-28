"""Recursos gráficos de la identidad visual de VetCare."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QImage, QPixmap, QTextDocument

from config.settings import ASSETS_DIR


LOGOS_DIR = ASSETS_DIR / "logos"
FULL_LOGO_PATH = LOGOS_DIR / "vetcare-logo-transparent.png"
SYMBOL_LOGO_PATH = LOGOS_DIR / "vetcare-symbol-transparent.png"
SYMBOL_RESOURCE_URL = QUrl("vetcare:/branding/symbol.png")


def scaled_logo(path: Path, width: int, height: int) -> QPixmap:
    """Carga un logo respetando su proporción y suavizando el escalado."""
    source = QPixmap(str(path))
    if source.isNull():
        return source
    return source.scaled(
        QSize(width, height),
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )


def add_symbol_resource(document: QTextDocument) -> None:
    """Registra el símbolo para vistas HTML, impresión y exportación a PDF."""
    image = QImage(str(SYMBOL_LOGO_PATH))
    if not image.isNull():
        document.addResource(
            QTextDocument.ImageResource,
            SYMBOL_RESOURCE_URL,
            image,
        )
