from __future__ import annotations

from typing import Any, Dict, Optional
from .base import BaseIndexer, iter_json, extract_periodo
from ..models import IndexedSource


class BorradorIndexer(BaseIndexer):
    def __init__(self):
        super().__init__("borrador")

    def index(self, parser_json: Dict[str, Any]) -> IndexedSource:
        periodo = extract_periodo(parser_json)
        items = []

        for path, node in iter_json(parser_json):
            if not isinstance(node, dict):
                continue
            if "value" in node and "raw" in node:
                val = node.get("value")
                if not isinstance(val, (int, float)):
                    continue

                label = node.get("label", path.split(".")[-1])
                attrs = {
                    "seccion": self._infer_seccion_from_node_or_path(node, path),
                    "categoria": node.get("seccion") or node.get("contexto_adicional"),
                    "tipo_concepto": self._infer_tipo_concepto(path),
                    "naturaleza": None,
                }
                items.append(self._make_item(label, val, None, path, node.get("raw"), attrs))

        return IndexedSource(source=self.source_name, periodo=periodo, items=items)

    def _infer_tipo_concepto(self, path: str) -> str:
        if ".extracted.campos_principales." in path:
            return "campo_principal"
        if ".extracted.tablas." in path:
            return "tabla"
        if ".extracted.conceptos_dinamicos" in path:
            return "concepto_dinamico"
        return "campo"

    def _infer_seccion_from_node_or_path(self, node: Dict[str, Any], path: str) -> Optional[str]:
        if "seccion" in node and node["seccion"] is not None:
            return str(node["seccion"])
        if ".extracted.tablas." in path:
            after = path.split(".extracted.tablas.", 1)[1]
            return after.split(".", 1)[0].split("[", 1)[0]
        if ".extracted.campos_principales." in path:
            return "campos_principales"
        if ".extracted.conceptos_dinamicos" in path:
            return "conceptos_dinamicos"
        return None
