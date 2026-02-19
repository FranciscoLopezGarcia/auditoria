from __future__ import annotations

from typing import Dict, Any, List, Set
from .base import BaseNormalizer
from ..models import CanonicalConceptValue


class AsientoNormalizer(BaseNormalizer):
    def __init__(self):
        super().__init__("asiento")

    def _build_variables_contables(self, indexed, conceptos: Dict[str, CanonicalConceptValue]) -> List[Dict[str, Any]]:
        used_paths: Set[str] = {v.evidencia.json_path for v in conceptos.values()}

        vars_out: List[Dict[str, Any]] = []
        seen_paths: Set[str] = set()  # DEDUPE por json_path

        for item in indexed.items:
            if item.json_path in used_paths:
                continue

            tipo = item.attributes.get("tipo_concepto")
            if tipo in ("concepto_dinamico", "asiento_linea"):
                if item.json_path in seen_paths:
                    continue
                seen_paths.add(item.json_path)

                vars_out.append({
                    "label": item.label,
                    "valor": item.value,
                    "evidencia": {
                        "label_original": item.label,
                        "codigo": item.codigo,
                        "json_path": item.json_path,
                        "raw": item.raw,
                        "attributes": item.attributes,
                    }
                })

        return vars_out
