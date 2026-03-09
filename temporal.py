from pathlib import Path
from backend.core.document_loader import load_document

# Ruta del PDF
pdf_path = Path(
    r"C:\Users\franl\Desktop\auditoria\proyecto\inputs\FOLC\FOLC- F931 07-2025 BORRADOR.pdf"
)

# Verificar que el archivo exista
if not pdf_path.exists():
    raise FileNotFoundError(f"No existe el archivo: {pdf_path}")

text, used_ocr = load_document(str(pdf_path))

print("OCR usado:", used_ocr)
print("\n--- TEXTO EXTRAÍDO (primeros 1000 caracteres) ---\n")
print(text[:1000])