"""
pipeline.py — Core pipeline for Px Laboral automation.

Public API:
    process_period(pdf_paths, period) -> Path

Executes the full pipeline in-process (no subprocess, no CLI):
    1. Parse PDFs → parser JSON dicts
    2. Index + Normalize → CanonicalSourceModel per source
    3. Consolidate → ConsolidatedTechnicalModel
    4. Write Excel → output file

Returns the Path to the generated Excel file.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# Parsers
from backend.core.parsers.asiento_parser import parse as parse_asiento
from backend.core.parsers.borrador_parser import parse as parse_borrador
from backend.core.parsers.f931_parser import parse as parse_f931

# Normalizer components
from backend.core.normalizer.dictionary_loader import load_dictionary_yaml
from backend.core.normalizer.indexers.f931 import F931Indexer
from backend.core.normalizer.indexers.borrador import BorradorIndexer
from backend.core.normalizer.indexers.asiento import AsientoIndexer
from backend.core.normalizer.normalizers.f931 import F931Normalizer
from backend.core.normalizer.normalizers.borrador import BorradorNormalizer
from backend.core.normalizer.normalizers.asiento import AsientoNormalizer
from backend.core.normalizer.models import CanonicalSourceModel

# Consolidator
from backend.core.normalizer.consolidator import ConsolidatorV2, ConsolidatedTechnicalModel

# Excel
from backend.core.excel.excel_loader import ExcelLoader

logger = logging.getLogger(__name__)

# Dictionary YAML lives alongside the normalizer package
_DICTIONARY_PATH = Path(__file__).parent / "normalizer" / "dictionary.yaml"

# Default template location (project root)
_DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent.parent / "Px Laboral Template.xlsx"


# ─────────────────────────────────────────────────────────
# Helpers: PDF type detection
# ─────────────────────────────────────────────────────────

def _detect_type(pdf_path: Path) -> Optional[str]:
    """Detect document type from filename. Returns 'f931', 'borrador', 'asiento', or None."""
    name = pdf_path.name.lower()
    if "f931" in name or "931" in name:
        return "f931"
    if "borrador" in name or "borra" in name:
        return "borrador"
    if "asiento" in name:
        return "asiento"
    return None


_PARSERS = {
    "f931": parse_f931,
    "borrador": parse_borrador,
    "asiento": parse_asiento,
}

_INDEXERS = {
    "f931": F931Indexer,
    "borrador": BorradorIndexer,
    "asiento": AsientoIndexer,
}

_NORMALIZERS = {
    "f931": F931Normalizer,
    "borrador": BorradorNormalizer,
    "asiento": AsientoNormalizer,
}


# ─────────────────────────────────────────────────────────
# Step 1: Parse
# ─────────────────────────────────────────────────────────

def _run_parsers(pdf_paths: List[Path]) -> Dict[str, Dict[str, Any]]:
    """
    Parse each PDF and return {source_type: parser_json_dict}.
    Skips unrecognized files with a warning.
    """
    results: Dict[str, Dict[str, Any]] = {}

    for pdf_path in pdf_paths:
        doc_type = _detect_type(pdf_path)
        if doc_type is None:
            logger.warning("Could not detect document type for: %s — skipping", pdf_path.name)
            continue

        parser_fn = _PARSERS[doc_type]
        logger.info("Parsing %s as %s", pdf_path.name, doc_type)
        parser_json = parser_fn(str(pdf_path))
        results[doc_type] = parser_json

    return results


# ─────────────────────────────────────────────────────────
# Step 2: Normalize
# ─────────────────────────────────────────────────────────

def _run_normalizers(
    parsed: Dict[str, Dict[str, Any]],
) -> List[CanonicalSourceModel]:
    """
    Index and normalize each parsed source into a CanonicalSourceModel.
    """
    dictionary = load_dictionary_yaml(str(_DICTIONARY_PATH))
    canonicals: List[CanonicalSourceModel] = []

    for source_name, parser_json in parsed.items():
        indexer = _INDEXERS[source_name]()
        normalizer = _NORMALIZERS[source_name]()

        indexed = indexer.index(parser_json)
        canonical = normalizer.normalize(indexed, dictionary)
        canonicals.append(canonical)

    return canonicals


# ─────────────────────────────────────────────────────────
# Step 3: Consolidate
# ─────────────────────────────────────────────────────────

def _run_consolidation(
    canonicals: List[CanonicalSourceModel],
    raw_sources: Dict[str, Dict[str, Any]],
) -> ConsolidatedTechnicalModel:
    """
    Merge all sources into a single ConsolidatedTechnicalModel.
    """
    dictionary = load_dictionary_yaml(str(_DICTIONARY_PATH))
    concept_keys = list(dictionary.concepts.keys())

    consolidator = ConsolidatorV2(
        sources_canonical=canonicals,
        sources_raw=raw_sources,
        concept_keys=concept_keys,
    )
    return consolidator.consolidate()


# ─────────────────────────────────────────────────────────
# Step 4: Excel generation
# ─────────────────────────────────────────────────────────

def _run_excel(
    consolidated: ConsolidatedTechnicalModel,
    template_path: Path,
    output_path: Path,
) -> Path:
    """
    Write the consolidated data into an Excel file copied from the template.
    Returns the output path.
    """
    consolidated_dict = asdict(consolidated)

    loader = ExcelLoader(
        template_path=str(template_path),
        consolidated_json=consolidated_dict,
    )
    loader.build_from_template(str(output_path))
    return output_path


# ─────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────

def process_period(
    pdf_paths: List[Path],
    period: str,
    template_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Execute the full pipeline for a single accounting period.

    Parameters
    ----------
    pdf_paths : list[Path]
        Paths to the PDF files (F931, Borrador, Asiento).
    period : str
        Period in ISO format, e.g. "2025-05".
    template_path : Path, optional
        Path to the Excel template. Defaults to project-root "Px Laboral Template.xlsx".
    output_dir : Path, optional
        Directory for the output Excel. Defaults to backend/output/.

    Returns
    -------
    Path
        Absolute path to the generated Excel file.

    Raises
    ------
    FileNotFoundError
        If the template is missing.
    ValueError
        If no PDFs could be parsed.
    """
    # Resolve template
    template = Path(template_path) if template_path else _DEFAULT_TEMPLATE
    if not template.exists():
        raise FileNotFoundError(f"Excel template not found: {template}")

    # Resolve output directory
    if output_dir is None:
        output_dir = Path(__file__).resolve().parent.parent / "output"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Parse ──
    logger.info("Step 1/4: Parsing %d PDF(s)", len(pdf_paths))
    parsed = _run_parsers([Path(p) for p in pdf_paths])

    if not parsed:
        raise ValueError("No PDFs could be parsed. Check filenames contain 'f931', 'borrador', or 'asiento'.")

    # ── Step 2: Normalize ──
    logger.info("Step 2/4: Normalizing %d source(s)", len(parsed))
    canonicals = _run_normalizers(parsed)

    if not canonicals:
        raise ValueError("Normalization produced no canonical models.")

    # ── Step 3: Consolidate ──
    logger.info("Step 3/4: Consolidating")
    consolidated = _run_consolidation(canonicals, parsed)

    # Persist consolidated JSON for audit trail
    consolidated_dict = asdict(consolidated)
    consolidated_json_path = output_dir / f"consolidated_{period}.json"
    with open(consolidated_json_path, "w", encoding="utf-8") as f:
        json.dump(consolidated_dict, f, ensure_ascii=False, indent=2)

    # ── Step 4: Excel ──
    logger.info("Step 4/4: Generating Excel")
    excel_filename = f"Px_Laboral_{period}.xlsx"
    excel_path = output_dir / excel_filename
    _run_excel(consolidated, template, excel_path)

    logger.info("Pipeline complete: %s", excel_path)
    return excel_path