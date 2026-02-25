from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..models import IndexedItem, IndexedSource


def build_json_path(parts: List[Any]) -> str:
    path = ""
    for p in parts:
        if isinstance(p, int):
            path += f"[{p}]"
        else:
            path = f"{path}.{p}" if path else str(p)
    return path


def extract_periodo(metadata: Dict[str, Any]) -> Optional[str]:
    iso = metadata.get("periodo_iso")
    if iso and isinstance(iso, str) and len(iso) == 7 and "-" in iso:
        return iso

    for key in ("periodo_detectado", "periodo_display"):
        val = metadata.get(key)
        if val and isinstance(val, str) and "/" in val:
            parts = val.strip().split("/")
            if len(parts) == 2:
                mm, yyyy = parts[0].zfill(2), parts[1]
                if len(yyyy) == 4 and yyyy.isdigit() and mm.isdigit():
                    return f"{yyyy}-{mm}"

    return None


class BaseIndexer(ABC):

    def __init__(self, source_name: str):
        self.source_name = source_name

    def index(self, parser_json: Dict[str, Any]) -> IndexedSource:
        metadata = parser_json.get("metadata", {})
        periodo = extract_periodo(metadata)
        meta = {
            "contribuyente": metadata.get("contribuyente"),
            "cuit": metadata.get("cuit"),
            "tipo_documento": metadata.get("tipo_documento"),
            "fecha_emision": metadata.get("fecha_emision"),
        }

        raw_items = self._index_items(parser_json)

        seen: Dict[str, bool] = {}
        items: List[IndexedItem] = []
        for item in raw_items:
            if item.json_path not in seen:
                seen[item.json_path] = True
                items.append(item)

        return IndexedSource(source=self.source_name, periodo=periodo, items=items, meta=meta)

    @abstractmethod
    def _index_items(self, parser_json: Dict[str, Any]) -> List[IndexedItem]:
        ...

    def _make_item(
        self,
        json_path: str,
        label: Optional[str],
        value: Any,
        raw: str,
        codigo: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[IndexedItem]:
        if value is None or not isinstance(value, (int, float)):
            return None
        return IndexedItem(
            json_path=json_path,
            label=label,
            value=float(value),
            raw=raw,
            codigo=codigo,
            attributes=attributes or {},
        )