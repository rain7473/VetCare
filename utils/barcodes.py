"""Códigos locales: conservar el valor del fabricante y renderizar Code 128.

Los números de 12/13 dígitos con checksum válido se imprimen como UPC-A/EAN-13.
Los demás valores imprimibles se representan en Code 128, sin corregirlos ni
añadir dígitos (incluidos los códigos históricos que ya existen en Oracle).
"""

from uuid import uuid4

from barcode import Code128, EAN13, UPCA

from utils.validators import ValidationError


def validate_barcode(raw: str, *, required: bool = False) -> str | None:
    code = (raw or "").strip()
    if not code:
        if required:
            raise ValidationError("El código de barras es obligatorio.")
        return None
    if len(code) > 100 or any(not 32 <= ord(char) <= 126 for char in code):
        raise ValidationError("El código debe contener hasta 100 caracteres ASCII imprimibles.")
    return code


def new_internal_code() -> str:
    # UUID completo; no depende del reloj, del stock ni de un contador local.
    return "VC" + uuid4().hex.upper()


def barcode_symbol(raw: str):
    code = validate_barcode(raw, required=True)
    if code.isascii() and code.isdigit():
        if len(code) == 13 and EAN13(code[:-1]).get_fullcode() == code:
            return EAN13(code[:-1])
        if len(code) == 12 and UPCA(code[:-1]).get_fullcode() == code:
            return UPCA(code[:-1])
    return Code128(code)


def equivalent_upc_ean(code: str) -> str | None:
    """Algunos lectores entregan UPC-A como EAN-13 con un cero inicial."""
    if not code.isascii() or not code.isdigit():
        return None
    if len(code) == 12 and UPCA(code[:-1]).get_fullcode() == code:
        return "0" + code
    if len(code) == 13 and code.startswith("0") and EAN13(code[:-1]).get_fullcode() == code:
        return code[1:]
    return None
