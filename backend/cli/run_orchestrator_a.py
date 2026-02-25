import os
import re
import subprocess
import json
from collections import defaultdict

INPUT_FOLDER = "temp_inputs"
OUTPUT_FOLDER = "output"


# =====================================================
# 1️⃣ Detectar periodo desde nombre de archivo
# =====================================================

def extract_period_from_filename(filename: str) -> str:
    """
    Devuelve periodo_iso en formato YYYY-MM detectado desde el nombre del archivo
    Ejemplos válidos:
        05-25
        052025
        06-25
        062025
    """
    match = re.search(r"(\d{2})[-_]?(\d{2,4})", filename)

    if not match:
        raise ValueError(f"No se pudo detectar período en: {filename}")

    mes = match.group(1)
    anio = match.group(2)

    if len(anio) == 2:
        anio = "20" + anio

    return f"{anio}-{mes}"


# =====================================================
# 2️⃣ Agrupar PDFs por periodo
# =====================================================

def group_pdfs_by_period(folder: str):
    period_groups = defaultdict(list)

    for file in os.listdir(folder):
        if file.lower().endswith(".pdf"):
            periodo = extract_period_from_filename(file)
            period_groups[periodo].append(file)

    return period_groups


# =====================================================
# 3️⃣ Sobrescribir periodo en JSON generados
# =====================================================

def override_period_in_json(output_folder: str, periodo: str):
    """
    Busca JSON del período y sobrescribe metadata.periodo_iso
    """
    for file in os.listdir(output_folder):
        if not file.endswith(".json"):
            continue

        file_path = os.path.join(output_folder, file)

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "metadata" in data:
            data["metadata"]["periodo_iso"] = periodo

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)


# =====================================================
# 4️⃣ Ejecutar parser para un periodo específico
# =====================================================

def run_parser_for_period(periodo: str, files: list):
    print(f"\n==============================")
    print(f"Procesando PERIODO: {periodo}")
    print("==============================")

    # Ejecuta parser sobre toda la carpeta
    subprocess.run([
        "python",
        "run_parser.py",
        "--input", INPUT_FOLDER,
        "--output", OUTPUT_FOLDER
    ], check=True)

    # Sobrescribir periodo
    override_period_in_json(OUTPUT_FOLDER, periodo)


# =====================================================
# 5️⃣ Ejecutar normalizer
# =====================================================

def run_normalizer():
    subprocess.run([
        "python",
        "run_normalizer.py"
    ], check=True)


# =====================================================
# 6️⃣ Ejecutar consolidator
# =====================================================

def run_consolidator():
    subprocess.run([
        "python",
        "run_consolidator.py"
    ], check=True)


# =====================================================
# MAIN
# =====================================================

def main():

    if not os.path.exists(INPUT_FOLDER):
        print(f"❌ No existe carpeta {INPUT_FOLDER}")
        return

    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)

    period_groups = group_pdfs_by_period(INPUT_FOLDER)

    if not period_groups:
        print("❌ No se encontraron PDFs.")
        return

    print("\nPDFs agrupados por periodo:")
    for periodo, files in period_groups.items():
        print(f"{periodo} -> {len(files)} archivos")

    # Procesar cada periodo
    for periodo, files in period_groups.items():

        run_parser_for_period(periodo, files)

        run_normalizer()

        run_consolidator()

    print("\n✅ Orchestrator_A finalizado correctamente.")


if __name__ == "__main__":
    main()