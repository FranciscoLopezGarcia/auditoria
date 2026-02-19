from __future__ import annotations

from abc import ABC
from typing import Dict, List, Any
from ..models import (
    IndexedSource,
    CanonicalSourceModel,
    CanonicalConceptEvidence,
    CanonicalConceptValue,
)
from ..dictionary_loader import DictionaryModel, MatcherDef
from ..matchers import matcher_matches


class BaseNormalizer(ABC):
    def __init__(self, source_name: str):
        self.source_name = source_name

    def normalize(self, indexed: IndexedSource, dictionary: DictionaryModel) -> CanonicalSourceModel:
        if indexed.source != self.source_name:
            raise ValueError(f"Normalizer {self.source_name} recibió IndexedSource de {indexed.source}")

        conceptos: Dict[str, CanonicalConceptValue] = {}
        warnings: List[Dict[str, Any]] = []

        for canonical_key, concept_def in dictionary.concepts.items():
            matchers = concept_def.matchers.get(self.source_name, []) or []
            matches = self._find_matches(indexed, matchers)

            if len(matches) == 1:
                item = matches[0]

                # VALIDACIÓN OBLIGATORIA: valor numérico
                if not isinstance(item.value, (int, float)):
                    warnings.append({
                        "code": "INVALID_VALUE_TYPE",
                        "concept": canonical_key,
                        "json_path": item.json_path,
                        "value_type": type(item.value).__name__,
                    })
                    continue

                if canonical_key in conceptos:
                    warnings.append({
                        "code": "DUPLICATE_CANONICAL_KEY",
                        "detail": f"Clave duplicada: {canonical_key}",
                    })
                    continue

                evidencia = CanonicalConceptEvidence(
                    label_original=item.label,
                    codigo=item.codigo,
                    json_path=item.json_path,
                    raw=item.raw,
                    attributes=item.attributes,
                )
                conceptos[canonical_key] = CanonicalConceptValue(
                    valor=item.value,  # NO modificar
                    evidencia=evidencia,
                )

            elif len(matches) > 1:
                warnings.append({
                    "code": "AMBIGUOUS_MATCH",
                    "concept": canonical_key,
                    "count": len(matches),
                    "matches": [
                        {"label": m.label, "codigo": m.codigo, "json_path": m.json_path}
                        for m in matches[:10]
                    ],
                })

            else:
                if concept_def.obligatorio:
                    warnings.append({
                        "code": "MISSING_REQUIRED",
                        "concept": canonical_key,
                    })

        variables_contables = self._build_variables_contables(indexed, conceptos)

        return CanonicalSourceModel(
            source=indexed.source,
            periodo=indexed.periodo,   # NO tocar formato
            conceptos=conceptos,
            variables_contables=variables_contables,
            warnings=warnings,
        )

    def _find_matches(self, indexed: IndexedSource, matchers: List[MatcherDef]):
        if not matchers:
            return []
        matched_items = []
        for item in indexed.items:
            for matcher in matchers:
                if matcher_matches(item, matcher):
                    matched_items.append(item)
                    break
        return matched_items

    def _build_variables_contables(self, indexed: IndexedSource, conceptos: Dict[str, CanonicalConceptValue]):
        return []
