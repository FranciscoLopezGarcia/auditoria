"""
parsers/borrador_parser.py
---------------------------
Parser para el Borrador de la Declaración Jurada (AFIP/ARCA).

ESTRATEGIA:
El borrador es un documento HTML renderizado como PDF, con dos columnas
de layout visual pero texto extraído de manera más lineal.

Tenemos dos tipos de datos:
1. Pares label:valor en líneas separadas o en la misma línea
   Ej: "Rem. Total: 27.380.973,46  Sumatoria de Remuneraciones"
2. Tablas de totales donde el valor está a la derecha del label
   Ej: "Aportes:  3.122.675,83"

ENFOQUE:
- Para los datos de cabecera (CUIT, período, etc.): regex sobre texto plano.
- Para las remuneraciones imponibles: regex iterativo buscando "Rem. Imponible N:".
- Para las tablas de totales: buscar el label y tomar el número más cercano
  a la derecha (misma línea o línea siguiente).

Criterio campos ausentes: si el label aparece pero el valor es 0,00 -> value=0.0
Si el label no aparece en el PDF -> campo ausente del JSON (no null forzado).
Rem. Imponibles del 1 al 11 se incluyen aunque sean 0,00 si aparecen en el PDF.
"""

import re
import logging
from pathlib import Path
from typing import Optional

from backend.core.utils.pdf_text import (
    extract_text, normalize_number,
    extract_periodo_from_filename, clean_lines
)

logger = logging.getLogger(__name__)

PARSER_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"


def parse(pdf_path: str) -> dict:
    path = Path(pdf_path)
    lines, num_pages = extract_text(str(path))
    lines_clean = clean_lines(lines)

    meta = _extract_metadata(lines_clean, path)

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

    try:
        result["extracted"]["campos_principales"] = _extract_campos_principales(lines_clean)
    except Exception as e:
        logger.warning(f"[borrador] Error en campos_principales: {e}")

    try:
        result["extracted"]["tablas"]["remuneraciones_imponibles"] = \
            _extract_rem_imponibles(lines_clean)
    except Exception as e:
        logger.warning(f"[borrador] Error en rem_imponibles: {e}")

    try:
        result["extracted"]["tablas"]["totales_generales"] = \
            _extract_totales_generales(lines_clean)
    except Exception as e:
        logger.warning(f"[borrador] Error en totales_generales: {e}")

    try:
        result["extracted"]["tablas"]["contribuciones_seguridad_social"] = \
            _extract_contribuciones_ss(lines_clean)
    except Exception as e:
        logger.warning(f"[borrador] Error en contribuciones_ss: {e}")

    try:
        result["extracted"]["tablas"]["aportes_seguridad_social"] = \
            _extract_aportes_ss(lines_clean)
    except Exception as e:
        logger.warning(f"[borrador] Error en aportes_ss: {e}")

    try:
        result["extracted"]["tablas"]["obra_social"] = _extract_obra_social(lines_clean)
    except Exception as e:
        logger.warning(f"[borrador] Error en obra_social: {e}")

    try:
        result["extracted"]["conceptos_dinamicos"] = \
            _extract_conceptos_dinamicos(lines_clean)
    except Exception as e:
        logger.warning(f"[borrador] Error en conceptos_dinamicos: {e}")

    return result


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def _periodo_to_iso(raw: str) -> Optional[str]:
    """Convierte 'MM/YYYY' → 'YYYY-MM'."""
    m = re.match(r"(\d{2})/(\d{4})", raw.strip())
    return f"{m.group(2)}-{m.group(1)}" if m else None


def _periodo_to_display(raw: str) -> Optional[str]:
    """Convierte 'MM/YYYY' → 'MM/YYYY' (mantiene el formato humano)."""
    return raw.strip() if re.match(r"\d{2}/\d{4}", raw.strip()) else None


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def _extract_metadata(lines: list[str], path: Path) -> dict:
    meta = {
        "source_file": path.name,
        "tipo_documento": "borrador_ddjj",
        "periodo_iso": None,        # YYYY-MM  (para indexación/ordenamiento)
        "periodo_display": None,    # MM/YYYY  (para presentación)
        "cuit": None,
        "contribuyente": None,
        "fecha_emision": None,
        "obra_social_codigo": None,
        "obra_social_nombre": None,
        "warnings": [],
        "parser_version": PARSER_VERSION,
    }

    raw_periodo = extract_periodo_from_filename(path.name)
    full_text = " ".join(lines)

    # CUIT
    m = re.search(r"C\.?U\.?I\.?T\.?\s*:?\s*(\d{2}-\d{8}-\d)", full_text, re.IGNORECASE)
    if m:
        meta["cuit"] = m.group(1)
    else:
        m = re.search(r"(\d{11})", full_text)
        if m:
            cuit_raw = m.group(1)
            meta["cuit"] = f"{cuit_raw[:2]}-{cuit_raw[2:10]}-{cuit_raw[10]}"

    # Contribuyente: cortar antes de cualquier día de la semana/fecha
    for line in lines:
        m = re.search(r"Contribuyente[:\s]+(.+)", line, re.IGNORECASE)
        if m:
            raw_c = m.group(1).strip()
            raw_c = re.split(
                r"\s+(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo),?\s+\d",
                raw_c, flags=re.IGNORECASE
            )[0].strip()
            meta["contribuyente"] = raw_c
            break

    # Período desde contenido PDF (prioridad sobre nombre de archivo)
    for line in lines:
        m = re.search(r"Per[íi]odo[:\s]+(\d{2}/\d{4})", line, re.IGNORECASE)
        if m:
            raw_periodo = m.group(1)
            break

    if raw_periodo:
        meta["periodo_iso"] = _periodo_to_iso(raw_periodo)
        meta["periodo_display"] = _periodo_to_display(raw_periodo)
    else:
        meta["warnings"].append({
            "codigo": "PERIODO_NO_DETECTADO",
            "severidad": "warning",
            "mensaje": "No se pudo detectar el período del documento",
            "detalle": {}
        })

    # Fecha de emisión
    for line in lines:
        m = re.search(r"\d{1,2}\s+de\s+\w+\s+de\s+\d{4}", line, re.IGNORECASE)
        if m:
            meta["fecha_emision"] = m.group(0)
            break

    # Obra social
    for line in lines:
        m = re.search(r"Obra Social[:\s]+(\d+)\s*[-–]\s*(.+)", line, re.IGNORECASE)
        if m:
            meta["obra_social_codigo"] = m.group(1)
            meta["obra_social_nombre"] = m.group(2).strip()
            break

    return meta


# ---------------------------------------------------------------------------
# Campos principales
# ---------------------------------------------------------------------------

def _extract_campos_principales(lines: list[str]) -> dict:
    """
    Extrae campos de encabezado: empleados, versión, tipo de declaración, etc.
    También extrae Rem. Total y Conceptos No Remunerativos.
    """
    campos = {}
    full_text = "\n".join(lines)

    simple_patterns = {
        "cantidad_empleados": r"Cantidad de empleados[:\s]+(\d+)",
        "version": r"Versi[oó]n[:\s]*:?\s*(\d+)",
        "tipo_declaracion": r"Tipo de declaraci[oó]n[:\s]+(.+?)(?:\n|Servicios)",
        "servicios_eventuales": r"Servicios Eventuales[:\s]+(S[íi]|No)",
        "corresponde_reducciones": r"Corresponde reducciones[:\s]+(S[íi]|No)",
        "tipo_empleador": r"Tipo de empleador[:\s]+(.+?)(?:\n|Actividad)",
        "actividad": r"Actividad[:\s]+(.+?)(?:\n|Obra)",
        "rem_total": r"Rem\.\s*Total[:\s]*([\d.,]+)",
        "conceptos_no_remunerativos": r"Conceptos No remun\.[:\s]*([\d.,]+)",
        "asig_fam_pagadas": r"Asig\.\s*Fam\.\s*pagadas[:\s]*([\d.,]+)",
    }

    for field, pattern in simple_patterns.items():
        m = re.search(pattern, full_text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            # Intentar convertir a número si parece un número
            num = normalize_number(raw) if re.match(r"[\d.,]+", raw) else None
            campos[field] = {
                "value": num if num is not None else raw,
                "raw": raw,
                "label": field,
            }
        else:
            logger.warning(f"[borrador] Campo no encontrado: {field}")

    return campos


# ---------------------------------------------------------------------------
# Remuneraciones imponibles 1..11
# ---------------------------------------------------------------------------

def _extract_rem_imponibles(lines: list[str]) -> list[dict]:
    """
    Extrae Rem. Imponible 1 a 11.

    Fix #5: Rem. 11 tiene el valor en una línea ("Rem. Imponible 11: 0,00") y
    la descripción ("Contribuciones Dcto 14/20 PAMI, Fondo Nacional de Empleo y Asig.")
    se parte en dos líneas, con la segunda comenzando "Familiares". El patrón DOTALL
    capturaba ese fragmento junto con el texto de "Conceptos No remun." siguiente.

    Solución: limpiar la descripción cortando en el primer salto de línea que
    empiece con un token que claramente no es parte de la descripción
    (mayúscula + no es continuación de frase).
    """
    result = []
    full_text = "\n".join(lines)

    pattern = re.compile(
        r"Rem\.\s*Imponible\s*(\d{1,2})[:\s]*([\d.,]+)\s*(.*?)(?=Rem\.\s*Imponible|\Z)",
        re.IGNORECASE | re.DOTALL
    )

    # Patrones que indican que la descripción terminó (inicio de otro campo)
    DESCRIPCION_STOP = re.compile(
        r"\n\s*(Conceptos No|Asig\. Fam|Totales generales|Contribuciones Seguridad|"
        r"Aportes de Seguridad|Contribuciones de Obra|Obra Social Aportes)",
        re.IGNORECASE
    )

    for m in pattern.finditer(full_text):
        num = int(m.group(1))
        raw = m.group(2)
        raw_desc = m.group(3)

        # Cortar la descripción en el primer stop-token
        stop = DESCRIPCION_STOP.search(raw_desc)
        if stop:
            raw_desc = raw_desc[:stop.start()]

        # Normalizar espacios y saltos de línea dentro de la descripción
        descripcion = re.sub(r"\s+", " ", raw_desc).strip()

        # Fix #5: si la descripción resultante es una sola palabra suelta
        # que empieza con mayúscula y tiene menos de 15 chars, es un fragmento
        # de línea rota (ej: "Familiares" que quedó colgada de la Rem 11).
        # En ese caso, la descartamos en lugar de guardar ruido.
        if re.match(r'^[A-ZÁÉÍÓÚ][a-záéíóú]+$', descripcion) and len(descripcion) < 15:
            descripcion = ""

        descripcion = descripcion[:120]

        # v1.0.0: separar descripción limpia de referencia legal
        # Ej: "Contribuciones Previsionales y PAMI - Ley 27.430" →
        #     descripcion_limpia: "Contribuciones Previsionales y PAMI"
        #     referencia_legal:   "Ley 27.430"
        LEY_REF = re.compile(r"\s*[-–]?\s*(Ley|Decreto|Dcto\.?)\s+[\d./]+.*$", re.IGNORECASE)
        descripcion_limpia = LEY_REF.sub("", descripcion).strip() or None
        m_ley = LEY_REF.search(descripcion)
        referencia_legal = m_ley.group(0).strip(" -–") if m_ley else None

        entry = {
            "numero": num,
            "label": f"Rem. Imponible {num}",
            "value": normalize_number(raw),
            "raw": raw,
            "descripcion": descripcion,
            "descripcion_limpia": descripcion_limpia,
        }
        if referencia_legal:
            entry["referencia_legal"] = referencia_legal
        result.append(entry)

    if not result:
        logger.warning("[borrador] No se encontraron remuneraciones imponibles")

    return sorted(result, key=lambda x: x["numero"])


# ---------------------------------------------------------------------------
# Totales generales
# ---------------------------------------------------------------------------

def _extract_totales_generales(lines: list[str]) -> dict:
    """
    Extrae la sección "Totales generales".

    v1.0.0: agrega semántica de categoría a cada campo:
    - total_global_no_operativo: total_general (suma de todas las secciones,
      no se usa para reconciliación parcial → excluir_de_normalizacion=True)
    - total_seccion: totales de cada régimen (SS, OS, LRT, SCVO)
    - concepto_operativo: aportes y contribuciones individuales
    """
    totales = {}
    full_text = "\n".join(lines)

    # (field_name, pattern, categoria, excluir_de_normalizacion)
    patterns = [
        ("seg_social_aportes",         r"Seguridad Social\s+Aportes[:\s]*([\d.,]+)",               "concepto_operativo",        False),
        ("seg_social_contribuciones",  r"Contribuciones[:\s]*([\d.,]+)(?=\s*Contribuciones RENATRE)", "concepto_operativo",      False),
        ("contrib_renatre",            r"Contribuciones RENATRE[:\s]*([\d.,]+)",                    "concepto_operativo",        False),
        ("seg_sepelio_uatre",          r"Seg\.\s*Sepelio UATRE[:\s]*([\d.,]+)",                    "concepto_operativo",        False),
        ("obra_social_aportes",        r"Obra Social\s+Aportes[:\s]*([\d.,]+)",                     "concepto_operativo",        False),
        ("obra_social_contribuciones", r"Obra Social.*?Contribuciones[:\s]*([\d.,]+)",              "concepto_operativo",        False),
        ("lrt",                        r"(?:Otros\s+)?LRT[:\s]*([\d.,]+)",                         "concepto_operativo",        False),
        ("seguro_colectivo_vida",      r"Seguro Colectivo de Vida Obligatorio[:\s]*([\d.,]+)",      "concepto_operativo",        False),
        ("vales_alimentarios",         r"Vales Alimentarios[:\s]*([\d.,]+)",                        "concepto_operativo",        False),
        # total_general es la suma de todos los anteriores: es informativo pero
        # no debe usarse como operando en reconciliaciones parciales
        ("total_general",              r"Total\s+([\d.,]+)(?=\s*Contribuciones Seguridad)",         "total_global_no_operativo", True),
    ]

    for field, pattern, categoria, excluir in patterns:
        m = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
        if m:
            raw = m.group(1)
            entry = {
                "value": normalize_number(raw),
                "raw": raw,
                "label": field,
                "categoria": categoria,
            }
            if excluir:
                entry["excluir_de_normalizacion"] = True
            totales[field] = entry
        else:
            logger.warning(f"[borrador] Total no encontrado: {field}")

    return totales


# ---------------------------------------------------------------------------
# Contribuciones de Seguridad Social (tabla detallada)
# ---------------------------------------------------------------------------

def _extract_contribuciones_ss(lines: list[str]) -> dict:
    """
    v1.0.0: campos con categoria explícita.
    - concepto_operativo: valores individuales que entran en reconciliación.
    - subtotal_tecnico: subtotales calculados por AFIP (no usar como operandos directos).
    """
    full_text = "\n".join(lines)

    # (field, pattern, categoria)
    patterns = [
        ("previsional_determinadas", r"Previsional[:\s]*([\d.,]+)\s+([\d.,]+|0,00)",  "concepto_operativo"),
        ("inssjp",                   r"INSSJP[:\s]*([\d.,]+)",                        "concepto_operativo"),
        ("contrib_tarea_dif",        r"Contrib\.\s*Tarea Dif\.[:\s]*([\d.,]+)",       "concepto_operativo"),
        ("asignaciones_familiares",  r"Asignaciones Familiares[:\s]*([\d.,]+)",        "concepto_operativo"),
        ("fne",                      r"FNE[:\s]*([\d.,]+)",                            "concepto_operativo"),
        ("anssal_contrib",           r"ANSSAL[:\s]*([\d.,]+)",                         "concepto_operativo"),
        ("subtotal_contrib_ss",      r"Subtotal Contribuciones SS[:\s]*([\d.,]+)",     "subtotal_tecnico"),
        ("asig_fam_compensadas",     r"Asig\.\s*Fam\.\s*Compensadas[:\s]*([\d.,]+)",  "concepto_operativo"),
        ("detraccion_art23",         r"Detracci[oó]n art\.\s*23[^:]*:[:\s]*([\d.,]+)","concepto_operativo"),
        ("retenciones_aplicadas_ss", r"Retenciones aplicadas[:\s]*([\d.,]+)(?=\s*Total Contribuciones SS)", "concepto_operativo"),
        ("total_contrib_ss",         r"Total Contribuciones SS[:\s]*([\d.,]+)",        "subtotal_tecnico"),
    ]

    NUMEROS_LEYES = re.compile(r"^(27\.541|27\.430|25\.922|814|788|1273)$")
    result = {}

    for field, pattern, categoria in patterns:
        m = re.search(pattern, full_text, re.IGNORECASE)
        if m:
            raw = m.group(1)
            if NUMEROS_LEYES.match(raw.strip()):
                logger.warning(f"[borrador] {field}: valor descartado por ser número de ley: {raw!r}")
                result[field] = {"value": None, "raw": raw, "label": field,
                                  "categoria": categoria, "warning": "valor_es_numero_de_ley"}
            else:
                result[field] = {"value": normalize_number(raw), "raw": raw,
                                  "label": field, "categoria": categoria}

    return result


# ---------------------------------------------------------------------------
# Aportes de Seguridad Social
# ---------------------------------------------------------------------------

def _extract_aportes_ss(lines: list[str]) -> dict:
    full_text = "\n".join(lines)

    patterns = {
        "previsional": r"Previsional[:\s]*([\d.,]+)(?=\s*INSSJP)",
        "inssjp": r"INSSJP[:\s]*([\d.,]+)(?=\s*Aporte Adicional)",
        "aporte_adicional": r"Aporte Adicional[:\s]*([\d.,]+)",
        "aporte_voluntario": r"Aporte Voluntario[:\s]*([\d.,]+)",
        "aporte_diferencial": r"Aporte Diferencial[:\s]*([\d.,]+)",
        "decreto_788": r"Decreto 788/05[:\s]*([\d.,]+)",
        "ap_personal_reg_esp": r"Ap\.\s*personal Reg\.\s*esp\.[:\s]*([\d.,]+)",
        "anssal_aportes": r"ANSSAL[:\s]*([\d.,]+)(?=\s*Excedentes)",
        "excedentes_aportes": r"Excedentes[:\s]*([\d.,]+)(?=\s*Total Aportes SS)",
        "total_aportes_ss": r"Total Aportes SS[:\s]*([\d.,]+)",
        "seg_sepelio_uatre_aportes": r"Seg\.\s*Sepelio UATRE[:\s]*([\d.,]+)(?=\s*Contribuciones de Obra)",
    }

    result = {}
    for field, pattern in patterns.items():
        m = re.search(pattern, full_text, re.IGNORECASE)
        if m:
            raw = m.group(1)
            result[field] = {"value": normalize_number(raw), "raw": raw, "label": field}

    return result


# ---------------------------------------------------------------------------
# Obra Social
# ---------------------------------------------------------------------------

def _extract_obra_social(lines: list[str]) -> dict:
    full_text = "\n".join(lines)

    patterns = {
        "contrib_os_total": r"Contribuciones[:\s]*([\d.,]+)(?=\s*Decreto 1273)",
        "decreto_1273": r"Decreto 1273[- ]2641[:\s]*([\d.,]+)",
        "excedentes_contrib_os": r"Excedentes[:\s]*([\d.,]+)(?=\s*Retenciones aplicadas)",
        "retenciones_aplicadas_os": r"Retenciones aplicadas[:\s]*([\d.,]+)(?=\s*Total Contribuciones OS)",
        "total_contrib_os": r"Total Contribuciones OS[:\s]*([\d.,]+)",
        "aportes_os": r"Aportes[:\s]*([\d.,]+)(?=\s*Excedentes)",
        "excedentes_aportes_os": r"Excedentes[:\s]*([\d.,]+)(?=\s*Total Aportes OS)",
        "total_aportes_os": r"Total Aportes OS[:\s]*([\d.,]+)",
    }

    result = {}
    for field, pattern in patterns.items():
        m = re.search(pattern, full_text, re.IGNORECASE)
        if m:
            raw = m.group(1)
            result[field] = {"value": normalize_number(raw), "raw": raw, "label": field}

    # Retenciones del período
    m = re.search(r"Del Per[íi]odo[:\s]*([\d.,]+)", full_text, re.IGNORECASE)
    if m:
        result["retenciones_del_periodo"] = {
            "value": normalize_number(m.group(1)),
            "raw": m.group(1),
            "label": "Retenciones del período",
        }

    return result


# ---------------------------------------------------------------------------
# Conceptos dinámicos: cualquier par label:valor no capturado antes
# ---------------------------------------------------------------------------

def _extract_conceptos_dinamicos(lines: list[str]) -> list[dict]:
    """
    Escanea líneas buscando pares label:valor no capturados antes.

    Fix #3: agrega tracking de sección activa para prefixar labels ambiguos.
    "Contribuciones: 2.812.150,80" dentro del bloque Seguridad Social
    queda como "Contribuciones SS", no simplemente "Contribuciones".

    HARDENING:
    - Solo acepta montos con formato argentino estricto (Regla A).
    - Excluye líneas con referencias a leyes/decretos, CUIT, fechas.
    - Prefija labels genéricos con el contexto de sección activo.
    """
    conceptos = []

    # Monto estricto: formato argentino completo
    MONTO_STRICT = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2}$")

    # Detectores de sección: cuando aparece uno de estos headers,
    # actualizamos current_section_prefix
    SECTION_HEADERS = [
        (re.compile(r"Seguridad Social\s+Aportes", re.IGNORECASE),     "Totales SS"),
        (re.compile(r"Contribuciones Seguridad Social", re.IGNORECASE), "SS"),
        (re.compile(r"Contribuciones de Obra Social", re.IGNORECASE),   "OS"),
        (re.compile(r"Obra Social\s+Aportes", re.IGNORECASE),           "Totales OS"),
        (re.compile(r"Aportes de Seguridad Social", re.IGNORECASE),     "Aportes SS"),
        (re.compile(r"Aportes de Obra Social", re.IGNORECASE),          "Aportes OS"),
        (re.compile(r"Totales generales", re.IGNORECASE),               "Totales"),
        (re.compile(r"Retenciones:", re.IGNORECASE),                    "Retenciones"),
    ]

    # Labels que necesitan prefijo de sección porque son genéricos y ambiguos
    AMBIGUOUS_LABELS = re.compile(
        r"^(Contribuciones|Aportes|Excedentes|Retenciones aplicadas|"
        r"Subtotal|Total|Previsional|INSSJP|ANSSAL|FNE)$",
        re.IGNORECASE
    )

    # Excluir líneas con referencias legales, CUIT, fechas o encabezados
    EXCLUIR = re.compile(
        r"(ley\s+\d{2}[\.,]\d+|decreto\s+\d|resoluci[oó]n\s+\d|"
        r"\d{2}-\d{8}-\d|"
        r"\d{2}[-/]\d{2}[-/]\d{4}|"
        r"^\s*\d{2}/\d{4}\s*$|"
        r"rem\.?\s*imponible|suma de rem|"
        r"contribuyente|período|versión)",
        re.IGNORECASE
    )

    pair_re = re.compile(r"^(.+?)[:\s]+([\d.,]+)\s*(.*)$")
    current_section = None

    for line in lines:
        # Actualizar sección activa
        for section_re, section_name in SECTION_HEADERS:
            if section_re.search(line):
                current_section = section_name
                break

        if EXCLUIR.search(line):
            continue

        m = pair_re.match(line)
        if not m:
            continue

        label = m.group(1).strip()
        raw   = m.group(2).strip()

        if not MONTO_STRICT.match(raw) or len(label) < 3:
            continue

        # Fix #3: prefixar si el label es ambiguo y tenemos contexto de sección
        if AMBIGUOUS_LABELS.match(label) and current_section:
            label_final = f"{label} {current_section}"
        else:
            label_final = label

        conceptos.append({
            "label": label_final,
            "value": normalize_number(raw),
            "raw": raw,
            "raw_line": line,
            "seccion": current_section,
            "contexto_adicional": m.group(3).strip(),
        })

    return conceptos