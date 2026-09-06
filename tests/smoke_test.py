"""Prueba de humo de la interfaz (no requiere Oracle).

Verifica que la aplicación Qt y las ventanas de arranque se construyen
sin errores, en modo offscreen:

    python -m tests.smoke_test
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def run() -> int:
    from main import create_app
    from views.startup.setup_window import SetupWindow
    from views.startup.startup_window import StartupWindow

    app = create_app([])
    startup = StartupWindow()
    setup = SetupWindow()

    checks = {
        "QApplication creada": app is not None,
        "Nombre de aplicación": app.applicationName() == "VetCare",
        "Hoja de estilos cargada": len(app.styleSheet()) > 0,
        "StartupWindow construida": startup.windowTitle() == "VetCare",
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
    }

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
