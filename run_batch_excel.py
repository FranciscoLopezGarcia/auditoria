from pathlib import Path
from datetime import datetime
from excel.excel_batch_loader import ExcelBatchLoader


TEMPLATE_PATH = "Px Laboral Template.xlsx"
OUTPUT_PATH = "Px Laboral 2025.xlsx"


def resolve_output_path(output_path: str) -> str:
    path = Path(output_path)

    if not path.exists():
        return str(path)

    print(f"\n⚠ El archivo ya existe: {path}")
    print("¿Qué desea hacer?")
    print("1 → Sobrescribir")
    print("2 → Crear copia con timestamp")
    print("3 → Cancelar")

    choice = input("Opción: ").strip()

    if choice == "1":
        print("Se sobrescribirá el archivo existente.")
        return str(path)

    elif choice == "2":
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"{path.stem}_{timestamp}{path.suffix}"
        new_path = path.parent / new_name
        print(f"Se creará nuevo archivo: {new_path}")
        return str(new_path)

    else:
        print("Operación cancelada.")
        exit()


def main():

    folder = Path("output")
    consolidados = sorted(folder.glob("consolidated_2025-*.json"))
    consolidados = [str(p) for p in consolidados]

    if not consolidados:
        print("No se encontraron consolidados.")
        return

    final_output = resolve_output_path(OUTPUT_PATH)

    batch = ExcelBatchLoader(TEMPLATE_PATH)
    batch.build_year(consolidados, final_output)


if __name__ == "__main__":
    main()