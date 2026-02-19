from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import yaml


@dataclass(frozen=True)
class MatcherDef:
    type: str                 # equals | regex | codigo | json_path
    value: str                # patrón / literal / código / path
    attributes_filter: Optional[Dict[str, Any]] = None  # exact match only
    case_sensitive: bool = True  # default True


@dataclass(frozen=True)
class ConceptDef:
    key: str
    obligatorio: bool
    tolerancia: float
    tipo: str
    categoria: Optional[str]
    resolution_hint: Dict[str, Any]
    matchers: Dict[str, List[MatcherDef]]  # por fuente


@dataclass(frozen=True)
class DictionaryModel:
    meta: Dict[str, Any]
    concepts: Dict[str, ConceptDef]


def load_dictionary_yaml(path: str) -> DictionaryModel:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    meta = data.get("meta", {})
    concepts_raw = data.get("concepts", {}) or {}

    concepts: Dict[str, ConceptDef] = {}

    for key, c in concepts_raw.items():
        matchers_by_source: Dict[str, List[MatcherDef]] = {}
        raw_matchers = c.get("matchers", {}) or {}

        for source_name, matcher_list in raw_matchers.items():
            matchers_by_source[source_name] = []
            for m in (matcher_list or []):
                matchers_by_source[source_name].append(
                    MatcherDef(
                        type=m["type"],
                        value=m["value"],
                        attributes_filter=m.get("attributes_filter"),
                        case_sensitive=bool(m.get("case_sensitive", True)),
                    )
                )

        concepts[key] = ConceptDef(
            key=key,
            obligatorio=bool(c.get("obligatorio", False)),
            tolerancia=float(c.get("tolerancia", 0.0)),
            tipo=str(c.get("tipo", "")),
            categoria=c.get("categoria"),
            resolution_hint=c.get("resolution_hint", {}) or {},  # declarado, NO ejecutado
            matchers=matchers_by_source,
        )

    return DictionaryModel(meta=meta, concepts=concepts)
