"""Capturas offscreen del perfil con mascotas reales; solo lectura en Oracle.

    python -m scripts.preview_pet_profile --output-dir RUTA

No muestra ventanas en el escritorio ni crea una sesión funcional persistente.
"""

import argparse
import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"


def main() -> None:
    from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
    from PySide6.QtWidgets import QApplication
    from main import create_app
    from models.user import User
    from services import permission_service, session
    from views.main_window import MainWindow

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication([])
    # El backend offscreen de Windows no descubre las fuentes del sistema.
    for filename in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Segoe UI", 10))
    palette = app.palette()
    palette.setColor(QPalette.Window, QColor("#202020"))
    palette.setColor(QPalette.Base, QColor("#202020"))
    app.setPalette(palette)
    create_app([])
    user = User(
        id=0, role_id=1, username="preview", email=None,
        full_name="Vista previa", phone=None, is_active=True, role_name="ADMIN",
    )
    permissions = frozenset(
        code for codes in permission_service.MODULE_PERMISSIONS.values() for code in codes
    )
    session.set_current_user(user, permissions)
    window = MainWindow(user)
    try:
        window.navigate_to("pets")
        window.show()
        app.processEvents()
        page = window.stack.widget(window._page_index["pets"])
        selected = next((pet for pet in page._pets if pet.photo_url), None)
        row = page._pets.index(selected) if selected else 0
        if page.model.rowCount():
            page.table.selectRow(row)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for width, height in ((1366, 768), (1920, 1080)):
            window.resize(width, height)
            for _ in range(4):
                app.processEvents()
            output = args.output_dir / f"vetcare-profile-{width}.png"
            if not window.grab().save(str(output)):
                raise RuntimeError(f"No se pudo guardar la captura: {output}")
            panel = page.profile_panel
            print(f"{output} | panel={panel.width()}px | columnas={panel._columns}")
    finally:
        window.close()
        session.clear()


if __name__ == "__main__":
    main()
