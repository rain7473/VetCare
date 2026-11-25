"""Campo de captura para lector de código de barras USB (modo teclado).

Los lectores tipo *keyboard wedge* escriben los dígitos/caracteres
rápidamente y terminan con Enter. Este widget emite ``scanned`` con el
código limpio únicamente al confirmar con Enter o Return.
"""

from __future__ import annotations

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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Escanear o ingresar código")
        self.setClearButtonEnabled(True)
        self._processing = False
        self.returnPressed.connect(self._emit_scan)

    def _emit_scan(self) -> None:
        code = self.text().strip()
        if not code or self._processing:
            return
        self._processing = True
        # Vaciar antes de emitir: Enter repetido o reentrada no repiten la lectura.
        self.clear()
        try:
            self.scanned.emit(code)
        finally:
            self._processing = False
            self.setFocus(Qt.OtherFocusReason)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        # Consumir Enter impide que active también el botón predeterminado del diálogo.
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                self._emit_scan()
            event.accept()
            return
        super().keyPressEvent(event)
