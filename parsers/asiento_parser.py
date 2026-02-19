"""
parsers/asiento_parser.py
--------------------------
Parser para el Asiento Contable mensual.

ESTRATEGIA DE PARSING:
El asiento tiene una estructura de tabla con columnas:
  [Descripción] [Parciales] [DEBE] [HABER]

El desafío principal es que las filas del DEBE y del HABER están
mezcladas verticalmente en el texto extraído. Usamos dos enfoques:

1. ENFOQUE COLUMNA (con pdfplumber coords):
   - Separamos palabras según su coordenada X.
   - X < umbral_debe  -> columna DEBE
   - X > umbral_haber -> columna HABER
   - Este enfoque es robusto ante variaciones de contenido.

2. ENFOQUE LÍNEAS (fallback con regex):
   - Detectamos líneas que empiezan con "a " -> son cuentas HABER.
   - Líneas con importe al final sin "a " -> son cuentas DEBE.
   - Buscamos secciones por headers en mayúsculas.

Criterio para campos ausentes:
  - Si un concepto tiene importe "$ -" o vacío -> value=null, raw="$ -"
  - Si un concepto no aparece en el PDF -> no se incluye en conceptos_dinamicos
    (preservamos la realidad del documento).
"""

import re
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from utils.pdf_text import (
    extract_text, extract_words_with_coords,
    normalize_number, extract_periodo_from_filename, clean_lines
)

logger = logging.getLogger(__name__)

PARSER_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"


def _normalize_label(label: str) -> str:
    """Normaliza un label para comparación case-insensitive y sin espacios extras."""
    return re.sub(r"\s+", " ", label.strip().lower())


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def parse(pdf_path: str) -> dict:
    """
    Parsea el asiento contable y retorna un dict con la estructura estándar.
    Nunca lanza excepciones: si algo falla, lo registra y continúa.
    """
    path = Path(pdf_path)
    lines, num_pages = extract_text(str(path))
    lines_clean = clean_lines(lines)

    meta = _extract_metadata(lines_clean, path)
    meta["warnings"] = []

    result = {
        "schema_version": SCHEMA_VERSION,
        "metadata": meta,
        "extracted": {
            "campos_principales": {},
            "tablas": {},
            "conceptos_dinamicos": [],
        },
        "raw": {
            "text_excerpt": lines[:30],
            "pages_detected": num_pages,
            "parser_version": PARSER_VERSION,
        }
    }

    campos = {}
    try:
        campos, sumas_warns = _extract_campos_principales(lines_clean)
        result["extracted"]["campos_principales"] = campos
        result["metadata"]["warnings"].extend(sumas_warns)
        for w in sumas_warns:
            lvl = w.get("severidad", "warning")
            (logger.error if lvl == "error" else logger.warning)(f"[asiento] {w}")
    except Exception as e:
        logger.warning(f"[asiento] Error en campos_principales: {e}")

    try:
        debe_haber = _extract_debe_haber_table(str(path), lines_clean)
        result["extracted"]["tablas"]["debe_haber"] = debe_haber
    except Exception as e:
        logger.warning(f"[asiento] Error en tabla debe_haber: {e}")

    try:
        # Pasar claves normalizadas de campos_principales para deduplicar
        cp_keys_norm = {_normalize_label(k) for k in campos}
        conceptos, cd_warns = _extract_conceptos_dinamicos(lines_clean, cp_keys_norm)
        result["extracted"]["conceptos_dinamicos"] = conceptos
        result["metadata"]["warnings"].extend(cd_warns)
        for w in cd_warns:
            logger.warning(f"[asiento] {w.get('mensaje', str(w))}")
    except Exception as e:
        logger.warning(f"[asiento] Error en conceptos_dinamicos: {e}")

    return result


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def _extract_metadata(lines: list[str], path: Path) -> dict:
    meta = {
        "source_file": path.name,
        "tipo_documento": "asiento_contable",
        "periodo_detectado": None,
        "cuit": None,
        "contribuyente": None,
        "fecha_emision": None,
        "parser_version": PARSER_VERSION,
    }

    # Período desde nombre de archivo
    meta["periodo_detectado"] = extract_periodo_from_filename(path.name)

    for line in lines:
        # Período desde el texto: "ASIENTO CONTABLE AL: 30-05-25"
        m = re.search(r"ASIENTO CONTABLE AL[:\s]+(\d{2}[-/]\d{2}[-/]\d{2,4})", line, re.IGNORECASE)
        if m:
            meta["fecha_emision"] = m.group(1)
            # Extraer período MM/YYYY desde la fecha
            parts = re.split(r"[-/]", m.group(1))
            if len(parts) == 3:
                anio = parts[2] if len(parts[2]) == 4 else "20" + parts[2]
                meta["periodo_detectado"] = meta["periodo_detectado"] or f"{parts[1]}/{anio}"

        # Contribuyente (primera línea suele ser el nombre)
        if re.match(r"^[A-Z][A-Z\s\.]{3,}$", line) and not meta["contribuyente"]:
            if not any(kw in line for kw in ["ASIENTO", "CONTABLE", "IMPUTACION", "DEBE", "HABER"]):
                meta["contribuyente"] = line.strip()

        # CUIT si aparece
        m = re.search(r"(\d{2}-\d{8}-\d)", line)
        if m:
            meta["cuit"] = m.group(1)

    return meta


# ---------------------------------------------------------------------------
# Campos principales: totales de secciones
# ---------------------------------------------------------------------------

def _extract_campos_principales(lines: list[str]) -> tuple[dict, list]:
    """
    Extrae los totales de las secciones principales del asiento.
    Retorna (campos, warnings).
    warnings incluye diferencia_debe_haber si DEBE ≠ HABER (fix #4).
    """
    campos = {}

    # Regla A (hardening): solo considerar monto válido si tiene formato argentino completo.
    # Acepta: 36.101,08 / 1.805.054,15 / 500.106,75
    # Rechaza: "3", "814", "27541" (números sueltos o de referencias legales)
    MONTO_STRICT = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")

    def strict_amounts_in_line(line: str) -> list[str]:
        """Retorna todos los montos con formato argentino estricto en la línea."""
        return MONTO_STRICT.findall(line)

    def last_strict_amount(line: str) -> Optional[str]:
        """
        Retorna el ÚLTIMO monto con formato argentino en la línea.
        En el asiento, cuando hay parcial + total en la misma línea
        (ej: 'IERIC 3 6.101,08 $ 36.101,08'), el último es siempre el importe contable.
        """
        found = strict_amounts_in_line(line)
        return found[-1] if found else None

    def first_strict_amount_after_label(line: str, label_pat: str) -> Optional[str]:
        """Primer monto estricto encontrado DESPUÉS del label en la línea."""
        m = re.search(label_pat, line, re.IGNORECASE)
        if not m:
            return None
        found = MONTO_STRICT.findall(line[m.end():])
        return found[0] if found else None

    # Campos donde el importe es el único o el primero después del label
    single_amount_fields = [
        ("sueldos_y_jornales_debe",  r"SUELDOS Y JORNALES"),
        ("credito_fiscal_dto814",    r"CREDITO FISCAL DTO\s*8\d+"),
        ("leyes_sociales",           r"LEYES SOCIALES"),
        ("art",                      r"A\.R\.T\."),
        ("fondo_de_cese",            r"FONDO DE CESE\b"),
    ]

    for field_name, label_pat in single_amount_fields:
        for line in lines:
            if re.search(label_pat, line, re.IGNORECASE):
                raw = first_strict_amount_after_label(line, label_pat)
                if raw:
                    campos[field_name] = {"value": normalize_number(raw), "raw": raw, "label": field_name}
                    break
        if field_name not in campos:
            logger.warning(f"[asiento] Campo no encontrado: {field_name}")

    # Campos con múltiples montos en la línea → tomar el ÚLTIMO (importe contable total).
    # "SEGURO DE VIDA OBLIGATORIO 9.371,04 $ 9.371,04"  → 9.371,04  ✓
    # "IERIC 3 6.101,08 $ 36.101,08"                    → 36.101,08 ✓
    # "UOCRA 3 6.101,08 $ 36.101,08"                    → 36.101,08 ✓
    # Regla B: si el último monto es < 100 pero hay montos mayores, tomar el mayor.
    multi_amount_fields = [
        ("seguro_vida_obligatorio",  r"SEGURO DE VIDA OBLIGATORIO"),
        ("ieric",                    r"^IERIC\b"),
        ("uocra",                    r"^UOCRA\b"),
    ]

    for field_name, label_pat in multi_amount_fields:
        for line in lines:
            if re.search(label_pat, line, re.IGNORECASE):
                all_amounts = strict_amounts_in_line(line)
                if not all_amounts:
                    break
                raw = all_amounts[-1]
                # Regla B: si el candidato es sospechosamente pequeño, tomar el mayor
                val = normalize_number(raw)
                if val is not None and val < 100:
                    converted = [(normalize_number(a), a) for a in all_amounts]
                    larger = [(v, r) for v, r in converted if v and v >= 100]
                    if larger:
                        raw = max(larger, key=lambda x: x[0])[1]
                campos[field_name] = {"value": normalize_number(raw), "raw": raw, "label": field_name}
                break
        if field_name not in campos:
            logger.warning(f"[asiento] Campo no encontrado: {field_name}")

    # Suma de sumas (control de cuadre) + Fix #4: warning si Debe ≠ Haber
    # Línea real: "SUMAS IGUALES $ 35.991.022,64 $ 35.991.022,65 -0,00"
    # El regex anterior no capturaba porque el $ antes de cada número rompía el patrón.
    # Solución: buscar la línea y extraer los dos primeros montos con formato estricto.
    full_text = "\n".join(lines)
    sumas_warnings = []
    MONTO_STRICT = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")

    for line in lines:
        if re.search(r"SUMAS IGUALES", line, re.IGNORECASE):
            montos = MONTO_STRICT.findall(line)
            if len(montos) >= 2:
                val_debe  = normalize_number(montos[0])
                val_haber = normalize_number(montos[1])
                campos["sumas_iguales_debe"]  = {"value": val_debe,  "raw": montos[0], "label": "SUMAS IGUALES DEBE"}
                campos["sumas_iguales_haber"] = {"value": val_haber, "raw": montos[1], "label": "SUMAS IGUALES HABER"}

                if val_debe is not None and val_haber is not None:
                    diferencia = round(abs(val_debe - val_haber), 2)
                    if diferencia > 0:
                        # Severidad: info si diff <= 0.01 (redondeo contable normal),
                        # warning si > 0.01, error si > 1.0
                        if diferencia <= 0.01:
                            severidad = "info"
                        elif diferencia <= 1.0:
                            severidad = "warning"
                        else:
                            severidad = "error"
                        sumas_warnings.append({
                            "codigo": "DIFERENCIA_DEBE_HABER",
                            "severidad": severidad,
                            "mensaje": f"Diferencia Debe/Haber: {diferencia}",
                            "detalle": {
                                "debe": val_debe,
                                "haber": val_haber,
                                "diferencia_absoluta": diferencia,
                                "diferencia_relativa_pct": round(diferencia / val_debe * 100, 6) if val_debe else None,
                            }
                        })
                        logger.warning(f"[asiento] Diferencia Debe/Haber: {diferencia} ({severidad})")
            break

    return campos, sumas_warnings


# ---------------------------------------------------------------------------
# Tabla DEBE/HABER con coordenadas
# ---------------------------------------------------------------------------

def _extract_debe_haber_table(pdf_path: str, lines_fallback: list[str]) -> list[dict]:
    """
    Estrategia principal: usa coordenadas X para separar columnas.

    La página del asiento tiene aprox:
      - Columna descripción: x < 300
      - Columna parciales: 300 < x < 400
      - Columna DEBE:  400 < x < 520
      - Columna HABER: x > 520

    Los umbrales se calibran dinámicamente buscando dónde están los headers
    "DEBE" y "HABER" en la página.

    Si falla, usa el fallback basado en líneas.
    """
    try:
        words = extract_words_with_coords(pdf_path)
        return _parse_columnas_con_coords(words)
    except Exception as e:
        logger.warning(f"[asiento] Extracción por coords falló: {e}. Usando fallback de líneas.")
        return _parse_columnas_fallback(lines_fallback)


def _parse_columnas_con_coords(words: list[dict]) -> list[dict]:
    """
    Agrupa palabras por fila (y0 similar) y luego asigna cada token
    a su columna según X.

    Retorna lista de filas con: {descripcion, parciales, debe, haber, raw_line}
    """
    if not words:
        return []

    # Detectar x de los headers DEBE y HABER para calibrar umbrales
    debe_x = None
    haber_x = None
    for w in words:
        if w["text"].upper() == "DEBE":
            debe_x = w["x0"]
        if w["text"].upper() == "HABER":
            haber_x = w["x0"]

    # Si no encontramos headers, usar umbrales razonables para A4
    if debe_x is None or haber_x is None:
        logger.warning("[asiento] No se encontraron headers DEBE/HABER, usando umbrales por defecto")
        debe_x = 380
        haber_x = 490

    # Umbral para separar descripción de parciales (mitad entre margen y DEBE)
    parciales_x = (debe_x + haber_x) / 2 - 30

    # Agrupar palabras por fila (y0 con tolerancia de 3px)
    rows = {}
    for w in words:
        y_key = round(w["y0"] / 3) * 3  # cuantizar a múltiplos de 3
        rows.setdefault(y_key, []).append(w)

    result = []
    for y_key in sorted(rows.keys()):
        row_words = sorted(rows[y_key], key=lambda w: w["x0"])

        desc_tokens = []
        parciales_tokens = []
        debe_tokens = []
        haber_tokens = []

        for w in row_words:
            if w["x0"] < parciales_x - 20:
                desc_tokens.append(w["text"])
            elif w["x0"] < debe_x - 10:
                parciales_tokens.append(w["text"])
            elif w["x0"] < haber_x - 10:
                debe_tokens.append(w["text"])
            else:
                haber_tokens.append(w["text"])

        descripcion = " ".join(desc_tokens).strip()
        parciales_raw = " ".join(parciales_tokens).strip()
        debe_raw = " ".join(debe_tokens).strip()
        haber_raw = " ".join(haber_tokens).strip()

        # Filtrar filas sin contenido relevante
        if not descripcion and not debe_raw and not haber_raw:
            continue

        # Determinar si es cuenta DEBE o HABER
        # Las cuentas "a pagar" suelen empezar con "a " en la descripción
        es_haber = descripcion.strip().lower().startswith(" a ") or \
                   re.match(r"^\s*a\s+[A-Z]", descripcion)

        row = {
            "descripcion": descripcion,
            "parciales": {
                "value": normalize_number(parciales_raw),
                "raw": parciales_raw,
            },
            "debe": {
                "value": normalize_number(debe_raw),
                "raw": debe_raw,
            },
            "haber": {
                "value": normalize_number(haber_raw),
                "raw": haber_raw,
            },
            "lado": "haber" if es_haber else "debe",
        }
        result.append(row)

    return result


def _parse_columnas_fallback(lines: list[str]) -> list[dict]:
    """
    Fallback cuando no hay coordenadas disponibles.
    Heurística:
      - Líneas que empiezan con " a " o "a " -> lado HABER
      - Resto con número al final -> lado DEBE
    """
    result = []
    number_re = re.compile(r"([\d.,]+)\s*$")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        es_haber = re.match(r"^\s*a\s+[A-ZÁÉÍÓÚ]", line, re.IGNORECASE) is not None

        m = number_re.search(stripped)
        raw_num = m.group(1) if m else ""

        row = {
            "descripcion": re.sub(r"\s*[\d.,]+\s*$", "", stripped).strip(),
            "parciales": {"value": None, "raw": ""},
            "debe": {
                "value": normalize_number(raw_num) if not es_haber else None,
                "raw": raw_num if not es_haber else "",
            },
            "haber": {
                "value": normalize_number(raw_num) if es_haber else None,
                "raw": raw_num if es_haber else "",
            },
            "lado": "haber" if es_haber else "debe",
        }
        result.append(row)

    return result


# ---------------------------------------------------------------------------
# Conceptos dinámicos: todos los conceptos variables del asiento
# ---------------------------------------------------------------------------

def _extract_conceptos_dinamicos(lines: list[str],
                                  cp_keys_norm: set | None = None) -> tuple[list[dict], list[dict]]:
    """
    Extrae conceptos contables variables del asiento.

    v1.0.0 cambios:
    - Acepta cp_keys_norm para deduplicar contra campos_principales.
      Un concepto dinámico cuyo normalized_label coincida con un campo principal
      se omite (ya está en campos_principales, duplicarlo genera ambigüedad).
    - Agrega normalized_label a cada concepto para facilitar indexación.
    - Labels duplicados por case se unifican (lower + strip).
    - Warnings homogéneos: dicts con codigo/severidad/mensaje/detalle.
    """
    if cp_keys_norm is None:
        cp_keys_norm = set()

    conceptos = []
    warnings = []
    seen_labels: set[str] = set()  # para deduplicar case-insensitive dentro de CD

    MONTO_STRICT = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")

    PALABRAS_CONTABLES = re.compile(
        r"\b(pagar|pago|retenci[oó]n|retenciones|fondo|sindicato|embargo|"
        r"anticipo|cuota|aporte|contribuci[oó]n|obra social|mutual|jornales|"
        r"sueldos|seguro|cese|sepelio|rnss|rnos|ieric|uocra|art\b|federal|"
        r"federaci[oó]n|alimentaria|judicial|osecac|faecys|amuppetrol|"
        r"redondeo|svo|leyes|retroactivo)\b",
        re.IGNORECASE
    )

    EXCLUIR = re.compile(
        r"(asiento contable al|imputaci[oó]n contable|importes|parciales|"
        r"debe\s*$|haber\s*$|sumas iguales|descripci[oó]n|importe|"
        r"\d{2}-\d{8}-\d|"
        r"\d{2}[-/]\d{2}[-/]\d{4}|"
        r"ley\s+\d{2}[\.\d]+|decreto\s+\d)",
        re.IGNORECASE
    )

    current_section = None

    for line in lines:
        stripped = line.strip()
        if len(stripped) < 3 or EXCLUIR.search(stripped):
            continue

        if stripped.isupper() and not MONTO_STRICT.search(stripped):
            current_section = stripped
            continue

        all_amounts = MONTO_STRICT.findall(stripped)
        if not all_amounts:
            continue

        if not PALABRAS_CONTABLES.search(stripped):
            continue

        # Seleccionar el monto correcto (último; Regla B si es < 100)
        raw_num = all_amounts[-1]
        val = normalize_number(raw_num)
        if val is not None and val < 100:
            larger = [normalize_number(a) for a in all_amounts if normalize_number(a) and normalize_number(a) >= 100]
            if larger:
                raw_num = next(a for a in reversed(all_amounts) if normalize_number(a) == max(larger))
                val = normalize_number(raw_num)

        # Warning homogéneo si hay múltiples montos
        if len(all_amounts) > 1:
            warnings.append({
                "codigo": "MULTIPLES_MONTOS_EN_LINEA",
                "severidad": "info",
                "mensaje": f"Múltiples montos en línea, tomando: {raw_num}",
                "detalle": {"raw_line": stripped, "montos_encontrados": all_amounts, "seleccionado": raw_num}
            })

        # Construir label limpio
        label = MONTO_STRICT.sub("", stripped)
        label = re.sub(r"[$\s]+$", "", label).strip()
        label = re.sub(r"^\s*a\s+", "", label, flags=re.IGNORECASE).strip()
        # Eliminar dígitos sueltos (1-3 chars) que quedan al quitar montos
        # Ej: "IERIC 3 6.101,08 $ 36.101,08" → quitando montos → "IERIC 3 $ " → "IERIC 3"
        #     el "3" es un parcial del PDF, no forma parte del label semántico
        label = re.sub(r"\s+\d{1,3}$", "", label).strip()
        label = re.sub(r"\s+\d{1,3}\s+", " ", label).strip()
        if not label:
            continue

        normalized = _normalize_label(label)

        # Deduplicar contra campos_principales
        if normalized in cp_keys_norm:
            continue

        # Deduplicar case-insensitive dentro de conceptos_dinamicos
        if normalized in seen_labels:
            warnings.append({
                "codigo": "LABEL_DUPLICADO_OMITIDO",
                "severidad": "info",
                "mensaje": f"Label duplicado omitido: {label!r}",
                "detalle": {"normalized_label": normalized}
            })
            continue
        seen_labels.add(normalized)

        es_haber = stripped.lstrip().lower().startswith("a ")
        conceptos.append({
            "label": label,
            "normalized_label": normalized,
            "value": val,
            "raw": raw_num,
            "raw_line": stripped,
            "categoria": "cuenta_haber" if es_haber else "cuenta_debe",
            "seccion_padre": current_section,
        })

    return conceptos, warnings