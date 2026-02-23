"""
run_batch_excel.py
-------------------
Script de ejecución batch para cargar consolidados al Excel anual.

Comportamiento:
  - Si el Excel de salida NO existe → lo crea desde el template
  - Si el Excel de salida YA existe → lo actualiza (agrega/actualiza meses)

Esto permite uso incremental:
  1ra corrida: consolidados de enero-mayo → crea Excel con 5 meses
  2da corrida: consolidados de junio-agosto → agrega 3 meses, preserva los 5 anteriores
  3ra corrida: consolidados de enero-diciembre → recrea todo (resultado idéntico)

Uso:
  python run_batch_excel.py
"""

from pathlib import Path
from datetime import datetime
from excel.excel_batch_loader import ExcelBatchLoader


# ──────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────

TEMPLATE_PATH = "Px Laboral Template.xlsx"
OUTPUT_PATH = "Px Laboral 2025.xlsx"
CONSOLIDATED_DIR = "output"


def find_consolidated_files(folder: str) -> list[str]:
    """
    Busca todos los consolidated_YYYY-MM.json en la carpeta indicada.
    Retorna lista ordenada de paths como strings.
    """
    folder_path = Path(folder)
    if not folder_path.exists():
        print(f"✗ Carpeta no encontrada: {folder}")
        return []

    files = sorted(folder_path.glob("consolidated_*.json"))
    return [str(p) for p in files]


def resolve_output_path(output_path: str) -> str:
    """
    Decide qué hacer con el archivo de salida.

    - Si NO existe → se usará tal cual (build_year lo crea desde template)
    - Si YA existe → pregunta si actualizar, crear copia, o cancelar
    """
    path = Path(output_path)

    if not path.exists():
        print(f"\nArchivo de salida: {path}")
        print("→ No existe, se creará desde el template.\n")
        return str(path)

    print(f"\n⚠ El archivo ya existe: {path}")
    print("¿Qué desea hacer?")
    print("1 → Actualizar (agrega/actualiza meses, preserva datos existentes)")
    print("2 → Crear copia nueva con timestamp (desde template limpio)")
    print("3 → Cancelar")

    choice = input("Opción: ").strip()

    if choice == "1":
        print("→ Se actualizará el archivo existente. Los meses previos se preservan.\n")
        return str(path)

    elif choice == "2":
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"{path.stem}_{timestamp}{path.suffix}"
        new_path = path.parent / new_name
        print(f"→ Se creará nuevo archivo desde template: {new_path}\n")
        return str(new_path)

    else:
        print("Operación cancelada.")
        exit()


def main():
    # 1. Buscar consolidados
    consolidados = find_consolidated_files(CONSOLIDATED_DIR)

    if not consolidados:
        print("No se encontraron consolidados en:", CONSOLIDATED_DIR)
        return

    print(f"Consolidados encontrados: {len(consolidados)}")
    for c in consolidados:
        print(f"  - {Path(c).name}")

    # 2. Resolver output path (crear nuevo vs actualizar existente)
    final_output = resolve_output_path(OUTPUT_PATH)

    # 3. Validar template
    if not Path(TEMPLATE_PATH).exists():
        print(f"✗ Template no encontrado: {TEMPLATE_PATH}")
        return

    # 4. Ejecutar batch
    batch = ExcelBatchLoader(TEMPLATE_PATH)
    batch.build_year(consolidados, final_output)


if __name__ == "__main__":
    main()