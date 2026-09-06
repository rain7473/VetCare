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

# Nombres de rol para mostrar en la interfaz (los códigos viven en ROLES).
ROLE_DISPLAY_NAMES = {
    "ADMIN": "Administrador",
    "RECEPTION": "Recepción",
    "VETERINARIAN": "Veterinario/a",
    "SALES": "Ventas",
}

# Valores de PETS.SEX y PETS.STATUS (checks en Oracle) → texto de interfaz.
PET_SEX_DISPLAY = {
    "MALE": "Macho",
    "FEMALE": "Hembra",
    "UNKNOWN": "Desconocido",
}

PET_STATUS_DISPLAY = {
    "ACTIVE": "Activa",
    "DECEASED": "Fallecida",
    "INACTIVE": "Inactiva",
}

# Niveles de prioridad de triaje (TRIAGES.PRIORITY_LEVEL, check 1..4).
TRIAGE_PRIORITY_DISPLAY = {
    1: "P1 · Crítico",
    2: "P2 · Urgente",
    3: "P3 · Prioritario",
    4: "P4 · Normal",
}

# Estados de consciencia registrados en triaje (VARCHAR2 libre; catálogo app).
CONSCIOUSNESS_DISPLAY = {
    "ALERT": "Alerta",
    "DEPRESSED": "Deprimido/letárgico",
    "UNCONSCIOUS": "Inconsciente",
}

# Estados de CONSULTATIONS.STATUS (check en Oracle) → texto de interfaz.
CONSULTATION_STATUS_DISPLAY = {
    "DRAFT": "Borrador",
    "FINALIZED": "Finalizada",
    "SEALED": "Sellada",
}

# Estados de SURGICAL_PROCEDURES.STATUS (check en Oracle) → texto de interfaz.
SURGERY_STATUS_DISPLAY = {
    "PLANNED": "Planificada",
    "IN_PROGRESS": "En curso",
    "COMPLETED": "Completada",
    "CANCELLED": "Cancelada",
}

# Estados de APPOINTMENTS.STATUS (check en Oracle) → texto de interfaz.
APPOINTMENT_STATUS_DISPLAY = {
    "SCHEDULED": "Programada",
    "CONFIRMED": "Confirmada",
    "IN_ATTENTION": "En atención",
    "COMPLETED": "Completada",
    "CANCELLED": "Cancelada",
    "NO_SHOW": "No asistió",
}


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
