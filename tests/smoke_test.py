"""Prueba de humo del Objetivo 1.

Verifica que la aplicación se construye sin errores: QApplication,
hoja de estilos cargada y ventana inicial con la identidad VetCare.
Se ejecuta en modo offscreen (no abre ventana real):

    python -m tests.smoke_test
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def run() -> int:
    from main import create_app

    app, window = create_app([])

    checks = {
        "QApplication creada": app is not None,
        "Nombre de aplicación": app.applicationName() == "VetCare",
        "Hoja de estilos cargada": len(app.styleSheet()) > 0,
        "Título de ventana": window.windowTitle() == "VetCare",
        "Tamaño mínimo 640x440": (
            window.minimumWidth() == 640 and window.minimumHeight() == 440
        ),
    }

    failures = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  [{'OK' if ok else 'FALLO'}] {name}")

    if failures:
        print(f"\nPrueba de humo FALLIDA: {len(failures)} comprobación(es) fallaron.")
        return 1

    print("\nPrueba de humo superada: la aplicación se construye correctamente.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
