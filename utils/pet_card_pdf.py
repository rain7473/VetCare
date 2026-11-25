"""Exportación A4 del carné público. Las coordenadas siguen el arte de la plantilla."""
from pathlib import Path

from PySide6.QtCore import QIODevice, QLineF, QMarginsF, QPointF, QRectF, QSaveFile, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QImage, QPageSize, QPainter, QPainterPath,
    QPdfWriter, QPen,
)

from config.constants import PET_SEX_DISPLAY
from config.settings import ASSETS_DIR
from utils.images import resolve_photo

_TEMPLATE = ASSETS_DIR / "templates" / "vaccination-card.jpg"
_PAGE = QRectF(0, 0, 1055, 1491)
_NAVY = "#0b304c"
_INK = "#303944"
_MUTED = "#535e6b"
_TABLE_TOP = 986
_MISSING = "Sin registrar"


def _font(size, bold=False, italic=False):
    font = QFont("Segoe UI")
    font.setPixelSize(size)
    font.setStretch(104)
    font.setBold(bold)
    font.setItalic(italic)
    return font


def _wrap_mode(metrics, value, width):
    if any(metrics.horizontalAdvance(word) > width for word in value.split()):
        return Qt.TextWrapAnywhere
    return Qt.TextWordWrap


def _text(painter, box, value, size, color=_INK, *, bold=False, italic=False, center=False):
    value = str(value or _MISSING)
    rect = QRectF(*box)
    align = Qt.AlignVCenter | (Qt.AlignHCenter if center else Qt.AlignLeft)
    font = _font(size, bold, italic)
    while True:
        metrics = QFontMetricsF(font, painter.device())
        flags = align | _wrap_mode(metrics, value, rect.width())
        bounds = metrics.boundingRect(rect, flags, value)
        if size <= 8 or (bounds.width() <= rect.width() and bounds.height() <= rect.height()):
            break
        size -= 1
        font.setPixelSize(size)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(rect, flags, value)


def _portrait(painter, photo):
    if photo.isNull():
        return  # La plantilla ya contiene la huella.
    frame = QRectF(86, 427, 91, 91)
    side = min(photo.width(), photo.height())
    crop = QRectF((photo.width() - side) / 2, (photo.height() - side) / 2, side, side)
    clip = QPainterPath()
    clip.addRoundedRect(frame, 20, 20)
    painter.save()
    painter.setClipPath(clip)
    painter.drawImage(frame, photo, crop)
    painter.restore()


def _profile(painter, pet, photo):
    _text(painter, (100, 239, 870, 74), "Carné de vacunación", 53, _NAVY, bold=True)
    _text(painter, (101, 307, 875, 44),
          "Información de identificación y registro de vacunas de la mascota.", 26, "#757d88")
    _portrait(painter, photo)
    _text(painter, (220, 428, 730, 35), "PACIENTE", 23, _MUTED, bold=True)
    _text(painter, (219, 453, 745, 70), pet.name, 52, _NAVY, bold=True)

    # Símbolo correspondiente al sexo registrado.
    painter.setPen(QPen(QColor("#087e80"), 3, Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    if pet.sex == "MALE":
        painter.drawEllipse(QRectF(733, 587, 27, 27))
        painter.drawLines([QLineF(756, 591, 770, 577), QLineF(758, 577, 770, 577),
                           QLineF(770, 577, 770, 589)])
    elif pet.sex == "FEMALE":
        painter.drawEllipse(QRectF(738, 573, 26, 26))
        painter.drawLines([QLineF(751, 599, 751, 617), QLineF(743, 609, 759, 609)])
    else:
        painter.drawEllipse(QRectF(736, 580, 30, 30))
    for x, y, width, label, value in (
        (178, 560, 181, "ESPECIE", pet.species_name),
        (480, 560, 201, "RAZA", pet.breed_name),
        (799, 560, 185, "SEXO", PET_SEX_DISPLAY.get(pet.sex, pet.sex)),
        (179, 670, 774, "EDAD", pet.age_text()),
    ):
        _text(painter, (x, y, width, 32), label, 21, _MUTED, bold=True)
        _text(painter, (x, y + 28, width, 42), value, 27)


def _vaccine_pages(vaccines, device):
    metrics = QFontMetricsF(_font(24), device)
    rows = []
    height = 0
    for vaccine in vaccines:
        name = vaccine.vaccine_name or _MISSING
        bounds = metrics.boundingRect(QRectF(0, 0, 339, 1000), _wrap_mode(metrics, name, 339), name)
        row_height = min(384, max(47, int(bounds.height()) + 13))
        if rows and height + row_height > 384:
            yield rows
            rows = []
            height = 0
        rows.append((vaccine, row_height))
        height += row_height
    yield rows


def _vaccines(painter, template, rows):
    _text(painter, (164, 829, 810, 65), "Registro de vacunas", 41, _NAVY, bold=True)
    for x, width, title in ((83, 335, "Vacuna"), (460, 239, "Aplicación"),
                            (732, 253, "Próxima dosis")):
        _text(painter, (x, 924, width, 55), title, 26, "#ffffff", bold=True)
    if not rows:
        _text(painter, (54, 988, 947, 74), "No hay vacunas registradas.",
              26, _MUTED, italic=True, center=True)
        return

    height = max(87, sum(h for _, h in rows))
    extra = height - 87
    if extra:
        # Reducir la marca de agua si la tabla ocupa su espacio habitual.
        paw = QRectF(804, 1180, 207, 198)
        paper = QRectF(582, 1180, paw.width(), paw.height())
        free_height = paw.bottom() - (_TABLE_TOP + height + 35)
        if free_height < paw.height():
            painter.drawImage(paw, template, paper)
            if free_height >= 42:
                width = paw.width() * free_height / paw.height()
                target = QRectF(paw.right() - width, paw.bottom() - free_height, width, free_height)
                painter.drawImage(target, template, paw)
        # Alargar solo el relleno, conservando las esquinas y la sombra del pie.
        painter.drawImage(QRectF(0, 1000, 1055, extra), template, QRectF(0, 1000, 1055, 48))
        painter.drawImage(QRectF(0, 1000 + extra, 1055, 108), template, QRectF(0, 1000, 1055, 108))

    top = _TABLE_TOP
    for index, (vaccine, row_height) in enumerate(rows):
        if len(rows) == 1:
            row_height = height
        if index:
            painter.setPen(QPen(QColor("#c8dfe0"), 1))
            painter.drawLine(QPointF(52, top), QPointF(1003, top))
        for x, width, value in (
            (83, 339, vaccine.vaccine_name),
            (460, 230, vaccine.applied_at.strftime("%d/%m/%Y") if vaccine.applied_at else None),
            (732, 252, vaccine.next_due_date.strftime("%d/%m/%Y") if vaccine.next_due_date else None),
        ):
            _text(painter, (x, top + 3, width, row_height - 6), value, 24)
        top += row_height


def export_card_pdf(view, path: str | Path) -> None:
    template = QImage(str(_TEMPLATE))
    if template.isNull():
        raise OSError("No se pudo cargar la plantilla del carné PDF.")
    photo_path = resolve_photo(view.pet.photo_url)
    photo = QImage(str(photo_path)) if photo_path else QImage()
    output = QSaveFile(str(path))
    if not output.open(QIODevice.WriteOnly):
        raise OSError(output.errorString())
    writer = QPdfWriter(output)
    writer.setTitle("Carné de vacunación")
    writer.setCreator("VetCare")
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))
    writer.setResolution(150)
    painter = QPainter(writer)
    if not painter.isActive():
        raise OSError("No se pudo iniciar el carné PDF.")
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        painter.scale(writer.width() / _PAGE.width(), writer.height() / _PAGE.height())
        for index, rows in enumerate(_vaccine_pages(view.vaccines, writer)):
            if index and not writer.newPage():
                raise OSError("No se pudo añadir una página al carné PDF.")
            painter.drawImage(_PAGE, template)
            _profile(painter, view.pet, photo)
            _vaccines(painter, template, rows)
            _text(painter, (310, 1400, 435, 42), "VetCare · Sistema de gestión veterinaria",
                  21, _MUTED, center=True)
    finally:
        painter.end()
    if not output.commit():
        raise OSError(output.errorString())
