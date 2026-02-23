"""
ExcelLoader v4 — Escribe datos en las hojas '931' y 'Analisis General'.

Flujo:
  1. Lee el periodo del consolidado → calcula mes y columna
  2. Copia template → output (template nunca se modifica)
  3. Escribe en hoja '931': datos del F931 (aportes, contribuciones, etc.)
  4. Escribe en 'Analisis General': solo celdas de input directo
     (conceptos no remun, RENATRE, UATRE, dinámicos)
  5. Las fórmulas de 'Analisis General' que referencian '931' se
     recalculan automáticamente cuando el usuario abre en Excel.
"""

import re
import shutil
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from datetime import datetime
from excel.excel_mapper import ExcelMapper


class ExcelLoader:

    SHEET_931 = "931"
    SHEET_ANALISIS = "Analisis General"
    HEADER_ROW = 7       # Fila de encabezados de mes en Analisis General
    FIRST_DATA_ROW = 8   # Primera fila de datos en Analisis General
    LAST_DATA_ROW = 38   # Última fila de datos en Analisis General

    def __init__(self, template_path: str, consolidated_json: dict):
        self.template_path = str(Path(template_path).resolve())
        self.data = consolidated_json
        self.mapper = ExcelMapper(consolidated_json)

    # ---------------------------------------------------------
    # Método principal
    # ---------------------------------------------------------
    def update_excel(self, output_path: str):

        output_path = str(Path(output_path).resolve())

        if output_path == self.template_path:
            raise ValueError(
                "output_path no puede ser el mismo que template_path.\n"
                "openpyxl destruye cached values de fórmulas al guardar.\n"
                f"Template: {self.template_path}"
            )

        # --- Paso 1: Determinar periodo y columna ---
        periodo = self.data["periodo_iso"]
        year, month = [int(x) for x in periodo.split("-")]

        # Columna en Analisis General (detectada desde Títulos!B3)
        ag_col = self._detect_analisis_column(month)
        print(f"Periodo: {periodo} → Analisis General col {ag_col}")

        # --- Paso 2: Copiar template ---
        shutil.copy2(self.template_path, output_path)
        print(f"Template copiado a: {output_path}")

        # --- Paso 3: Escribir ---
        wb = load_workbook(output_path)

        written_931 = self._write_931(wb, month)
        written_ag = self._write_analisis_general(wb, ag_col)

        total = written_931 + written_ag
        print(f"\nResumen: {written_931} celdas en '931', "
              f"{written_ag} celdas en 'Analisis General', "
              f"{total} total")

        try:
            wb.save(output_path)
            print(f"Archivo guardado en: {output_path}")
        except PermissionError:
            raise PermissionError(
                "No se pudo guardar. ¿El archivo está abierto en Excel?"
            )

        wb.close()

    # ---------------------------------------------------------
    # Escritura en hoja '931'
    # ---------------------------------------------------------
    def _write_931(self, wb, month: int) -> int:

        if self.SHEET_931 not in wb.sheetnames:
            raise ValueError(f"No existe la hoja '{self.SHEET_931}'")

        ws = wb[self.SHEET_931]
        values = self.mapper.get_931_values(month)

        print(f"\nEscribiendo en hoja '{self.SHEET_931}':")
        written = 0

        for item in values:
            row = item["row"]
            col = item["col"]
            value = item["value"]
            label = item["label"]
            col_letter = get_column_letter(col)

            ws.cell(row=row, column=col, value=value)
            tipo = "texto" if isinstance(value, str) else "numérico"
            print(f"  {col_letter}{row} | {label} → {value} ({tipo})")
            written += 1

        return written

    # ---------------------------------------------------------
    # Escritura en 'Analisis General' (solo inputs directos)
    # ---------------------------------------------------------
    def _write_analisis_general(self, wb, month_col: int) -> int:

        if self.SHEET_ANALISIS not in wb.sheetnames:
            raise ValueError(f"No existe la hoja '{self.SHEET_ANALISIS}'")

        ws = wb[self.SHEET_ANALISIS]

        print(f"\nEscribiendo en hoja '{self.SHEET_ANALISIS}' (col {month_col}):")
        written = 0

        for row_num in range(self.FIRST_DATA_ROW, self.LAST_DATA_ROW + 1):

            concepto_cell = ws.cell(row=row_num, column=2)
            if not concepto_cell.value:
                continue

            concepto_text = str(concepto_cell.value).strip()
            target_cell = ws.cell(row=row_num, column=month_col)

            # No pisar fórmulas
            if target_cell.data_type == "f":
                continue

            value = self.mapper.resolve_analisis_value(row_num, concepto_text)

            if value is None:
                continue

            target_cell.value = value
            tipo = "texto" if isinstance(value, str) else "numérico"
            print(f"  Fila {row_num} | {concepto_text} → {value} ({tipo})")
            written += 1

        return written

    # ---------------------------------------------------------
    # Detección de columna en Analisis General
    # ---------------------------------------------------------
    def _detect_analisis_column(self, month: int) -> int:
        """
        Determina la columna del mes en 'Analisis General'.

        Estrategia 1: Lee Títulos!B3 (ancla hardcoded) → col = mes + 3
        Estrategia 2: data_only para cached values
        Estrategia 3: Buscar referencia a Títulos!B4 en fila de headers
        """

        # Estrategia 1: Ancla Títulos!B3
        try:
            wb = load_workbook(self.template_path, data_only=False)
            if "Títulos" in wb.sheetnames:
                anchor = wb["Títulos"].cell(row=3, column=2).value
                wb.close()
                if isinstance(anchor, datetime):
                    col = month + 3
                    if 4 <= col <= 15:
                        print(f"Ancla Títulos!B3 = {anchor.date()} → col {col}")
                        return col
            else:
                wb.close()
        except Exception:
            pass

        # Estrategia 2: Cached values
        try:
            wb = load_workbook(self.template_path, data_only=True)
            ws = wb[self.SHEET_ANALISIS]
            year_from_periodo = int(self.data["periodo_iso"].split("-")[0])
            for col_cell in ws[self.HEADER_ROW]:
                if isinstance(col_cell.value, datetime):
                    if col_cell.value.month == month and col_cell.value.year == year_from_periodo:
                        result = col_cell.column
                        wb.close()
                        print(f"Cached value → col {result}")
                        return result
            wb.close()
        except Exception:
            pass

        raise ValueError(
            f"No se pudo determinar la columna para mes {month}.\n"
            "Verificar que el template tenga la hoja 'Títulos' con B3 = fecha."
        )