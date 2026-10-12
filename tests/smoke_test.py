"""Prueba de humo de la interfaz (no requiere Oracle).

Verifica que la aplicación Qt, las ventanas de arranque y el shell
principal se construyen sin errores, en modo offscreen:

    python -m tests.smoke_test
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _fake_user():
    from models.user import User

    return User(
        id=0,
        role_id=1,
        username="demo",
        email="demo@vetcare.local",
        full_name="Usuaria Demo",
        phone=None,
        is_active=True,
        role_name="ADMIN",
    )


def run() -> int:
    from main import (
        _show_primary_window,
        _swap_window,
        claim_single_instance,
        create_app,
    )
    from PySide6.QtCore import QEvent, QTimer
    from PySide6.QtNetwork import QLocalServer
    from PySide6.QtWidgets import QApplication, QWidget
    from services import permission_service, session
    from views.login.login_window import LoginWindow
    from views.main_window import MainWindow
    from views.startup.setup_window import SetupWindow
    from widgets.sidebar import NAV_ITEMS
    from widgets.managed_dialog import ManagedDialog

    root = Path(__file__).resolve().parents[1]

    app = create_app([])
    setup = SetupWindow()
    login = LoginWindow()
    _show_primary_window(login)
    app.processEvents()

    # Una transición no debe dejar el HWND anterior oculto. Esas superficies
    # nativas residuales provocaban ventanas fantasma en Windows al abrir
    # formularios modales como "Nueva mascota".
    transition_source = LoginWindow()
    transition_target = QWidget()
    transition_source.show()
    _swap_window(transition_source, transition_target)
    app.processEvents()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    transition_source_removed = transition_source not in QApplication.topLevelWidgets()

    dialog_parent = QWidget()
    dialog = ManagedDialog(dialog_parent)
    dialog.created_id = 123
    QTimer.singleShot(0, dialog.accept)
    dialog_result = dialog.exec()
    dialog_data_available = dialog.created_id == 123
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    dialog_surface_removed = dialog not in QApplication.topLevelWidgets()

    instance_name = f"VetCare-smoke-{os.getpid()}"
    first_instance = claim_single_instance(app, instance_name)
    second_instance = claim_single_instance(app, instance_name)
    test_server = getattr(app, "_vetcare_instance_server", None)

    # Sesión simulada con todos los permisos (como un ADMIN).
    all_codes = frozenset(
        code
        for codes in permission_service.MODULE_PERMISSIONS.values()
        for code in codes
    )
    fake = _fake_user()
    session.set_current_user(fake, all_codes)
    main_window = MainWindow(fake)

    # Shell con permisos limitados (como SALES).
    session.set_current_user(
        fake, frozenset({"SALES_READ", "SALES_CREATE", "INVENTORY_READ"})
    )
    sales_window = MainWindow(fake)
    session.set_current_user(fake, all_codes)

    # Navegación: cambiar a un módulo debe cambiar la página visible.
    index_before = main_window.stack.currentIndex()
    main_window.navigate_to("pets")
    index_after = main_window.stack.currentIndex()

    checks = {
        "QApplication creada": app is not None,
        "Hoja de estilos cargada": len(app.styleSheet()) > 0,
        "SetupWindow construida": "Configuración inicial" in setup.windowTitle(),
        "SetupWindow tiene 7 campos": all(
            hasattr(setup, name)
            for name in (
                "full_name_input",
                "username_input",
                "email_input",
                "phone_input",
                "clinic_name_input",
                "password_input",
                "confirmation_input",
            )
        ),
        "LoginWindow construida": "Iniciar sesión" in login.windowTitle(),
        "Login abre maximizado": login.isMaximized(),
        "Transición destruye la ventana nativa anterior": transition_source_removed,
        "Diálogo conserva datos al retornar": (
            dialog_result == ManagedDialog.Accepted and dialog_data_available
        ),
        "Diálogo libera su ventana nativa": dialog_surface_removed,
        "Solo una instancia permitida": first_instance and not second_instance,
        "Sidebar define 13 módulos": len(NAV_ITEMS) == 13,
        "Stack ADMIN con 13 páginas": main_window.stack.count() == 13,
        "Shell SALES con 3 páginas": sales_window.stack.count() == 3,
        "Página Propietarios integrada": "owners" in main_window._page_index,
        "Página Mascotas integrada": "pets" in main_window._page_index,
        "Página Citas integrada": "appointments" in main_window._page_index,
        "Página Triaje integrada": "triage" in main_window._page_index,
        "Página Consultas integrada": "consultations" in main_window._page_index,
        "Página Vacunas integrada": "vaccines" in main_window._page_index,
        "Página Hospitalización integrada": "hospitalization" in main_window._page_index,
        "Página Inventario integrada": "inventory" in main_window._page_index,
        "Página Ventas integrada": "sales" in main_window._page_index,
        "Página Auditoría integrada": "audit" in main_window._page_index,
        "Navegación cambia de página": index_before != index_after,
        "Topbar muestra al usuario": (
            main_window.topbar._user.full_name == "Usuaria Demo"
        ),
        "Dashboard por rol preparado": hasattr(main_window.stack.widget(0), "refresh"),
        "Lanzador Windows sin consola disponible": (
            (root / "launch_vetcare.vbs").is_file()
            and (root / "VetCare.pyw").is_file()
            and (root / ".venv" / "Scripts" / "pythonw.exe").is_file()
        ),
    }
    from services import session as _session

    _session.clear()
    if test_server is not None:
        test_server.close()
    QLocalServer.removeServer(instance_name)

    failures = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  [{'OK' if ok else 'FALLO'}] {name}")

    if failures:
        print(f"\nPrueba de humo FALLIDA: {len(failures)} comprobación(es) fallaron.")
        return 1

    print("\nPrueba de humo superada: la interfaz se construye correctamente.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
