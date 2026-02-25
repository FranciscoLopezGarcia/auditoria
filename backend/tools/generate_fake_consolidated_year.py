import json
import copy
from pathlib import Path

BASE_FILE = "output/consolidated_2025-05.json"
OUTPUT_DIR = Path("output")

def load_base():
    with open(BASE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def modify_values(data, month_offset):
    """
    Modifica algunos valores numéricos para que cada mes sea distinto.
    """

    # Cambiar periodo
    data["periodo_iso"] = f"2025-{month_offset:02d}"

    # Modificar algunos valores del F931 para diferenciar
    f931 = data.get("sources_raw", {}).get("f931", {})

    # Ejemplo: modificar empleados en nómina
    if "metadata" in f931:
        if "empleados_en_nomina" in f931["metadata"]:
            f931["metadata"]["empleados_en_nomina"] += month_offset

    # Modificar algunos conceptos dinámicos si existen
    conceptos = f931.get("conceptos_dinamicos", [])
    for item in conceptos:
        if isinstance(item.get("value"), (int, float)):
            item["value"] += month_offset * 1000

    return data

def main():
    base_data = load_base()

    for month in range(1, 13):
        new_data = copy.deepcopy(base_data)
        new_data = modify_values(new_data, month)

        output_path = OUTPUT_DIR / f"consolidated_2025-{month:02d}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)

        print(f"✓ Creado {output_path.name}")

if __name__ == "__main__":
    main()