import os
import shutil
import subprocess
import json
from glob import glob
import sys

OUTPUT_FOLDER = "output"
ARCHIVE_FOLDER = "archive"


def get_consolidated_files(folder: str):
    pattern = os.path.join(folder, "consolidated_*.json")
    return sorted(glob(pattern))


def validate_consolidated(file_path: str):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    required_keys = ["schema_version", "periodo_iso", "canonical"]

    for key in required_keys:
        if key not in data:
            raise ValueError(f"{file_path} inválido: falta {key}")

    return data["periodo_iso"]


def run_batch_excel():
    subprocess.run(
        [sys.executable, "run_batch_excel.py"],
        check=True
    )


def archive_consolidated():
    os.makedirs(ARCHIVE_FOLDER, exist_ok=True)
    for file in get_consolidated_files(OUTPUT_FOLDER):
        shutil.move(
            file,
            os.path.join(ARCHIVE_FOLDER, os.path.basename(file))
        )


def cleanup_intermediate_json():
    for file in os.listdir(OUTPUT_FOLDER):
        if file.endswith(".json"):
            os.remove(os.path.join(OUTPUT_FOLDER, file))


def main():

    if not os.path.exists(OUTPUT_FOLDER):
        print("❌ No existe carpeta output.")
        return

    consolidated_files = get_consolidated_files(OUTPUT_FOLDER)

    if not consolidated_files:
        print("❌ No se encontraron consolidated_*.json")
        return

    print("\nConsolidados detectados:")
    for file in consolidated_files:
        print("-", os.path.basename(file))

    print("\nValidando integridad...")

    periodos = []
    for file in consolidated_files:
        periodo = validate_consolidated(file)
        periodos.append(periodo)

    print("Períodos listos para carga Excel:", periodos)

    print("\nEjecutando run_batch_excel.py...")
    run_batch_excel()

    print("\nArchivando JSON consolidados...")
    archive_consolidated()

    print("\nLimpiando JSON intermedios...")
    cleanup_intermediate_json()

    print("\n✅ Orchestrator_B finalizado correctamente.")


if __name__ == "__main__":
    main()