import re
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional
from collections import defaultdict

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

# Pipeline
from backend.core.pipeline import process_period


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Px Laboral Automation API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def cleanup_temp_dir(dir_path: str):
    try:
        shutil.rmtree(dir_path)
    except Exception as e:
        print(f"Error al limpiar directorio temporal {dir_path}: {e}")


def detect_period(filename: str) -> Optional[str]:
    """
    Detecta periodo desde nombre del archivo.

    Ejemplos válidos:
        F931 07-2025
        FOLC- F931 07-2025 BORRADOR.pdf
        asiento_072025.pdf
    """
    name = filename.lower()

    # 07-2025
    m = re.search(r"(0[1-9]|1[0-2])[-_](20\d{2})", name)
    if m:
        return f"{m.group(2)}-{m.group(1)}"

    # 072025
    m = re.search(r"(0[1-9]|1[0-2])(20\d{2})", name)
    if m:
        return f"{m.group(2)}-{m.group(1)}"

    return None


def group_pdfs_by_period(paths: List[Path]):
    groups = defaultdict(list)

    for p in paths:
        period = detect_period(p.name)
        if not period:
            raise ValueError(f"No se pudo detectar período en: {p.name}")

        groups[period].append(p)

    return groups


# ---------------------------------------------------------
# Frontend / Static
# ---------------------------------------------------------

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(BASE_DIR / "index.html")


# Sirve archivos estáticos como /static/style.css y /static/main.js
STATIC_DIR = BASE_DIR

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------
# API
# ---------------------------------------------------------

@app.post("/process")
def process_endpoint(
    files: List[UploadFile] = File(...),
    existing_excel: Optional[UploadFile] = File(None),
):
    if not files:
        raise HTTPException(status_code=400, detail="No se enviaron archivos.")

    temp_dir = tempfile.mkdtemp(prefix="px_upload_")
    temp_dir_path = Path(temp_dir)

    try:
        # -------------------------------------------------
        # Guardar PDFs
        # -------------------------------------------------
        pdf_paths = []

        for file in files:
            file_path = temp_dir_path / file.filename
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            pdf_paths.append(file_path)

        # -------------------------------------------------
        # Guardar Excel existente si viene
        # -------------------------------------------------
        excel_input_path = None

        if existing_excel and existing_excel.filename:
            excel_file_path = temp_dir_path / existing_excel.filename
            with open(excel_file_path, "wb") as buffer:
                shutil.copyfileobj(existing_excel.file, buffer)

            excel_input_path = excel_file_path

        # -------------------------------------------------
        # Agrupar PDFs por período
        # -------------------------------------------------
        groups = group_pdfs_by_period(pdf_paths)

        # ordenar periodos cronológicamente
        ordered_periods = sorted(groups.keys())

        excel_path = excel_input_path

        # -------------------------------------------------
        # Ejecutar pipeline por período
        # -------------------------------------------------
        for period in ordered_periods:
            print(f"\n===== Procesando periodo {period} =====")

            excel_path = process_period(
                pdf_paths=groups[period],
                period=period,
                existing_excel=excel_path,
            )

        # -------------------------------------------------
        # Validar resultado
        # -------------------------------------------------
        if not excel_path or not Path(excel_path).exists():
            raise HTTPException(
                status_code=500,
                detail="El pipeline no generó el Excel de salida."
            )

        # -------------------------------------------------
        # Descargar Excel
        # -------------------------------------------------
        return FileResponse(
            path=excel_path,
            filename=Path(excel_path).name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            background=BackgroundTask(cleanup_temp_dir, temp_dir)
        )

    except HTTPException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))