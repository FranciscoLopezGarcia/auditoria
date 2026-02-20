import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from normalizer.dictionary_loader import load_dictionary_yaml
from normalizer.models import CanonicalSourceModel
from normalizer.consolidator import ConsolidatorV2, ConsolidatedTechnicalModel
from run_normalizer import run_one, FILES

BASE_DIR = Path(__file__).parent
DICT_PATH = BASE_DIR / "normalizer" / "dictionary.yaml"
OUTPUT_DIR = BASE_DIR / "output"


def build_sources(verbose: bool = False) -> list[CanonicalSourceModel]:
    sources: list[CanonicalSourceModel] = []
    for source_name, file_name in FILES.items():
        canonical = run_one(source_name, file_name, verbose=verbose)
        if canonical is not None:
            sources.append(canonical)
    return sources


def load_raw_sources() -> dict[str, dict[str, Any]]:
    """
    Carga los JSON PARSEADOS (los que salen de run_parser.py y quedan en output/),
    no los consolidados.
    Usa el mapping FILES del run_normalizer.py.
    """
    raw_sources: dict[str, dict[str, Any]] = {}
    for source_name, file_name in FILES.items():
        file_path = OUTPUT_DIR / file_name
        if not file_path.exists():
            continue
        with open(file_path, "r", encoding="utf-8") as f:
            raw_sources[source_name] = json.load(f)
    return raw_sources


def resolve_concept_keys() -> list[str]:
    dictionary = load_dictionary_yaml(DICT_PATH)
    return list(dictionary.concepts.keys())


def export_json(result: ConsolidatedTechnicalModel) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    file_name = f"consolidated_{result.periodo_iso}.json"
    output_path = OUTPUT_DIR / file_name
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, ensure_ascii=False, indent=2)
    return output_path


def print_consolidated(result: ConsolidatedTechnicalModel) -> None:
    print("\n=============================")
    print(f"Periodo: {result.periodo_iso}")
    print(f"Fuentes presentes: {result.diagnostics.sources_present}")
    print(f"Conceptos canónicos resueltos: {len(result.canonical.conceptos)}")
    print(f"Faltantes canónicos: {len(result.canonical.faltantes)}")
    print("=============================\n")


def main() -> None:
    canonical_sources = build_sources(verbose=False)
    if not canonical_sources:
        print("[ERROR] No se pudo normalizar ninguna fuente.")
        return

    raw_sources = load_raw_sources()
    concept_keys = resolve_concept_keys()

    consolidator = ConsolidatorV2(
        sources_canonical=canonical_sources,
        sources_raw=raw_sources,
        concept_keys=concept_keys,
    )
    result = consolidator.consolidate()

    print_consolidated(result)

    output_path = export_json(result)
    print(f"\n✓ JSON exportado: {output_path}")


if __name__ == "__main__":
    main()