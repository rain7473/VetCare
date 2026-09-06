"""Utilidades de imágenes (fotos de mascotas).

Las fotos se copian redimensionadas a ``data/pet_photos/`` (carpeta
local fuera de git); en Oracle solo se guarda la ruta relativa.
"""

import logging
from pathlib import Path

from PIL import Image

from config.settings import BASE_DIR
from utils.validators import ValidationError

logger = logging.getLogger(__name__)

PET_PHOTOS_DIR = BASE_DIR / "data" / "pet_photos"
_MAX_SIDE = 512


def save_pet_photo(source_path: str, key: str) -> str:
    """Valida, redimensiona y guarda una foto; devuelve la ruta relativa.

    Raises:
        ValidationError: si el archivo no es una imagen válida.
    """
    source = Path(source_path)
    if not source.exists():
        raise ValidationError("El archivo de foto seleccionado no existe.")

    try:
        with Image.open(source) as img:
            img = img.convert("RGB")
            img.thumbnail((_MAX_SIDE, _MAX_SIDE))
            PET_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
            target = PET_PHOTOS_DIR / f"{key}.jpg"
            img.save(target, "JPEG", quality=88)
    except (OSError, ValueError) as exc:
        logger.warning("Foto inválida (%s): %s", source, exc)
        raise ValidationError("El archivo seleccionado no es una imagen válida.") from exc

    return str(target.relative_to(BASE_DIR))


def resolve_photo(photo_url: str | None) -> Path | None:
    """Ruta absoluta de una foto guardada, si existe."""
    if not photo_url:
        return None
    path = Path(photo_url)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path if path.exists() else None
