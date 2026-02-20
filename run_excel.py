import json
from pathlib import Path
from excel.excel_loader import ExcelLoader


# --------------------------------------------------
# RUTAS HARDCODEADAS
# --------------------------------------------------

BASE_DIR = Path(__file__).parent

OUTPUT_DIR = BASE_DIR / "output"

EXCEL_PATH = r"C:\Users\franl\Desktop\auditoria\Px Laboral 2025.xlsx"

# --------------------------------------------------
# UTIL
# --------------------------------------------------

def get_latest_consolidated_json():
    files = list(OUTPUT_DIR.glob("consolidated_*.json"))
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

    print(f"Periodo detectado: {data['periodo_iso']}")

    loader = ExcelLoader(
        template_path=EXCEL_PATH,
        consolidated_json=data
    )

    print("Actualizando Excel...")
    loader.update_excel(EXCEL_PATH)

    print("\n✓ Excel actualizado correctamente.")


if __name__ == "__main__":
    main()