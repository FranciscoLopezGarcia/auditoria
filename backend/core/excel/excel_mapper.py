"""
ExcelMapper v3 — Resuelve valores para las hojas '931' y 'Analisis General'.

Arquitectura:
  La hoja '931' es el input principal (datos del F931).
  'Analisis General' tiene fórmulas que tiran a '931', salvo unas pocas
  celdas de input directo (conceptos no remun, RENATRE, UATRE, dinámicos).

YAMLs:
  - excel_mapping_931.yaml: entries con {row, col_offset, path, type}
  - excel_mapping_analisis.yaml: entries con {row, path, type}
  - excel_mapping_dynamic.yaml: conceptos dinámicos del asiento
"""

import re
import yaml
import unicodedata
from typing import Optional, Any
from pathlib import Path

def normalize(text: str) -> str:
    """Normaliza texto: lowercase, sin acentos, sin espacios extra."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


# Regex para acceso a array en paths: "key[N]"
_ARRAY_PATTERN = re.compile(r"^(.+)\[(\d+)\]$")


class ExcelMapper:

    def __init__(self, consolidated_json: dict):
        self.data = consolidated_json

        base_dir = Path(__file__).parent
        self.mapping_931 = self._load_yaml(str(base_dir / "excel_mapping_931.yaml"))
        self.mapping_analisis = self._load_yaml(str(base_dir / "excel_mapping_analisis.yaml"))
        self.mapping_dynamic = self._load_yaml(str(base_dir / "excel_mapping_dynamic.yaml"))

        # Índice analisis: { row: entry }
        self._analisis_index = {}
        for entry in self.mapping_analisis.get("entries", []):
            self._analisis_index[entry["row"]] = entry

        # Índice dynamic: [(normalized_key, config)]
        self._dynamic_entries = [
            (normalize(k), v) for k, v in self.mapping_dynamic.items()
        ]

    def _load_yaml(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    # =================================================================
    # Resolución para hoja '931'
    # =================================================================
    def get_931_values(self, month: int) -> list[dict]:
        """
        Retorna una lista de {row, col, value} para escribir en la hoja '931'.
        month: 1-12 (enero=1, ..., diciembre=12)
        """
        base_col = 2 + (month - 1) * 8
        results = []

        for entry in self.mapping_931.get("entries", []):
            row = entry["row"]
            col = base_col + entry["col_offset"]
            value = self._resolve_entry(entry)

            if value is not None:
                results.append({"row": row, "col": col, "value": value,
                                "label": entry.get("label", "")})

        return results

    # =================================================================
    # Resolución para 'Analisis General' (celdas de input directo)
    # =================================================================
    def resolve_analisis_value(self, row_num: int, concepto_text: str) -> Optional[Any]:
        """
        Para una fila de 'Analisis General', busca el valor.
        Primero intenta structured (por row), luego dynamic (por texto).
        Retorna None si no hay mapeo.
        """
        # Fase 1: Structured (por row)
        entry = self._analisis_index.get(row_num)
        if entry is not None:
            return self._resolve_entry(entry)

        # Fase 2: Dynamic (por contains del texto)
        concepto_norm = normalize(concepto_text)
        for yaml_key_norm, config in self._dynamic_entries:
            if yaml_key_norm in concepto_norm:
                return self._resolve_dynamic(config)

        return None

    # =================================================================
    # Resolución interna
    # =================================================================
    def _resolve_entry(self, entry: dict) -> Optional[Any]:
        """Resuelve un entry del YAML navegando el path."""
        path = entry.get("path", "")
        value_type = entry.get("type", "numeric")

        value = self._get_nested(path.split("."))

        if value is None:
            return None

        if value_type == "text":
            return str(value)

        if value_type == "rectificativa":
            # El Excel espera "Orig. (0) - Rect. (1/9): {raw}"
            return f"Orig. (0) - Rect. (1/9): {value}"

        # numeric
        if isinstance(value, (int, float)):
            return float(value)

        return None

    def _resolve_dynamic(self, config: dict) -> Optional[float]:
        """Busca en asiento.conceptos_dinamicos con match_any."""
        conceptos = (
            self.data
            .get("sources_raw", {})
            .get("asiento", {})
            .get("extracted", {})
            .get("conceptos_dinamicos", [])
        )

        patterns = config.get("match_any", [])
        if not patterns:
            return None

        total = 0.0
        matches = 0

        for item in conceptos:
            label = normalize(item.get("normalized_label", ""))
            for pattern in patterns:
                if pattern in label:
                    total += float(item.get("value", 0))
                    matches += 1
                    break

        return total if matches > 0 else None

    def _get_nested(self, keys: list) -> Any:
        """Navega dict/list anidado. Soporta key[N] para arrays."""
        obj = self.data
        for k in keys:
            if obj is None:
                return None
            match = _ARRAY_PATTERN.match(k)
            if match:
                dict_key, index = match.group(1), int(match.group(2))
                if isinstance(obj, dict):
                    obj = obj.get(dict_key)
                else:
                    return None
                if isinstance(obj, list) and 0 <= index < len(obj):
                    obj = obj[index]
                else:
                    return None
            else:
                if isinstance(obj, dict):
                    obj = obj.get(k)
                else:
                    return None
        return obj