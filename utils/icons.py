"""Iconografía VetCare: Font Awesome Solid mediante QtAwesome y PySide6.

Crear iconos después de QApplication. Los nombres semánticos mantienen a
las vistas independientes de la familia de iconos y centralizan su paleta.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QAbstractButton, QLabel

import qtawesome as qta

from config.constants import Colors

SMALL = 14
NORMAL = 18
LARGE = 28

ICONS = {
    "dashboard": "fa5s.home", "owners": "fa5s.user",
    "pets": "fa5s.paw", "appointments": "fa5s.calendar-alt",
    "triage": "fa5s.ambulance", "consultations": "fa5s.stethoscope",
    "vaccines": "fa5s.syringe", "hospitalization": "fa5s.bed",
    "inventory": "fa5s.boxes", "sales": "fa5s.shopping-cart",
    "users": "fa5s.users", "audit": "fa5s.shield-alt", "settings": "fa5s.cog",
    "brand": "fa5s.heart", "add": "fa5s.plus", "edit": "fa5s.pen",
    "camera": "fa5s.camera", "history": "fa5s.history", "info": "fa5s.info-circle",
    "files": "fa5s.folder-open", "card": "fa5s.id-card", "sex": "fa5s.venus-mars",
    "age": "fa5s.birthday-cake", "color": "fa5s.palette", "microchip": "fa5s.microchip",
    "blood": "fa5s.tint", "allergies": "fa5s.allergies",
    "chronic": "fa5s.heartbeat", "features": "fa5s.fingerprint",
    "notes": "fa5s.notes-medical", "weight": "fa5s.weight",
    "success": "fa5s.check-circle", "warning": "fa5s.exclamation-triangle",
    "inactive": "fa5s.pause-circle", "deceased": "fa5s.heart-broken",
    "search": "fa5s.search", "notifications": "fa5s.bell",
    "chevron_down": "fa5s.chevron-down", "logout": "fa5s.sign-out-alt",
    "refresh": "fa5s.sync-alt", "print": "fa5s.print", "save": "fa5s.save",
    "delete": "fa5s.trash-alt", "view": "fa5s.eye", "products": "fa5s.tags",
    "expiring": "fa5s.hourglass-half", "waiting": "fa5s.stopwatch",
    "followup": "fa5s.calendar-check", "breed": "fa5s.bone",
    "filter": "fa5s.filter", "stock": "fa5s.sliders-h", "supplier": "fa5s.truck",
    "download": "fa5s.download", "barcode": "fa5s.barcode", "receipt": "fa5s.receipt",
}


def icon(name: str, color: str = Colors.PRIMARY, *, active: str | None = None) -> QIcon:
    """Devuelve un QIcon con estados normal, activo, seleccionado y deshabilitado."""
    return qta.icon(
        ICONS[name], color=color, color_active=active or color,
        color_selected=active or color, color_on=active or color,
        color_disabled="#93ABB8",
    )


def pixmap(name: str, size: int = NORMAL, color: str = Colors.PRIMARY) -> QPixmap:
    return icon(name, color).pixmap(QSize(size, size))


def icon_label(name: str, size: int = NORMAL, color: str = Colors.PRIMARY) -> QLabel:
    label = QLabel()
    label.setObjectName("vetIcon")
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignCenter)
    label.setPixmap(pixmap(name, size, color))
    return label


def set_button_icon(
    button: QAbstractButton, name: str, *, size: int = NORMAL,
    color: str = "#FFFFFF", active: str | None = None,
) -> None:
    button.setIcon(icon(name, color, active=active))
    button.setIconSize(QSize(size, size))
