import os
import re
import json
import shutil
from pathlib import Path
from openpyxl import load_workbook

from backend.core.excel.excel_loader import ExcelLoader

OUTPUT_DIR = r"C:\Users\franl\Desktop\auditoria\proyecto\px_laboral_automation\output"
TEMPLATE_EXCEL = r"C:\Users\franl\Desktop\auditoria\Px Laboral 2025.xlsx"
OUT_EXCEL = r"C:\Users\franl\Desktop\auditoria\Px Laboral 2025__OUT.xlsx"

CONSOLIDATED_RE = re.compile(r"^consolidated_(\d{4}-\d{2})\.json$", re.IGNORECASE)


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_consolidated(folder: str):
    items = []
    for name in os.listdir(folder):
        m = CONSOLIDATED_RE.match(name)
        if not m:
            continue
        periodo = m.group(1)
        items.append((periodo, os.path.join(folder, name)))
    items.sort(key=lambda x: x[0])
    return items


def main():
    consolidated = list_consolidated(OUTPUT_DIR)
    if not consolidated:
        print("✗ No hay consolidated_YYYY-MM.json en output/")
        return

    print(f"✓ {len(consolidated)} consolidados encontrados:")
    for p, fp in consolidated:
        print("  -", p, os.path.basename(fp))

    # 1) Copiar template a OUT una vez
    shutil.copy2(TEMPLATE_EXCEL, OUT_EXCEL)
    print("\n✓ Template copiado a:", OUT_EXCEL)

    # 2) Abrir OUT una sola vez
    wb = load_workbook(OUT_EXCEL)

    total_931 = 0
    total_ag = 0

    # 3) Por cada período, usar métodos internos del ExcelLoader
    for periodo, fp in consolidated:
        data = load_json(fp)
        loader = ExcelLoader(template_path=TEMPLATE_EXCEL, consolidated_json=data)

        # calcular mes y col como hace tu loader
        month = int(data["periodo_iso"].split("-")[1])
        ag_col = loader._detect_analisis_column(month, wb=wb)

        print("\n=============================")
        print("Periodo:", data["periodo_iso"], "| mes:", month, "| col:", ag_col)
        print("=============================")

        total_931 += loader._write_931(wb, month)
        total_ag += loader._write_analisis_general(wb, ag_col)

    print("\nGuardando…")
    wb.save(OUT_EXCEL)
    wb.close()

    print("\n=============================")
    print("RESUMEN FINAL")
    print("=============================")
    print("Celdas escritas en 931:", total_931)
    print("Celdas escritas en Analisis General:", total_ag)
    print("Archivo final:", OUT_EXCEL)
    print("Listo.")


if __name__ == "__main__":
    main()