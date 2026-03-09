import fitz  # PyMuPDF
import pytesseract
from pdf2image import convert_from_path
import cv2
import numpy as np
from typing import Tuple

# ==========================
# CONFIGURACIÓN EXPLÍCITA
# ==========================

# Ruta a Tesseract (ajustada a tu máquina)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Ruta a Poppler (ajustada a tu máquina)
POPPLER_PATH = r"C:\poppler\poppler-25.12.0\Library\bin"

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

    pages = convert_from_path(
        pdf_path,
        dpi=300,
        poppler_path=POPPLER_PATH
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