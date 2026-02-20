"""
ExcelLoader v2 — Actualiza la hoja "Analisis General" con datos del consolidado.

Cambios respecto a v1:
  - Pasa row_num al mapper (necesario para resolución row-based)
  - Soporta valores de texto (str) además de float
  - Logging mejorado con tipo de valor
"""

from openpyxl import load_workbook
from datetime import datetime
from excel.excel_mapper import ExcelMapper


class ExcelLoader:

    SHEET_NAME = "Analisis General"
    HEADER_ROW = 7
    FIRST_DATA_ROW = 8
    LAST_DATA_ROW = 38

    def __init__(self, template_path: str, consolidated_json: dict):
        self.template_path = template_path
        self.data = consolidated_json
        self.mapper = ExcelMapper(consolidated_json)

    # ---------------------------------------------------------
    # Método principal
    # ---------------------------------------------------------
    def update_excel(self, output_path: str):

        print("Abriendo Excel para lectura de encabezados...")

        # Paso 1: data_only=True para leer headers resueltos (EOMONTH → datetime)
        wb_read = load_workbook(self.template_path, data_only=True)

        if self.SHEET_NAME not in wb_read.sheetnames:
            raise ValueError(f"No existe la hoja '{self.SHEET_NAME}'")

        ws_read = wb_read[self.SHEET_NAME]

        periodo = self.data["periodo_iso"]
        month_col = self._find_month_column(ws_read, periodo)

        wb_read.close()

        print(f"Columna detectada para {periodo}: {month_col}")

        # Paso 2: modo normal para escribir (preserva fórmulas)
        print("Abriendo Excel para escritura...")
        wb = load_workbook(self.template_path)
        ws = wb[self.SHEET_NAME]

        written = 0
        skipped_none = 0
        skipped_formula = 0
        skipped_empty = 0

        for row_num in range(self.FIRST_DATA_ROW, self.LAST_DATA_ROW + 1):

            concepto_cell = ws.cell(row=row_num, column=2)  # Columna B

            if not concepto_cell.value:
                skipped_empty += 1
                continue

            concepto_text = str(concepto_cell.value).strip()

            # --- Resolver valor via mapper (ahora con row_num) ---
            value = self.mapper.resolve_value(row_num, concepto_text)

            # None → no hay dato real → no tocar la celda
            if value is None:
                print(f"  Fila {row_num} | {concepto_text} → sin mapeo (no se toca)")
                skipped_none += 1
                continue

            target_cell = ws.cell(row=row_num, column=month_col)

            # No pisar fórmulas
            if target_cell.data_type == "f":
                print(f"  Fila {row_num} | {concepto_text} → fórmula existente (no se toca)")
                skipped_formula += 1
                continue

            # Escribir el valor (puede ser float o str)
            target_cell.value = value
            tipo = "texto" if isinstance(value, str) else "numérico"
            print(f"  Fila {row_num} | {concepto_text} → {value} ({tipo})")
            written += 1

        print(f"\nResumen: {written} escritos, {skipped_none} sin mapeo, "
              f"{skipped_formula} fórmulas preservadas, {skipped_empty} filas vacías")

        try:
            wb.save(output_path)
            print(f"Archivo guardado en: {output_path}")
        except PermissionError:
            raise PermissionError(
                "No se pudo guardar el Excel. "
                "Probablemente esté abierto en otra ventana."
            )

        wb.close()

    # ---------------------------------------------------------
    # Detecta columna del mes
    # ---------------------------------------------------------
    def _find_month_column(self, ws, periodo_iso: str) -> int:

        year, month = periodo_iso.split("-")
        year = int(year)
        month = int(month)

        for col in ws[self.HEADER_ROW]:
            val = col.value

            if val is None:
                continue

            if isinstance(val, datetime):
                if val.year == year and val.month == month:
                    return col.column

            if isinstance(val, str):
                header = val.strip().lower()
                target = datetime(year, month, 1).strftime("%b-%y").lower()
                if header == target:
                    return col.column

        raise ValueError(
            f"No se encontró columna para {periodo_iso}. "
            f"Encabezados detectados: {[c.value for c in ws[self.HEADER_ROW]]}"
        )