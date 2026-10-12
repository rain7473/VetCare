"""Render offscreen del dashboard completo con datos reales de Oracle (sin escrituras)."""

import argparse
import os
from pathlib import Path
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"


def main():
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtCore import QThreadPool
    from PySide6.QtTest import QTest
    from main import create_app
    from models.user import User
    from services import permission_service, session
    from views.main_window import MainWindow

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    app = create_app([])
    for filename in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Segoe UI", 10))
    user = User(0,1,"preview",None,"Vista previa",None,True,role_name="ADMIN")
    session.set_current_user(user, frozenset(c for codes in permission_service.MODULE_PERMISSIONS.values() for c in codes))
    window = MainWindow(user)
    page = window.stack.widget(window._page_index["dashboard"])
    try:
        window.show()
        deadline = time.monotonic() + 30
        while page._snapshot is None and time.monotonic() < deadline:
            QTest.qWait(20)
            if not page.error_label.isHidden():
                raise RuntimeError(page.error_label.text())
        if page._snapshot is None:
            raise RuntimeError("El dashboard no terminó de cargar")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for width,height in ((1366,768),(1920,1080)):
            window.resize(width,height)
            QTest.qWait(150)
            for suffix, value in (("overview",0),("detail",page.scroll.verticalScrollBar().maximum())):
                page.scroll.verticalScrollBar().setValue(value)
                app.processEvents()
                path = args.output_dir / f"dashboard-{width}-{suffix}.png"
                if not window.grab().save(str(path)):
                    raise RuntimeError(f"No se pudo guardar {path}")
                print(path)
            assert page.scroll.horizontalScrollBar().maximum() == 0
    finally:
        window.close()
        QThreadPool.globalInstance().waitForDone(20000)
        session.clear()


if __name__ == "__main__":
    main()
