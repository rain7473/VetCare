"""VetCare — Sistema de Gestión Integral para Clínica Veterinaria.

Punto de entrada. Flujo de arranque:

    Iniciar VetCare → Conectar a Oracle → ¿Existen usuarios en USERS?
        NO → Configuración inicial (crear ADMIN) → Login
        SÍ → Login

El login se implementa en el Objetivo 4; mientras tanto se muestra la
ventana de marca como pantalla siguiente.
"""

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from config import settings
from config.constants import APP_NAME, APP_VERSION
from database.connection import DatabaseConnectionError
from views.startup.setup_window import SetupWindow
from views.startup.startup_window import StartupWindow

logger = logging.getLogger(__name__)


def load_stylesheet(app: QApplication) -> None:
    """Aplica la hoja de estilos global de VetCare (assets/styles/main.qss)."""
    if settings.STYLES_FILE.exists():
        app.setStyleSheet(settings.STYLES_FILE.read_text(encoding="utf-8"))


def create_app(argv: list[str] | None = None) -> QApplication:
    """Construye la aplicación Qt con la identidad VetCare (sin tocar la BD)."""
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    load_stylesheet(app)
    return app


def select_first_window() -> QWidget:
    """Decide la primera pantalla según la tabla USERS (regla de bootstrap).

    Raises:
        DatabaseConnectionError: si Oracle no está disponible.
    """
    from services import bootstrap_service

    if bootstrap_service.users_exist():
        # Objetivo 4: aquí irá el login.
        return StartupWindow()

    setup = SetupWindow()
    setup.admin_created.connect(lambda: _after_admin_created(setup))
    return setup


def _after_admin_created(setup: SetupWindow) -> None:
    """Tras crear el ADMIN, cerrar la configuración y pasar a la siguiente pantalla."""
    next_window = StartupWindow()  # Objetivo 4: será el login.
    setup.close()
    next_window.show()
    # Mantener referencia para que Qt no destruya la ventana.
    QApplication.instance().setProperty("main_window", next_window)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = create_app()

    try:
        window = select_first_window()
    except DatabaseConnectionError as exc:
        logger.error("No fue posible iniciar VetCare: %s", exc)
        QMessageBox.critical(None, APP_NAME, str(exc))
        return 1

    window.show()
    app.setProperty("main_window", window)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
