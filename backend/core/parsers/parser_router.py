import re
from backend.core.utils.pdf_text import extract_text, clean_lines

from backend.core.parsers.asiento_parser import parse as parse_asiento
from backend.core.parsers.borrador_parser import parse as parse_borrador
from backend.core.parsers.f931_parser import parse as parse_f931


def detect_document_type(lines: list[str]) -> str:
    full_text = "\n".join(lines)

    # BORRADOR
    if re.search(r"Declaraci[oó]n en l[ií]nea", full_text, re.IGNORECASE):
        return "borrador"

    # F931 oficial
    if re.search(r"I\s*-\s*REGIMEN NACIONAL DE SEGURIDAD SOCIAL", full_text, re.IGNORECASE):
        return "f931"

    # ASIENTO
    if re.search(r"ASIENTO CONTABLE AL", full_text, re.IGNORECASE):
        return "asiento"

    return "unknown"


def parse_document(pdf_path: str) -> dict:
    lines, _ = extract_text(pdf_path)
    lines_clean = clean_lines(lines)

    doc_type = detect_document_type(lines_clean)

    if doc_type == "borrador":
        return parse_borrador(pdf_path)

    if doc_type == "f931":
        return parse_f931(pdf_path)

    if doc_type == "asiento":
        return parse_asiento(pdf_path)

    raise ValueError("Tipo de documento no reconocido")