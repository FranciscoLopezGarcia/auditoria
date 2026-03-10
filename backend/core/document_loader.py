import os
import fitz  # PyMuPDF
import pytesseract
from pdf2image import convert_from_path
import cv2
import numpy as np
from pathlib import Path
from typing import Tuple

# ==========================
# RUTAS A DEPS (relativas al proyecto)
# ==========================

# Raíz del proyecto (donde está app.py)
# document_loader.py está en backend/core/ → subimos 2 niveles
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Ruta a Tesseract dentro de deps
pytesseract.pytesseract.tesseract_cmd = str(
    _PROJECT_ROOT / "deps" / "tesseract" / "tesseract.exe"
)

# Ruta a Poppler dentro de deps
POPPLER_PATH = str(
    _PROJECT_ROOT / "deps" / "poppler" / "poppler-25.07.0" / "Library" / "bin"
)

# En Windows, registrar la carpeta de poppler para que Python encuentre sus DLLs
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(POPPLER_PATH)

# Umbral mínimo de texto para considerar que el PDF tiene capa de texto
TEXT_THRESHOLD = 300


# ==========================
# EXTRACCIÓN NATIVA
# ==========================

def _extract_text_native(pdf_path: str) -> str:
    """Extrae texto usando PyMuPDF."""
    text_content = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text_content.append(page.get_text())
    return "\n".join(text_content)


def _has_text_layer(text: str) -> bool:
    """Determina si el PDF tiene texto suficiente."""
    if not text:
        return False
    return len(text.strip()) > TEXT_THRESHOLD


# ==========================
# PREPROCESAMIENTO OCR
# ==========================

def _preprocess_image_for_ocr(image):
    """Preprocesamiento básico para mejorar OCR."""
    img = np.array(image)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Binarización adaptativa
    thresh = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2
    )

    return thresh


# ==========================
# OCR
# ==========================

def _run_ocr(pdf_path: str) -> str:
    """Ejecuta OCR con Tesseract sobre cada página."""
    text_content = []

    # Usamos fitz para contar páginas y saltear el pdfinfo de pdf2image
    with fitz.open(pdf_path) as _doc:
        num_pages = len(_doc)

    pages = convert_from_path(
        pdf_path,
        dpi=300,
        poppler_path=POPPLER_PATH,
        first_page=1,
        last_page=num_pages,
    )

    for page in pages:
        processed = _preprocess_image_for_ocr(page)
        ocr_text = pytesseract.image_to_string(processed, lang="spa")
        text_content.append(ocr_text)

    return "\n".join(text_content)


# ==========================
# API PRINCIPAL
# ==========================

def load_document(pdf_path: str) -> Tuple[str, bool]:

    native_text = _extract_text_native(pdf_path)

    if _has_text_layer(native_text):
        print(f"[document_loader] {pdf_path} → USANDO TEXTO NATIVO")
        return native_text, False

    print(f"[document_loader] {pdf_path} → USANDO OCR")
    ocr_text = _run_ocr(pdf_path)
    return ocr_text, True