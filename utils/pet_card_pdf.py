"""Diseño y exportación del carné público de vacunación."""
from html import escape
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrinter

from config.constants import PET_SEX_DISPLAY
from utils.branding import SYMBOL_RESOURCE_URL, add_symbol_resource


def card_html(view) -> str:
    pet = view.pet
    def safe(value):
        return escape(str(value)) if value else "Sin registrar"

    rows = []
    for vaccine in view.vaccines:
        applied = vaccine.applied_at.strftime("%d/%m/%Y") if vaccine.applied_at else "Sin registrar"
        next_date = vaccine.next_due_date.strftime("%d/%m/%Y") if vaccine.next_due_date else "Sin registrar"
        rows.append(f"<tr><td>{safe(vaccine.vaccine_name)}</td><td>{applied}</td><td>{next_date}</td></tr>")
    if not rows:
        rows.append('<tr><td colspan="3" class="empty">No hay vacunas registradas.</td></tr>')
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #102a43; font-size: 10pt; }}
    table {{ width: 100%; border-collapse: collapse; }}
    .brand td {{ vertical-align: middle; padding: 3px; }}
    .logo {{ width: 62px; }} .brand-name {{ font-size: 23pt; font-weight: bold; color: #006978; }}
    .caption {{ font-size: 9pt; color: #6b8194; }}
    .heading {{ margin: 20px 0 6px; font-size: 20pt; color: #102a43; font-weight: bold; }}
    .lead {{ color: #6b8194; font-size: 10pt; margin-bottom: 15px; }}
    .accent {{ border-top: 3px solid #14b8c4; margin: 14px 0; }}
    .profile {{ background: #edf8fa; border: 1px solid #d6edf0; }}
    .profile td {{ padding: 10px 13px; vertical-align: top; }}
    .name {{ font-size: 18pt; color: #006978; font-weight: bold; }}
    .label {{ color: #6b8194; font-size: 8pt; font-weight: bold; }}
    .value {{ color: #102a43; font-size: 10pt; }}
    .section {{ margin: 21px 0 8px; font-size: 13pt; font-weight: bold; color: #006978; }}
    .vaccines th {{ background: #dff1f3; color: #006978; padding: 9px; text-align: left; border: 1px solid #d6e9ec; }}
    .vaccines td {{ padding: 9px; border: 1px solid #d6e9ec; }}
    .empty {{ color: #6b8194; text-align: center; }}
    .footer {{ color: #6b8194; font-size: 8pt; margin-top: 25px; border-top: 1px solid #d6e9ec; padding-top: 10px; }}
    </style></head><body>
    <table class="brand"><tr><td class="logo"><img src="{SYMBOL_RESOURCE_URL.toString()}" width="52" height="50"></td>
    <td><span class="brand-name">VetCare</span><br><span class="caption">Cuidamos su bienestar</span></td></tr></table>
    <div class="accent"></div><div class="heading">Carné de vacunación</div>
    <div class="lead">Información de identificación y registro de vacunas de la mascota.</div>
    <table class="profile" width="100%"><tr><td colspan="3"><span class="label">PACIENTE</span><br><span class="name">{safe(pet.name)}</span></td></tr>
    <tr><td><span class="label">ESPECIE</span><br><span class="value">{safe(pet.species_name)}</span></td>
    <td><span class="label">RAZA</span><br><span class="value">{safe(pet.breed_name)}</span></td>
    <td><span class="label">SEXO</span><br><span class="value">{safe(PET_SEX_DISPLAY.get(pet.sex, pet.sex))}</span></td></tr>
    <tr><td colspan="3"><span class="label">EDAD</span><br><span class="value">{safe(pet.age_text())}</span></td></tr></table>
    <div class="section">Registro de vacunas</div><table class="vaccines">
    <tr><th width="45%">Vacuna</th><th width="27%">Aplicación</th><th width="28%">Próxima dosis</th></tr>{''.join(rows)}</table>
    <div class="footer">VetCare · Sistema de gestión veterinaria</div></body></html>"""


def export_card_pdf(view, path: str | Path) -> None:
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageMargins(QMarginsF(14, 14, 14, 14))
    document = QTextDocument()
    add_symbol_resource(document)
    document.setHtml(card_html(view))
    document.print_(printer)
    target = Path(path)
    if not target.is_file() or target.stat().st_size == 0:
        raise OSError("No se pudo crear el carné PDF.")
