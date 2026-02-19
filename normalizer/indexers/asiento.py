from __future__ import annotations

from typing import Any, Dict, List

from normalizer.indexers.base import BaseIndexer, build_json_path
from normalizer.models import IndexedItem


class AsientoIndexer(BaseIndexer):

    def __init__(self):
        super().__init__("asiento")

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

        # debe_haber: cada fila genera dos items separados (debe y haber)
        for i, fila in enumerate(extracted.get("tablas", {}).get("debe_haber", []) or []):
            if not isinstance(fila, dict):
                continue
            descripcion = fila.get("descripcion", "") or ""

            for lado in ("debe", "haber"):
                lado_data = fila.get(lado, {})
                if not isinstance(lado_data, dict):
                    continue
                item = self._make_item(
                    json_path=build_json_path(["extracted", "tablas", "debe_haber", i, lado, "value"]),
                    label=f"{descripcion}_{lado}" if descripcion else lado,
                    value=lado_data.get("value"),
                    raw=str(lado_data.get("raw", "")),
                    attributes={
                        "tipo_concepto": "asiento_linea",
                        "categoria": lado,
                        "descripcion": descripcion,
                        "fila_index": i,
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
                label=cd.get("label") or cd.get("normalized_label"),
                value=cd.get("value"),
                raw=str(cd.get("raw", "")),
                attributes={
                    "tipo_concepto": "concepto_dinamico",
                    "categoria": cd.get("categoria"),
                    "seccion_padre": cd.get("seccion_padre"),
                },
            )
            if item:
                items.append(item)

        return items