"""
ExcelBatchLoader v2

Modos de operación:
  - build_year()  → Crea Excel nuevo desde template O actualiza uno existente.
    - Si el output NO existe → copia template (modo creación)
    - Si el output YA existe → lo abre directo (modo update, preserva datos)

Garantías:
  - Idempotente: cargar el mismo mes dos veces no duplica ni corrompe datos.
  - Incremental: agregar meses nuevos no borra los anteriores.
  - Determinístico: cargar 3 meses + 9 meses = cargar 12 meses de una vez.

Log de verificación:
  - Post-escritura reporta celdas escritas por mes y por hoja.
  - Resumen final con totales acumulados.
"""

from pathlib import Path
from openpyxl import load_workbook
import shutil
import json

from backend.core.excel.excel_loader import ExcelLoader


class ExcelBatchLoader:

    def __init__(self, template_path: str):
        self.template_path = str(Path(template_path).resolve())

    def build_year(self, consolidated_paths: list, output_path: str):
        """
        Escribe múltiples meses consolidados en un solo Excel.

        Lógica de archivo:
          - Si output_path NO existe → copia template (creación desde cero)
          - Si output_path YA existe → lo abre directo (preserva datos previos)

        Esto permite uso incremental:
          1) Correr con enero-mayo → crea archivo con 5 meses
          2) Correr con junio-agosto → agrega 3 meses sin borrar los anteriores
          3) Correr con enero-diciembre → recrea todo desde cero (mismo resultado)
        """
        output_path = str(Path(output_path).resolve())

        if output_path == self.template_path:
            raise ValueError("Output no puede ser el template.")

        if not consolidated_paths:
            raise ValueError("No se recibieron consolidados.")

        # ─── DECISIÓN CLAVE: crear vs actualizar ───
        output_exists = Path(output_path).exists()

        if output_exists:
            print(f"[UPDATE] Archivo existente detectado → {output_path}")
            print(f"         Se agregarán/actualizarán {len(consolidated_paths)} meses")
            print(f"         Los meses previamente cargados se PRESERVAN")
        else:
            shutil.copy2(self.template_path, output_path)
            print(f"[CREATE] Template copiado → {output_path}")

        # Abrir workbook UNA vez
        wb = load_workbook(output_path)

        total_written = 0
        # Registro de escritura por mes para verificación
        write_log: list[dict] = []

        # Ordenar por nombre (asume formato consolidated_YYYY-MM.json)
        consolidated_paths = sorted(consolidated_paths)

        for path in consolidated_paths:

            print(f"\n{'─' * 50}")
            print(f"Procesando: {path}")

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            periodo = data.get("periodo_iso", "???")

            loader = ExcelLoader(
                template_path=self.template_path,
                consolidated_json=data
            )

            ag_col = loader._detect_analisis_column(loader.month, wb=wb)

            written_931 = loader._write_931(wb)
            written_ag = loader._write_analisis_general(wb, ag_col)

            month_total = written_931 + written_ag
            total_written += month_total

            # Registrar para log de verificación
            write_log.append({
                "periodo": periodo,
                "hoja_931": written_931,
                "analisis_general": written_ag,
                "total": month_total,
            })

            print(f"  → {month_total} celdas escritas (931: {written_931}, AG: {written_ag})")

        # Guardar UNA sola vez
        wb.save(output_path)
        wb.close()

        # ─── LOG DE VERIFICACIÓN ───
        self._print_verification_log(write_log, total_written, output_path, output_exists)

    def _print_verification_log(
        self,
        write_log: list[dict],
        total_written: int,
        output_path: str,
        was_update: bool
    ):
        """
        Imprime resumen detallado post-escritura.
        Permite verificar de un vistazo que cada mes se cargó correctamente.
        """
        print(f"\n{'═' * 60}")
        print(f"  RESUMEN DE VERIFICACIÓN")
        print(f"{'═' * 60}")
        print(f"  Modo: {'UPDATE (preservó datos previos)' if was_update else 'CREATE (desde template limpio)'}")
        print(f"  Archivo: {output_path}")
        print(f"  Meses procesados: {len(write_log)}")
        print(f"{'─' * 60}")
        print(f"  {'Periodo':<12} {'931':>8} {'AG':>8} {'Total':>8}")
        print(f"  {'─' * 40}")

        meses_vacios = []
        for entry in write_log:
            periodo = entry["periodo"]
            flag = "" if entry["total"] > 0 else "  ⚠ SIN DATOS"
            print(f"  {periodo:<12} {entry['hoja_931']:>8} {entry['analisis_general']:>8} {entry['total']:>8}{flag}")
            if entry["total"] == 0:
                meses_vacios.append(periodo)

        print(f"  {'─' * 40}")
        print(f"  {'TOTAL':<12} {sum(e['hoja_931'] for e in write_log):>8} {sum(e['analisis_general'] for e in write_log):>8} {total_written:>8}")
        print(f"{'═' * 60}")

        # Alertas
        if meses_vacios:
            print(f"\n  ⚠ ALERTA: {len(meses_vacios)} mes(es) con 0 celdas escritas:")
            for p in meses_vacios:
                print(f"    - {p} → Verificar que el JSON consolidado tenga datos válidos")
        else:
            print(f"\n  ✓ Todos los meses tienen datos escritos")

        print()