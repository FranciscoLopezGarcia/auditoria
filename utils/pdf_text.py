import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extracción de texto
# ---------------------------------------------------------------------------

def extract_text_pdfplumber(pdf_path: str) -> tuple[list[str], int]:
    """
    Extrae el texto de cada página como lista de líneas.
    Retorna (lineas, num_paginas).

    layout=True + x_tolerance=3 ayuda a mantener columnas separadas.
    """
    import pdfplumber

    lines = []
    num_pages = 0
    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            lines.extend(text.splitlines())
    return lines, num_pages


def extract_text_pymupdf(pdf_path: str) -> tuple[list[str], int]:
    """
    Fallback con pymupdf (fitz).
    Devuelve el mismo formato que extract_text_pdfplumber.
    """
    import fitz  # pymupdf

    lines = []
    num_pages = 0
    with fitz.open(pdf_path) as doc:
        num_pages = len(doc)
        for page in doc:
            text = page.get_text("text") or ""
            lines.extend(text.splitlines())
    return lines, num_pages


def extract_text(pdf_path: str) -> tuple[list[str], int]:
    """
    Intenta pdfplumber primero; si falla, cae a pymupdf.
    """
    try:
        return extract_text_pdfplumber(pdf_path)
    except ImportError:
        logger.warning("pdfplumber no disponible, usando pymupdf como fallback")
        return extract_text_pymupdf(pdf_path)
    except Exception as e:
        logger.error(f"Error con pdfplumber: {e}. Intentando pymupdf...")
        return extract_text_pymupdf(pdf_path)


def extract_words_with_coords(pdf_path: str) -> list[dict]:
    """
    Extrae palabras con sus coordenadas (necesario para parsear columnas del asiento).
    Retorna lista de dicts: {text, x0, y0, x1, y1, page_num}
    """
    import pdfplumber

    words = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_words = page.extract_words(x_tolerance=3, y_tolerance=3) or []
            for w in page_words:
                words.append({
                    "text": w["text"],
                    "x0": w["x0"],
                    "y0": w["top"],
                    "x1": w["x1"],
                    "y1": w["bottom"],
                    "page_num": page_num,
                })
    return words


# ---------------------------------------------------------------------------
# Normalización de números argentinos
# ---------------------------------------------------------------------------

# Patrón: captura números con formato argentino
# Ejemplos válidos: 27.380.973,46  /  642.515,41  /  -  /  $ -  /  0,00
_AR_NUMBER_PATTERN = re.compile(
    r"^[$ ]*"          # símbolo $ opcional con espacios
    r"(-?)"            # signo negativo opcional
    r"[\s]*"
    r"([\d]{1,3}(?:\.[\d]{3})*(?:,[\d]{0,2})?|[\d]+(?:,[\d]{0,2})?)"
    r"$"
)


def normalize_number(raw: str) -> Optional[float]:
    """
    Convierte un importe en formato argentino a float estándar.

    Ejemplos:
        "27.380.973,46"  ->  27380973.46
        "$ 642.515,41"   ->  642515.41
        "$ -"            ->  None   (campo vacío/sin valor)
        "-"              ->  None
        ""               ->  None
        "0,00"           ->  0.0

    Retorna None cuando el campo está vacío o es explícitamente "-".
    Esto permite distinguir "no aplica" de "es cero".
    """
    if not raw:
        return None

    cleaned = raw.strip().replace(" ", "")

    # Casos de campo vacío
    if cleaned in ("", "-", "$-", "$", "—"):
        return None

    # Quitar símbolo $ si está pegado
    cleaned = cleaned.lstrip("$").strip()

    if cleaned in ("", "-", "—"):
        return None

    # Capturar signo
    negative = cleaned.startswith("-")
    cleaned = cleaned.lstrip("-").strip()

    # Formato argentino: puntos como separador de miles, coma como decimal
    # 27.380.973,46 -> 27380973.46
    if "," in cleaned:
        # Quitar puntos de miles, reemplazar coma decimal por punto
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        # Sin coma: puede ser entero con puntos de miles (ej: "27.380.962")
        # Heurística: si hay más de un punto, son miles; si hay uno y 3 dígitos después = miles
        parts = cleaned.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            cleaned = cleaned.replace(".", "")
        # Si no, dejarlo como está (podría ser decimal con punto ya)

    try:
        value = float(cleaned)
        return -value if negative else value
    except ValueError:
        logger.warning(f"No se pudo convertir a número: '{raw}' -> '{cleaned}'")
        return None


# ---------------------------------------------------------------------------
# Helpers de regex
# ---------------------------------------------------------------------------

def extract_periodo_from_filename(filename: str) -> Optional[str]:
    """
    Intenta detectar el período desde el nombre de archivo.
    Soporta formatos: 052025, 05-25, 05_2025, 052025, etc.

    Retorna "MM/YYYY" o None.
    """
    name = Path(filename).stem

    # Patrón MM-YY o MM_YY o MM-YYYY
    m = re.search(r"[_\-](\d{2})[_\-](\d{2,4})", name)
    if m:
        mes = m.group(1)
        anio = m.group(2)
        if len(anio) == 2:
            anio = "20" + anio
        return f"{mes}/{anio}"

    # Patrón MMYYYY al final del nombre
    m = re.search(r"(\d{2})(\d{4})$", name)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    return None


def find_value_after_label(lines: list[str], label_pattern: str,
                            search_same_line: bool = True,
                            next_lines: int = 1) -> Optional[str]:
    """
    Busca un label (regex) en las líneas y retorna el primer número que aparece
    en la misma línea o en las siguientes `next_lines` líneas.

    Útil para parsear pares label:valor en documentos semi-estructurados.
    """
    label_re = re.compile(label_pattern, re.IGNORECASE)
    number_re = re.compile(r"[\d.,]+")

    for i, line in enumerate(lines):
        if label_re.search(line):
            # Buscar en la misma línea primero
            if search_same_line:
                nums = number_re.findall(line.split(label_re.split(line)[0])[-1])
                # Tomar el último número de la línea (suele ser el importe)
                candidate = nums[-1] if nums else None
                if candidate:
                    return candidate

            # Buscar en líneas siguientes
            for j in range(1, next_lines + 1):
                if i + j < len(lines):
                    nums = number_re.findall(lines[i + j])
                    if nums:
                        return nums[-1]
    return None


def clean_lines(lines: list[str]) -> list[str]:
    """Elimina líneas vacías y espacios extra."""
    return [l.strip() for l in lines if l.strip()]