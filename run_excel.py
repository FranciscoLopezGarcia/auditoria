import json
from pathlib import Path
from excel.excel_loader import ExcelLoader


# --------------------------------------------------
# RUTAS
# --------------------------------------------------

BASE_DIR = Path(__file__).parent
JSON_DIR = BASE_DIR / "output"

# Template: el Excel original (read-only, no se toca)
TEMPLATE_PATH = r"C:\Users\franl\Desktop\auditoria\Px Laboral 2025.xlsx"

# Output: donde se guarda el resultado
OUTPUT_DIR = BASE_DIR / "output"


# --------------------------------------------------
# UTIL
# --------------------------------------------------

def get_latest_consolidated_json():
    files = list(JSON_DIR.glob("consolidated_*.json"))
    if not files:
        raise FileNotFoundError("No se encontró ningún consolidated_*.json en /output")
    files.sort()
    return files[-1]


def main():

    print("\nBuscando JSON consolidado...")
    json_path = get_latest_consolidated_json()
    print(f"✓ Usando: {json_path.name}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    periodo = data["periodo_iso"]
    print(f"Periodo detectado: {periodo}")

    # Nombre del output: Px_Laboral_{periodo}.xlsx
    output_filename = f"Px_Laboral_{periodo}.xlsx"
    output_path = OUTPUT_DIR / output_filename

    loader = ExcelLoader(
        template_path=TEMPLATE_PATH,
        consolidated_json=data
    )

    print("Actualizando Excel...")
    loader.update_excel(str(output_path))

    print(f"\n✓ Excel generado: {output_path}")


if __name__ == "__main__":
    main()