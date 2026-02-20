"""
ExcelMapper v2 — Resolución row-based para structured, contains para dynamic.

Cambios respecto a v1:
  - Structured ahora es row-based: el YAML tiene entries con {row, path, type}
    → Resuelve el problema de labels duplicados (EXCEDENTES, RETENCIONES)
    → Soporta campos de texto (ORIGINAL/RECTIFICATIVA, FECHA)
    → Soporta acceso a arrays vía [N] en el path
  - Dynamic usa "contains": la clave del YAML se busca DENTRO del texto del Excel
    → Resuelve "FACYS" matcheando contra "FACYS (Descontado del bono)"
    → Es dirigido (solo entre claves del YAML), no búsqueda libre contra el JSON
  - Retorna None si no hay match (nunca 0.0)
"""

import yaml
import re
import unicodedata
from typing import Optional, Any


def normalize(text: str) -> str:
    """Normaliza texto: lowercase, sin acentos, sin espacios extra."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


# Regex para detectar acceso a array en paths: "key[N]"
_ARRAY_PATTERN = re.compile(r"^(.+)\[(\d+)\]$")


class ExcelMapper:

    def __init__(self, consolidated_json: dict):
        self.data = consolidated_json
        self.structured = self._load_yaml("excel/excel_mapping_structured.yaml")
        self.dynamic = self._load_yaml("excel/excel_mapping_dynamic.yaml")

        # Índice structured: { row_number: entry_dict }
        # Cada entry tiene: row, label, path, type (default "numeric")
        self._row_index = {}
        for entry in self.structured.get("entries", []):
            self._row_index[entry["row"]] = entry

        # Índice dynamic: lista de (normalized_key, config)
        # Se itera en orden para match por contains
        self._dynamic_entries = [
            (normalize(k), v) for k, v in self.dynamic.items()
        ]

    # -----------------------------------------------------------------
    def _load_yaml(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    # -----------------------------------------------------------------
    # Punto de entrada — ahora recibe row_num además del texto
    # -----------------------------------------------------------------
    def resolve_value(self, row_num: int, concepto_excel: str) -> Optional[Any]:
        """
        Dado el número de fila y el texto de columna B, busca el valor.

        Orden de resolución:
          1. Structured (por row_num) → navega path en el JSON
          2. Dynamic (por contains del texto) → busca en asiento.conceptos_dinamicos
          3. Sin match → None

        Retorna:
          float/str → valor encontrado
          None      → no hay mapeo (no tocar la celda)
        """

        # --- Fase 1: Structured (row-based) ---
        entry = self._row_index.get(row_num)
        if entry is not None:
            return self._resolve_structured(entry)

        # --- Fase 2: Dynamic (contains-match) ---
        concepto_norm = normalize(concepto_excel)
        for yaml_key_norm, config in self._dynamic_entries:
            if yaml_key_norm in concepto_norm:
                return self._resolve_dynamic(config)

        # --- Sin mapeo ---
        return None

    # -----------------------------------------------------------------
    # Structured: navega un path con soporte de arrays
    # -----------------------------------------------------------------
    def _resolve_structured(self, entry: dict) -> Optional[Any]:
        """
        Navega el path definido en el entry. Soporta:
          - Acceso a dict: "key1.key2.key3"
          - Acceso a array: "key[N]" donde N es el índice
          - Tipos: "numeric" (default) retorna float, "text" retorna str
        """
        path = entry.get("path", "")
        value_type = entry.get("type", "numeric")

        value = self._get_nested(path.split("."))

        if value is None:
            return None

        if value_type == "text":
            return str(value)

        # Numeric: solo retorna si es número real
        if isinstance(value, (int, float)):
            return float(value)

        return None

    # -----------------------------------------------------------------
    # Dynamic: busca en asiento.conceptos_dinamicos
    # -----------------------------------------------------------------
    def _resolve_dynamic(self, config: dict) -> Optional[float]:
        """
        Busca en los conceptos dinámicos del asiento usando los patterns
        de match_any. Acumula valores de coincidencias.
        Retorna None si no hay ningún match.
        """
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
        matches_found = 0

        for item in conceptos:
            label = normalize(item.get("normalized_label", ""))
            for pattern in patterns:
                if pattern in label:
                    total += float(item.get("value", 0))
                    matches_found += 1
                    break

        if matches_found == 0:
            return None

        return total

    # -----------------------------------------------------------------
    # Navegación genérica con soporte de arrays
    # -----------------------------------------------------------------
    def _get_nested(self, keys: list) -> Any:
        """
        Navega un dict/list anidado. Soporta:
          - Keys normales: accede a dict[key]
          - Keys con [N]: accede a list[N] y luego sigue navegando
            Ejemplo: "suma_remuneraciones[1]" → list[1]
        """
        obj = self.data
        for k in keys:
            if obj is None:
                return None

            # Chequeamos si la key tiene acceso a array: "name[N]"
            match = _ARRAY_PATTERN.match(k)
            if match:
                dict_key = match.group(1)
                index = int(match.group(2))

                # Primero accedemos al dict por la key
                if isinstance(obj, dict):
                    obj = obj.get(dict_key)
                else:
                    return None

                # Luego al array por índice
                if isinstance(obj, list) and 0 <= index < len(obj):
                    obj = obj[index]
                else:
                    return None
            else:
                # Key normal de dict
                if isinstance(obj, dict):
                    obj = obj.get(k)
                else:
                    return None

        return obj