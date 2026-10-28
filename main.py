"""VetCare — Sistema de Gestión Integral para Clínica Veterinaria.

Punto de entrada. Flujo de arranque:

    Iniciar VetCare → Conectar a Oracle → ¿Existen usuarios en USERS?
        NO → Configuración inicial (crear ADMIN) → Login
        SÍ → Login

Tras el bootstrap se muestra el login y, después de autenticar, el shell
principal filtrado por permisos.
"""

import logging
import hashlib
import sys

from PySide6.QtCore import Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from config import settings
from config.constants import APP_NAME, APP_VERSION
from database.connection import DatabaseConnectionError
from utils.icons import icon
from utils.logging_config import configure_gui_logging
from views.login.login_window import LoginWindow
from views.startup.setup_window import SetupWindow

logger = logging.getLogger(__name__)

_INSTANCE_NAME = "VetCare-" + hashlib.sha256(
    str(settings.BASE_DIR.resolve()).lower().encode("utf-8")
).hexdigest()[:16]


def load_stylesheet(app: QApplication) -> None:
    """Aplica la hoja de estilos global de VetCare (assets/styles/main.qss)."""
    if settings.STYLES_FILE.exists():
        app.setStyleSheet(settings.STYLES_FILE.read_text(encoding="utf-8"))


def create_app(argv: list[str] | None = None) -> QApplication:
    """Construye la aplicación Qt con la identidad VetCare (sin tocar la BD)."""
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(icon("pets"))
    from utils.calendar_style import CalendarStyle
    if not hasattr(app, "_calendar_style"):
        app._calendar_style = CalendarStyle(app)
        app.installEventFilter(app._calendar_style)
    load_stylesheet(app)
    return app


def select_first_window() -> QWidget:
    """Decide la primera pantalla según la tabla USERS (regla de bootstrap).

    Raises:
        DatabaseConnectionError: si Oracle no está disponible.
    """
    from services import bootstrap_service

    if bootstrap_service.users_exist():
        return _build_login_window()

    setup = SetupWindow()
    setup.admin_created.connect(lambda: _swap_window(setup, _build_login_window()))
    return setup


def _build_login_window() -> LoginWindow:
    login = LoginWindow()
    login.login_succeeded.connect(
        lambda user: _swap_window(login, _build_main_window(user))
    )
    return login


def _build_main_window(user) -> QWidget:
    """Shell principal tras un login exitoso."""
    from services import permission_service, session
    from views.main_window import MainWindow

    permissions = permission_service.load_role_permissions(user.role_id)
    session.set_current_user(user, permissions)
    logger.info(
        "Sesión iniciada: %s (%s permisos)", user.username, len(permissions)
    )

    window = MainWindow(user)
    window.logout_requested.connect(lambda: _on_logout(window))
    return window


def _on_logout(window: QWidget) -> None:
    """Cierra la sesión actual y vuelve al login."""
    from services import session

    session.clear()
    logger.info("Sesión cerrada.")
    _swap_window(window, _build_login_window())


def _swap_window(current: QWidget, next_window: QWidget) -> None:
    """Sustituye una ventana primaria y destruye su superficie nativa anterior.

    ``QWidget.close()`` solo oculta una ventana de nivel superior de forma
    predeterminada.  Mantener esas ventanas ocultas dejaba sus ``HWND`` vivos
    en Windows y podía producir miniaturas/superficies fantasma al abrir un
    diálogo.  ``WA_DeleteOnClose`` garantiza que login, configuración o shell
    anterior desaparezcan por completo al terminar la transición.
    """
    # Ocultar primero evita que Windows muestre dos ventanas de VetCare durante
    # la transición login ↔ shell, especialmente en equipos con animaciones.
    current.hide()
    _show_primary_window(next_window)
    current.setAttribute(Qt.WA_DeleteOnClose, True)
    current.close()
    QApplication.instance().setProperty("main_window", next_window)


def _show_primary_window(window: QWidget) -> None:
    """Las pantallas primarias ocupan el escritorio y cubren el lanzador."""
    window.setWindowState(window.windowState() | Qt.WindowMaximized)
    window.showMaximized()
    window.raise_()
    window.activateWindow()


def claim_single_instance(app: QApplication, name: str = _INSTANCE_NAME) -> bool:
    """Impide que dobles clics o ejecuciones repetidas creen más ventanas."""
    probe = QLocalSocket(app)
    probe.connectToServer(name)
    if probe.waitForConnected(250):
        probe.write(b"activate")
        probe.waitForBytesWritten(250)
        probe.disconnectFromServer()
        return False

    # Solo se elimina un endpoint huérfano después de comprobar que nadie
    # escucha. En Windows corresponde al nombre de la tubería local de Qt.
    QLocalServer.removeServer(name)
    server = QLocalServer(app)
    if not server.listen(name):
        logger.warning("No se pudo registrar la instancia única: %s", server.errorString())
        return True

    def activate_existing_window() -> None:
        connection = server.nextPendingConnection()
        if connection is not None:
            connection.waitForReadyRead(100)
            connection.deleteLater()
        window = app.property("main_window")
        if isinstance(window, QWidget):
            _show_primary_window(window)

    server.newConnection.connect(activate_existing_window)
    # La referencia Python evita que el servidor sea recolectado mientras vive Qt.
    app._vetcare_instance_server = server
    return True


def main() -> int:
    configure_gui_logging()
    app = create_app()
    if not claim_single_instance(app):
        return 0

    try:
        window = select_first_window()
    except DatabaseConnectionError as exc:
        logger.error("No fue posible iniciar VetCare: %s", exc)
        QMessageBox.critical(None, APP_NAME, str(exc))
        return 1

    _show_primary_window(window)
    app.setProperty("main_window", window)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
