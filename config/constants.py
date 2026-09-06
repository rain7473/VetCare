"""Constantes de la aplicación VetCare.

Aquí viven la identidad de la aplicación y la paleta de colores oficial.
Cualquier ajuste visual global debe hacerse en este archivo y en
``assets/styles/main.qss``, nunca con colores sueltos en las vistas.
"""

APP_NAME = "VetCare"
APP_TAGLINE = "Cuidamos su bienestar"
APP_DESCRIPTION = "Sistema de Gestión Integral Veterinaria"
APP_FOOTER_MOTTO = "Animales más sanos, vidas más felices"
APP_VERSION = "0.1.0"


class Colors:
    """Paleta oficial de VetCare (identidad teal / turquesa / mint)."""

    PRIMARY_DARK = "#006978"
    PRIMARY = "#008FA3"
    SECONDARY = "#14B8C4"
    MINT = "#63D7B0"
    BACKGROUND = "#F5FAFC"
    CARD = "#FFFFFF"
    TEXT_DARK = "#102A43"
    MUTED = "#6B8194"

    # Estados
    SUCCESS = "#2FB380"
    INFO = "#0E9CD9"
    WARNING = "#F2A93B"
    ERROR = "#E5484D"
