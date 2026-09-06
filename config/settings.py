"""Settings de VetCare.

Carga las variables de entorno desde ``.env`` (nunca credenciales en código)
y expone rutas base del proyecto. La conexión Oracle que consume estas
variables se implementa en ``database/connection.py`` (Objetivo 2).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Rutas base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
STYLES_FILE = ASSETS_DIR / "styles" / "main.qss"

# Variables de entorno (.env en la raíz del proyecto)
load_dotenv(BASE_DIR / ".env")

DB_USER = os.getenv("DB_USER", "VETCARE")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "1521"))
DB_SERVICE = os.getenv("DB_SERVICE", "XEPDB1")
