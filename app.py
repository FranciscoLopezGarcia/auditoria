import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask

# Importar el pipeline central
from backend.core.pipeline import process_period

app = FastAPI(title="Px Laboral Automation API")

# Habilitar CORS por si el frontend corre en otro puerto durante desarrollo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def cleanup_temp_dir(dir_path: str):
    """Elimina de forma segura la carpeta temporal una vez finalizado el uso."""
    try:
        shutil.rmtree(dir_path)
    except Exception as e:
        print(f"Error al limpiar directorio temporal {dir_path}: {e}")


@app.post("/process")
def process_endpoint(
    files: List[UploadFile] = File(...),
    existing_excel: Optional[UploadFile] = File(None),
):
    """
    Recibe múltiples PDFs (e.g. F931, Borrador y Asiento), los guarda en 
    una carpeta aislada, los procesa a través del core pipeline, y 
    devuelve el archivo Excel resultante como descarga directa.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No se enviaron archivos.")

    # Guardarlos en una carpeta temporal aislada
    temp_dir = tempfile.mkdtemp(prefix="px_upload_")
    temp_dir_path = Path(temp_dir)

    try:
        pdf_paths = []
        for file in files:
            file_path = temp_dir_path / file.filename
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            pdf_paths.append(file_path)

        # Si viene un Excel existente, guardarlo en el mismo temp_dir
        excel_input_path = None
        if existing_excel and existing_excel.filename:
            excel_file_path = temp_dir_path / existing_excel.filename
            with open(excel_file_path, "wb") as buffer:
                shutil.copyfileobj(existing_excel.file, buffer)
            excel_input_path = excel_file_path

        # Invocamos el pipeline core
        # Se asume un 'period' por defecto, si es requerido.
        excel_path = process_period(
            pdf_paths=pdf_paths,
            period="2025-05",
            existing_excel=excel_input_path,
        )
        
        if not excel_path or not Path(excel_path).exists():
            raise HTTPException(
                status_code=500, 
                detail="El pipeline falló y no generó el archivo Excel de salida."
            )

        # Devolver el archivo Excel como FileResponse
        # Usamos un BackgroundTask para borrar la carpeta temp luego de que termine la descarga
        return FileResponse(
            path=excel_path,
            filename=Path(excel_path).name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            background=BackgroundTask(cleanup_temp_dir, temp_dir)
        )

    except HTTPException:
        # Si ya se levantó un HTTPException, limpiar carpeta temporal y propagar
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    except Exception as e:
        # En caso de otro error, asegurar la limpieza y devolver un 500 limpio
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))