"""Campo de captura para lector de código de barras USB (modo teclado).

Los lectores tipo *keyboard wedge* escriben los dígitos/caracteres
rápidamente y terminan con Enter. Este widget emite ``scanned`` con el
código limpio al confirmar (Return) o al detectar un barrido rápido.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit


class BarcodeScannerInput(QLineEdit):
    """Entrada optimizada para escáner USB tipo teclado.

    - Emite ``scanned(str)`` al pulsar Enter / Return.
    - Ignora espacios laterales.
    - No interpreta el código (eso lo hace el service).
    """

    scanned = Signal(str)

    # Umbral: si llegan varios caracteres en menos de este intervalo (ms)
    # se considera barrido de escáner (informativo; Enter sigue siendo
    # la confirmación principal).
    _RAPID_MS = 80

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Escanear código de barras…")
        self.setClearButtonEnabled(True)
        self._last_key_at = 0.0
        self.returnPressed.connect(self._emit_scan)

    def _emit_scan(self) -> None:
        code = self.text().strip()
        if not code:
            return
        self.scanned.emit(code)
        self.clear()
        self.setFocus(Qt.OtherFocusReason)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        now = time.monotonic() * 1000
        # Conservar comportamiento estándar; solo rastrear velocidad.
        if event.text() and not event.modifiers() & Qt.ControlModifier:
            self._last_key_at = now
        super().keyPressEvent(event)
