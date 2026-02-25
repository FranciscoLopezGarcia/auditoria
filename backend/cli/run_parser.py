"""
run_parse.py
-------------
Entrypoint CLI.

Uso:
    python run_parse.py --input "./pdfs" --output "./outputs"

El script detecta automáticamente qué tipo de PDF es cada archivo
basándose en su nombre (heurística) o en el contenido.

Criterio de detección:
  - Si el nombre contiene "asiento" -> asiento_parser
  - Si el nombre contiene "borrador" o "f931" -> borrador_parser / f931_parser
  - Si no, intenta detectar por contenido (primera página).

Salidas:
  - Un .json por PDF procesado.
  - Un archivo resumen.json con estadísticas de campos extraídos.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

# Configurar logging ANTES de importar los parsers
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def detect_parser_type(pdf_path: Path) -> str:
    """
    Detecta el tipo de parser necesario.
    Primero por nombre de archivo, luego por contenido.
    """
    name_lower = pdf_path.name.lower()

    if "asiento" in name_lower:
        return "asiento"
    if "borrador" in name_lower or "borra" in name_lower:
        return "borrador"
    if "f931" in name_lower or "931" in name_lower:
        return "f931"

    # Fallback: leer primeras líneas del PDF
    try:
        from backend.core.utils.pdf_text import extract_text
        lines, _ = extract_text(str(pdf_path))
        first_500 = " ".join(lines[:20]).upper()

        if "ASIENTO CONTABLE" in first_500:
            return "asiento"
        if "BORRADOR" in first_500 or "DECLARACI" in first_500:
            return "borrador"
        if "F.931" in first_500 or "SUSS" in first_500:
            return "f931"
    except Exception as e:
        logger.warning(f"No se pudo detectar tipo por contenido: {e}")

    logger.warning(f"No se pudo detectar tipo para {pdf_path.name}. Saltando.")
    return "unknown"


def run_parser(pdf_path: Path, parser_type: str) -> dict:
    """Ejecuta el parser correspondiente y retorna el resultado."""
    if parser_type == "asiento":
        from backend.core.parsers.asiento_parser import parse
    elif parser_type == "borrador":
        from backend.core.parsers.borrador_parser import parse
    elif parser_type == "f931":
        from backend.core.parsers.f931_parser import parse
    else:
        raise ValueError(f"Tipo de parser desconocido: {parser_type}")

    return parse(str(pdf_path))


def count_fields(result: dict) -> dict:
    """Cuenta cuántos campos se extrajeron exitosamente."""
    stats = {
        "campos_principales": 0,
        "tablas": 0,
        "conceptos_dinamicos": 0,
        "total": 0,
    }

    extracted = result.get("extracted", {})

    campos = extracted.get("campos_principales", {})
    stats["campos_principales"] = len([v for v in campos.values()
                                        if isinstance(v, dict) and v.get("value") is not None])

    tablas = extracted.get("tablas", {})
    for tabla_name, tabla_data in tablas.items():
        if isinstance(tabla_data, list):
            stats["tablas"] += len(tabla_data)
        elif isinstance(tabla_data, dict):
            stats["tablas"] += len([v for v in tabla_data.values()
                                     if isinstance(v, dict) and v.get("value") is not None])

    stats["conceptos_dinamicos"] = len(extracted.get("conceptos_dinamicos", []))
    stats["total"] = sum(stats[k] for k in stats if k != "total")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Parser de PDFs laborales (Asiento, Borrador, F.931)"
    )
    parser.add_argument(
        "--input", required=True,
        help="Carpeta con los PDFs a procesar"
    )
    parser.add_argument(
        "--output", required=True,
        help="Carpeta donde se guardan los JSON resultantes"
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nivel de logging"
    )
    args = parser.parse_args()

    logging.getLogger().setLevel(args.log_level)

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not input_dir.exists():
        logger.error(f"Carpeta de entrada no existe: {input_dir}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Fix #5: deduplicar usando resolve() para evitar que *.pdf y *.PDF
    # matcheen el mismo archivo en filesystems case-insensitive (Windows).
    seen = set()
    pdfs = []
    for p in list(input_dir.glob("*.pdf")) + list(input_dir.glob("*.PDF")):
        key = p.resolve()
        if key not in seen:
            seen.add(key)
            pdfs.append(p)
    if not pdfs:
        logger.warning(f"No se encontraron PDFs en {input_dir}")
        sys.exit(0)

    logger.info(f"Encontrados {len(pdfs)} PDFs en {input_dir}")

    summary = {
        "run_timestamp": datetime.now().isoformat(),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "files_processed": [],
        "files_failed": [],
    }

    for pdf_path in sorted(pdfs):
        logger.info(f"\n{'='*60}")
        logger.info(f"Procesando: {pdf_path.name}")

        parser_type = detect_parser_type(pdf_path)
        if parser_type == "unknown":
            summary["files_failed"].append({
                "file": pdf_path.name,
                "reason": "tipo_no_detectado"
            })
            continue

        logger.info(f"Tipo detectado: {parser_type}")

        try:
            result = run_parser(pdf_path, parser_type)
            stats = count_fields(result)

            # Guardar JSON
            output_filename = f"{pdf_path.stem}_{parser_type}.json"
            output_path = output_dir / output_filename

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            logger.info(f"✓ Guardado: {output_filename}")
            logger.info(f"  Campos extraídos: {stats}")

            summary["files_processed"].append({
                "file": pdf_path.name,
                "parser_type": parser_type,
                "output_file": output_filename,
                "stats": stats,
                "periodo": result.get("metadata", {}).get("periodo_detectado"),
                "contribuyente": result.get("metadata", {}).get("contribuyente"),
            })

        except Exception as e:
            logger.error(f"✗ Error procesando {pdf_path.name}: {e}", exc_info=True)
            summary["files_failed"].append({
                "file": pdf_path.name,
                "reason": str(e)
            })

    # Guardar resumen
    summary_path = output_dir / "resumen.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info(f"\n{'='*60}")
    logger.info(f"RESUMEN FINAL:")
    logger.info(f"  Procesados exitosamente: {len(summary['files_processed'])}")
    logger.info(f"  Fallidos: {len(summary['files_failed'])}")
    logger.info(f"  Resumen guardado en: {summary_path}")

    # Imprimir tabla de campos
    if summary["files_processed"]:
        logger.info("\nCampos extraídos por archivo:")
        for item in summary["files_processed"]:
            logger.info(f"  {item['file']:<40} -> {item['stats']['total']} campos totales")


if __name__ == "__main__":
    main()