"""Registro persistente para la aplicación gráfica, sin depender de una consola."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_gui_logging() -> Path:
    """Envía los mensajes a LocalAppData y evita depender de stderr."""
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "VetCare" / "logs"
    base.mkdir(parents=True, exist_ok=True)
    log_file = base / "vetcare.log"

    root = logging.getLogger()
    if not any(getattr(handler, "name", "") == "vetcare_file" for handler in root.handlers):
        handler = RotatingFileHandler(
            log_file,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.name = "vetcare_file"
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    return log_file
