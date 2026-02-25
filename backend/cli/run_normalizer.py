import json
from pathlib import Path
from typing import Optional

from backend.core.normalizer.dictionary_loader import load_dictionary_yaml
from backend.core.normalizer.indexers.f931 import F931Indexer
from backend.core.normalizer.indexers.borrador import BorradorIndexer
from backend.core.normalizer.indexers.asiento import AsientoIndexer
from backend.core.normalizer.normalizers.f931 import F931Normalizer
from backend.core.normalizer.normalizers.borrador import BorradorNormalizer
from backend.core.normalizer.normalizers.asiento import AsientoNormalizer
from backend.core.normalizer.models import CanonicalSourceModel

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
DICT_PATH = BASE_DIR / "normalizer" / "dictionary.yaml"

FILES: dict[str, str] = {
    "f931": "SUMP-F931 05-25_f931.json",
    "borrador": "SUMP-BORRADOR 05-25_borrador.json",
    "asiento": "Asiento SUMPETROL 052025_asiento.json",
}


def run_one(source_name: str, file_name: str, verbose: bool = True) -> Optional[CanonicalSourceModel]:
    file_path = OUTPUT_DIR / file_name
    if not file_path.exists():
        print(f"[ERROR] No existe: {file_path}")
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        parser_json = json.load(f)

    if source_name == "f931":
        indexed = F931Indexer().index(parser_json)
        normalizer = F931Normalizer()
    elif source_name == "borrador":
        indexed = BorradorIndexer().index(parser_json)
        normalizer = BorradorNormalizer()
    elif source_name == "asiento":
        indexed = AsientoIndexer().index(parser_json)
        normalizer = AsientoNormalizer()
    else:
        raise ValueError(f"Fuente no soportada: {source_name}")

    dictionary = load_dictionary_yaml(DICT_PATH)
    canonical = normalizer.normalize(indexed, dictionary)

    if verbose:
        print(f"\n---- DEBUG INDEX ({source_name}) ----")
        print(f"Items indexados: {len(indexed.items)}")
        for item in indexed.items[:15]:
            print(item.json_path)

        print("\n=============================")
        print(f"Fuente: {canonical.source}")
        print(f"Periodo: {canonical.periodo}")
        print(f"Conceptos encontrados: {len(canonical.conceptos)}")
        print(f"Warnings: {len(canonical.warnings)}")
        print("=============================\n")

        for k, v in canonical.conceptos.items():
            print(f"{k}: {v.valor}")

        if canonical.warnings:
            print("\n⚠ WARNINGS:")
            for w in canonical.warnings:
                print(w)

    return canonical


def main() -> None:
    for source, file_name in FILES.items():
        run_one(source, file_name, verbose=True)


if __name__ == "__main__":
    main()