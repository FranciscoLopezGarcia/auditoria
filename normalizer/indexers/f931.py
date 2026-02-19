from __future__ import annotations

from typing import Any, Dict, Optional
from .base import BaseIndexer, iter_json, extract_periodo
from ..models import IndexedSource


class F931Indexer(BaseIndexer):
    """
    - Recorre TODO el JSON
    - Indexa solo conceptos operativos con value numérico (int/float)
    - Evita duplicación: nodo con value+raw+codigo+nombre => 1 solo IndexedItem
    """

    def __init__(self):
        super().__init__("f931")

    def index(self, parser_json: Dict[str, Any]) -> IndexedSource:
        periodo = extract_periodo(parser_json)
        items = []

        for path, node in iter_json(parser_json):
            if not isinstance(node, dict):
                continue

            # --- Caso especial: códigos (value+raw+codigo+nombre) => SOLO 1 item ---
            if {"codigo", "nombre", "value", "raw"}.issubset(node.keys()):
                val = node.get("value")
                if isinstance(val, (int, float)):
                    codigo = str(node.get("codigo"))
                    label = f"cod_{codigo}"
                    attrs = {
                        "seccion": "seccion_VIII_montos",
                        "categoria": "monto_ingreso",
                        "tipo_concepto": "codigo",
                        "naturaleza": None,
                        "nombre": node.get("nombre"),
                    }
                    items.append(self._make_item(label, val, codigo, path, node.get("raw"), attrs))
                continue  # IMPORTANT: evita duplicación por caer al bloque genérico

            # --- Bloque genérico: solo si value numérico ---
            if "value" in node and "raw" in node:
                val = node.get("value")
                if not isinstance(val, (int, float)):
                    continue

                label = node.get("label", path.split(".")[-1])
                codigo = node.get("codigo")  # puede existir en otros nodos, pero sin nombre
                attrs = {
                    "seccion": self._infer_seccion_from_path(path),
                    "categoria": None,
                    "tipo_concepto": "campo",
                    "naturaleza": None,
                }
                items.append(self._make_item(label, val, codigo, path, node.get("raw"), attrs))

        return IndexedSource(source=self.source_name, periodo=periodo, items=items)

    def _infer_seccion_from_path(self, path: str) -> Optional[str]:
        if ".extracted.tablas." in path:
            after = path.split(".extracted.tablas.", 1)[1]
            return after.split(".", 1)[0].split("[", 1)[0]
        if ".extracted.campos_principales." in path:
            return "campos_principales"
        if ".extracted.conceptos_dinamicos" in path:
            return "conceptos_dinamicos"
        return None
