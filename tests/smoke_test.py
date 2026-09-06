"""Prueba de humo de la interfaz (no requiere Oracle).

Verifica que la aplicación Qt, las ventanas de arranque y el shell
principal se construyen sin errores, en modo offscreen:

    python -m tests.smoke_test
"""

import os
import sys

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
    from main import create_app
    from services import permission_service, session
    from views.login.login_window import LoginWindow
    from views.main_window import MainWindow
    from views.startup.setup_window import SetupWindow
    from widgets.sidebar import NAV_ITEMS

    app = create_app([])
    setup = SetupWindow()
    login = LoginWindow()

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
        "Sidebar define 12 módulos": len(NAV_ITEMS) == 12,
        "Stack ADMIN con 12 páginas": main_window.stack.count() == 12,
        "Shell SALES con 3 páginas": sales_window.stack.count() == 3,
        "Página Propietarios integrada": "owners" in main_window._page_index,
        "Página Mascotas integrada": "pets" in main_window._page_index,
        "Navegación cambia de página": index_before != index_after,
        "Topbar muestra al usuario": (
            main_window.topbar._user.full_name == "Usuaria Demo"
        ),
        "Dashboard con 4 stat cards": (
            len(main_window.stack.widget(0).cards) == 4
        ),
    }
    from services import session as _session

    _session.clear()

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
