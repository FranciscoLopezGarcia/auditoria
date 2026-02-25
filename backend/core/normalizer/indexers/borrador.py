from __future__ import annotations

from typing import Any, Dict, List

from .base import BaseIndexer, build_json_path
from ..models import IndexedItem


class BorradorIndexer(BaseIndexer):

    def __init__(self):
        super().__init__("borrador")

    def _index_items(self, parser_json: Dict[str, Any]) -> List[IndexedItem]:
        items: List[IndexedItem] = []
        extracted = parser_json.get("extracted", {})

        # campos_principales
        for field_key, campo in (extracted.get("campos_principales", {}) or {}).items():
            if not isinstance(campo, dict):
                continue
            item = self._make_item(
                json_path=build_json_path(["extracted", "campos_principales", field_key, "value"]),
                label=campo.get("label") or field_key,
                value=campo.get("value"),
                raw=str(campo.get("raw", "")),
                attributes={"tipo_concepto": "campo_principal"},
            )
            if item:
                items.append(item)

        tablas = extracted.get("tablas", {}) or {}

        # remuneraciones_imponibles (lista)
        for i, rem in enumerate(tablas.get("remuneraciones_imponibles", []) or []):
            if not isinstance(rem, dict):
                continue
            item = self._make_item(
                json_path=build_json_path(["extracted", "tablas", "remuneraciones_imponibles", i, "value"]),
                label=rem.get("label"),
                value=rem.get("value"),
                raw=str(rem.get("raw", "")),
                attributes={
                    "tipo_concepto": "remuneracion_imponible",
                    "numero": rem.get("numero"),
                    "descripcion": rem.get("descripcion_limpia") or rem.get("descripcion"),
                },
            )
            if item:
                items.append(item)

        # totales_generales (dict)
        for concept_key, concepto in (tablas.get("totales_generales", {}) or {}).items():
            if not isinstance(concepto, dict):
                continue
            item = self._make_item(
                json_path=build_json_path(["extracted", "tablas", "totales_generales", concept_key, "value"]),
                label=concepto.get("label") or concept_key,
                value=concepto.get("value"),
                raw=str(concepto.get("raw", "")),
                attributes={
                    "tipo_concepto": concepto.get("categoria", "concepto_operativo"),
                    "seccion": "totales_generales",
                },
            )
            if item:
                items.append(item)

        # conceptos_dinamicos
        for i, cd in enumerate(extracted.get("conceptos_dinamicos", []) or []):
            if not isinstance(cd, dict):
                continue
            item = self._make_item(
                json_path=build_json_path(["extracted", "conceptos_dinamicos", i, "value"]),
                label=cd.get("label"),
                value=cd.get("value"),
                raw=str(cd.get("raw", "")),
                attributes={"tipo_concepto": "concepto_dinamico", "categoria": cd.get("categoria")},
            )
            if item:
                items.append(item)

        return items