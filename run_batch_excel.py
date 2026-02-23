import os
import re
import json
import shutil
from pathlib import Path
from datetime import datetime

from excel.excel_loader import ExcelLoader


# =========================
# CONFIG HARDCODEADA (tu pedido)
# =========================
OUTPUT_DIR = r"C:\Users\franl\Desktop\auditoria\proyecto\px_laboral_automation\output"
EXCEL_PATH = r"C:\Users\franl\Desktop\auditoria\Px Laboral 2025.xlsx"

# Si querés modo BUILD (crear un excel nuevo), usá:
# TEMPLATE_EXCEL_PATH = r"C:\Users\franl\Desktop\auditoria\Px Laboral 2025.xlsx"
# OUT_EXCEL_BUILD = r"C:\Users\franl\Desktop\auditoria\Px Laboral 2025 - BUILD.xlsx"


CONSOLIDATED_RE = re.compile(r"^consolidated_(\d{4}-\d{2})\.json$", re.IGNORECASE)


def find_consolidated_files(folder: str) -> list[tuple[str, str]]:
    """
    Devuelve lista de (periodo_iso, filepath) ordenada por periodo.
    """
    items = []
    for name in os.listdir(folder):
        m = CONSOLIDATED_RE.match(name)
        if not m:
            continue
        periodo = m.group(1)
        items.append((periodo, os.path.join(folder, name)))

    items.sort(key=lambda x: x[0])
    return items


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_output_path(original_excel_path: str) -> str:
    """
    Si el excel está abierto y no se puede escribir encima (PermissionError),
    guardamos un archivo nuevo con timestamp al final.
    """
    p = Path(original_excel_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(p.with_name(f"{p.stem}__updated_{stamp}{p.suffix}"))


def main():
    print("Buscando consolidados en:", OUTPUT_DIR)
    consolidated = find_consolidated_files(OUTPUT_DIR)

    if not consolidated:
        print("✗ No se encontraron consolidated_YYYY-MM.json en output/")
        return

    print(f"✓ Encontrados {len(consolidated)} consolidado(s):")
    for periodo, fp in consolidated:
        print("  -", periodo, "->", os.path.basename(fp))

    # Intentamos escribir sobre el EXCEL_PATH.
    # Si está abierto, caemos en un archivo nuevo.
    target_excel_path = EXCEL_PATH
    fallback_excel_path = safe_output_path(EXCEL_PATH)

    # (Opcional) Verificación rápida: existe excel
    if not os.path.exists(target_excel_path):
        print("✗ No existe el Excel:", target_excel_path)
        return

    # Ejecuta actualización por período
    written_periods = 0
    for periodo, consolidated_path in consolidated:
        data = load_json(consolidated_path)

        # sanity check
        data_periodo = data.get("periodo_iso")
        if data_periodo != periodo:
            print(f"⚠ Periodo inconsistente. Archivo {os.path.basename(consolidated_path)} "
                  f"dice {periodo} pero json trae {data_periodo}. Se usa json.periodo_iso.")
            periodo = data_periodo or periodo

        print("\n=============================")
        print("Actualizando periodo:", periodo)
        print("=============================")

        loader = ExcelLoader(template_path=target_excel_path, consolidated_json=data)

        try:
            # OJO: update_excel hoy recibe output_path.
            # Si querés que NO pise el archivo original, pasale otro path acá.
            loader.update_excel(output_path=target_excel_path)
            written_periods += 1
            print("✓ OK:", periodo)
        except PermissionError:
            print("⚠ Excel está abierto o sin permisos:", target_excel_path)
            print("→ Guardando en archivo alternativo:", fallback_excel_path)

            # Copiamos el original a fallback SOLO una vez (así mantenemos lo ya escrito)
            if not os.path.exists(fallback_excel_path):
                shutil.copy2(target_excel_path, fallback_excel_path)

            # A partir de ahora seguimos escribiendo sobre el fallback
            target_excel_path = fallback_excel_path

            loader = ExcelLoader(template_path=target_excel_path, consolidated_json=data)
            loader.update_excel(output_path=target_excel_path)
            written_periods += 1
            print("✓ OK:", periodo, "(en fallback)")

    print("\n=============================")
    print("RESUMEN")
    print("=============================")
    print("Periodos escritos:", written_periods)
    print("Excel final:", target_excel_path)
    print("Listo.")


if __name__ == "__main__":
    main()