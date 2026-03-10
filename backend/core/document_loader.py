import os
import fitz  # PyMuPDF
import pytesseract
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
# OCR — renderizado con PyMuPDF, sin poppler
# ==========================

def _run_ocr(pdf_path: str) -> str:
    """Renderiza cada página con fitz y ejecuta Tesseract. No usa poppler."""
    text_content = []

    with fitz.open(pdf_path) as doc:
        for page in doc:
            # Renderizar página a imagen (300 DPI equivalente: matrix 300/72 ≈ 4.17)
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)

            # Convertir a numpy array para OpenCV
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )

            processed = _preprocess_image_for_ocr(img)
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