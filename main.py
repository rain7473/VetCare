"""VetCare — Sistema de Gestión Integral para Clínica Veterinaria.

Punto de entrada de la aplicación de escritorio (PySide6 + Oracle).
"""

import sys

from PySide6.QtWidgets import QApplication

from config import settings
from config.constants import APP_NAME, APP_VERSION
from views.startup.startup_window import StartupWindow


def load_stylesheet(app: QApplication) -> None:
    """Aplica la hoja de estilos global de VetCare (assets/styles/main.qss)."""
    if settings.STYLES_FILE.exists():
        app.setStyleSheet(settings.STYLES_FILE.read_text(encoding="utf-8"))


def create_app(argv: list[str] | None = None) -> tuple[QApplication, StartupWindow]:
    """Construye la aplicación Qt y su ventana inicial.

    Se separa de ``main()`` para que las pruebas puedan construir la
    interfaz sin entrar al bucle de eventos.
    """
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    load_stylesheet(app)
    window = StartupWindow()
    return app, window


def main() -> int:
    app, window = create_app()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
