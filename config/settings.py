"""Settings de VetCare.

Carga las variables de entorno desde ``.env`` (nunca credenciales en código)
y expone rutas base del proyecto. La conexión Oracle que consume estas
variables vive en ``database/connection.py``.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Rutas base del proyecto
# El ejecutable conserva .env y los datos junto a VetCare.exe. Los recursos
# incluidos por PyInstaller se extraen a _MEIPASS si no hay assets externos.
BASE_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent
)
_bundled_assets = Path(getattr(sys, "_MEIPASS", BASE_DIR)) / "assets"
ASSETS_DIR = BASE_DIR / "assets"
if not ASSETS_DIR.is_dir():
    ASSETS_DIR = _bundled_assets
STYLES_FILE = ASSETS_DIR / "styles" / "main.qss"

# Variables de entorno (.env en la raíz del proyecto)
load_dotenv(BASE_DIR / ".env")

DB_USER = os.getenv("DB_USER", "VETCARE")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "1521"))
DB_SERVICE = os.getenv("DB_SERVICE", "XEPDB1")
