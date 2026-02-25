from __future__ import annotations

from typing import Any, Dict, List

from .base import BaseIndexer, build_json_path
from ..models import IndexedItem


class F931Indexer(BaseIndexer):

    def __init__(self):
        super().__init__("f931")

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

        # suma_remuneraciones (lista)
        for i, rem in enumerate(tablas.get("suma_remuneraciones", []) or []):
            if not isinstance(rem, dict):
                continue
            item = self._make_item(
                json_path=build_json_path(["extracted", "tablas", "suma_remuneraciones", i, "value"]),
                label=rem.get("label"),
                value=rem.get("value"),
                raw=str(rem.get("raw", "")),
                attributes={"tipo_concepto": "remuneracion", "numero": rem.get("numero")},
            )
            if item:
                items.append(item)

        # secciones con estructura dict de conceptos
        for seccion in (
            "seccion_I_seg_social",
            "seccion_II_obras_sociales",
            "seccion_III_retenciones",
            "seccion_VI_lrt",
            "seccion_VII_seguro_vida",
        ):
            for concept_key, concepto in (tablas.get(seccion, {}) or {}).items():
                if not isinstance(concepto, dict):
                    continue
                item = self._make_item(
                    json_path=build_json_path(["extracted", "tablas", seccion, concept_key, "value"]),
                    label=concepto.get("label") or concept_key,
                    value=concepto.get("value"),
                    raw=str(concepto.get("raw", "")),
                    attributes={
                        "tipo_concepto": concepto.get("tipo_concepto", "declarado"),
                        "seccion": seccion,
                    },
                )
                if item:
                    items.append(item)

        # seccion_VIII_montos (códigos AFIP)
        for concept_key, concepto in (tablas.get("seccion_VIII_montos", {}) or {}).items():
            if not isinstance(concepto, dict):
                continue
            item = self._make_item(
                json_path=build_json_path(["extracted", "tablas", "seccion_VIII_montos", concept_key, "value"]),
                label=concepto.get("nombre") or concepto.get("label") or concept_key,
                value=concepto.get("value"),
                raw=str(concepto.get("raw", "")),
                codigo=concepto.get("codigo"),
                attributes={
                    "tipo_concepto": concepto.get("tipo_concepto", "a_pagar"),
                    "seccion": "seccion_VIII_montos",
                    "categoria": concepto.get("categoria"),
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