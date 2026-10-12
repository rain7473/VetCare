"""Verifica QtAwesome/PySide6 y que todo el catálogo produzca iconos visibles."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def run() -> int:
    import qtpy
    import qtawesome
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon
    from main import create_app
    from utils.icons import ICONS, icon
    from widgets.sidebar import Sidebar

    app = create_app([])
    failures = []
    if qtpy.API_NAME != "PySide6":
        failures.append("QtAwesome no está utilizando PySide6")
    for name in ICONS:
        for mode in (QIcon.Normal, QIcon.Disabled):
            rendered = icon(name).pixmap(QSize(24, 24), mode).toImage()
            if rendered.isNull() or not any(
                rendered.pixelColor(x, y).alpha() > 0
                for x in range(rendered.width()) for y in range(rendered.height())
            ):
                failures.append(f"Icono vacío: {name} ({mode})")
    sidebar = Sidebar()
    if any(button.icon().isNull() for button in sidebar._buttons.values()):
        failures.append("Hay módulos de navegación sin icono")
    sidebar.close()
    print(f"QtAwesome {qtawesome.__version__} / {qtpy.API_NAME}")
    print(f"Catálogo: {len(ICONS)} iconos, estados normal y deshabilitado.")
    for message in failures:
        print(f"  [FALLO] {message}")
    print("Iconografía verificada." if not failures else "Falló la verificación de iconos.")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(run())
