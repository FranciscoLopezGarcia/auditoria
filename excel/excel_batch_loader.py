from pathlib import Path
from openpyxl import load_workbook
import shutil
import json

from excel.excel_loader import ExcelLoader


class ExcelBatchLoader:

    def __init__(self, template_path: str):
        self.template_path = str(Path(template_path).resolve())

    def build_year(self, consolidated_paths: list, output_path: str):

        output_path = str(Path(output_path).resolve())

        if output_path == self.template_path:
            raise ValueError("Output no puede ser el template.")

        if not consolidated_paths:
            raise ValueError("No se recibieron consolidados.")

        # Copiar template una sola vez
        shutil.copy2(self.template_path, output_path)
        print(f"Template copiado → {output_path}")

        # Abrir workbook UNA vez
        wb = load_workbook(output_path)

        total_written = 0

        # Ordenar por nombre (asume formato consolidated_YYYY-MM.json)
        consolidated_paths = sorted(consolidated_paths)

        for path in consolidated_paths:

            print(f"\nProcesando: {path}")

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            loader = ExcelLoader(
                template_path=self.template_path,
                consolidated_json=data
            )

            ag_col = loader._detect_analisis_column(loader.month, wb=wb)

            written_931 = loader._write_931(wb)
            written_ag = loader._write_analisis_general(wb, ag_col)

            total = written_931 + written_ag
            total_written += total

            print(f"  → {total} celdas escritas")

        # Guardar UNA sola vez
        wb.save(output_path)
        wb.close()

        print("\nBatch finalizado.")
        print(f"Total celdas escritas: {total_written}")
        print(f"Archivo generado: {output_path}")