"""
parsers/f931_parser.py
-----------------------
Parser para el Formulario F.931 (SUSS) definitivo.

ESTRATEGIA:
El F.931 es el formulario más estructurado de los tres.
Tiene secciones numeradas del I al VIII con labels fijos y valores numéricos.

Ventajas para el parsing:
- Los labels son consistentes (definidos por AFIP).
- La sección VIII tiene códigos numéricos fijos (301, 351, etc.).
- Los valores siempre tienen formato "label  valor" en la misma línea.

Desafíos:
- El layout tiene dos columnas (I-II, III-IV, V, VI-VII, VIII).
- pdfplumber puede extraer las columnas entrelazadas.
- Solución: buscar el label y el primer número que aparece después,
  con una ventana de contexto de 2 líneas.

Criterio campos ausentes: todos los campos de las secciones I-VIII
se intentan extraer. Si no se encuentra un label, se loguea warning
y no se incluye en el JSON (para distinguir "no está" de "es 0").
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
        result["extracted"]["campos_principales"] = _extract_cabecera(lines_clean)
    except Exception as e:
        logger.warning(f"[f931] Error en cabecera: {e}")

    try:
        result["extracted"]["tablas"]["suma_remuneraciones"] = _extract_sum_rem(lines_clean)
    except Exception as e:
        logger.warning(f"[f931] Error en suma_remuneraciones: {e}")

    try:
        result["extracted"]["tablas"]["seccion_I_seg_social"] = _extract_seccion_I(lines_clean)
    except Exception as e:
        logger.warning(f"[f931] Error en seccion_I: {e}")

    try:
        result["extracted"]["tablas"]["seccion_II_obras_sociales"] = _extract_seccion_II(lines_clean)
    except Exception as e:
        logger.warning(f"[f931] Error en seccion_II: {e}")

    try:
        result["extracted"]["tablas"]["seccion_III_retenciones"] = _extract_seccion_III(lines_clean)
    except Exception as e:
        logger.warning(f"[f931] Error en seccion_III: {e}")

    try:
        result["extracted"]["tablas"]["seccion_VI_lrt"] = _extract_seccion_VI(lines_clean)
    except Exception as e:
        logger.warning(f"[f931] Error en seccion_VI: {e}")

    try:
        result["extracted"]["tablas"]["seccion_VII_seguro_vida"] = _extract_seccion_VII(lines_clean)
    except Exception as e:
        logger.warning(f"[f931] Error en seccion_VII: {e}")

    try:
        result["extracted"]["tablas"]["seccion_VIII_montos"] = _extract_seccion_VIII(lines_clean)
    except Exception as e:
        logger.warning(f"[f931] Error en seccion_VIII: {e}")

    try:
        result["extracted"]["conceptos_dinamicos"] = _extract_leyes_especiales(lines_clean)
    except Exception as e:
        logger.warning(f"[f931] Error en leyes_especiales: {e}")

    return result


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def _extract_metadata(lines: list[str], path: Path) -> dict:
    meta = {
        "source_file": path.name,
        "tipo_documento": "f931",
        "periodo_iso": None,      # YYYY-MM  (para ordenamiento/indexación)
        "periodo_display": None,  # MM/YYYY  (para presentación)
        "cuit": None,
        "contribuyente": None,
        "fecha_emision": None,
        "art_codigo": None,
        "art_nombre": None,
        "seguro_colectivo_codigo": None,
        "seguro_colectivo_nombre": None,
        "domicilio_fiscal": None,
        "nro_verificador": None,
        "usuario_declarante": None,
        "warnings": [],
        "parser_version": PARSER_VERSION,
    }

    full_text = "\n".join(lines)
    periodo_pdf = None

    # Prioridad 1: desde el CONTENIDO del PDF (ventana de 3 líneas tras "Mes - Año")
    for i, line in enumerate(lines):
        if re.search(r"Mes\s*-\s*A[ñn]o", line, re.IGNORECASE):
            window = " ".join(lines[i:i+3])
            m = re.search(r"\b(\d{2}/\d{4})\b", window)
            if m:
                periodo_pdf = m.group(1)
                break

    # Prioridad 2: línea que empiece exactamente con MM/YYYY
    if not periodo_pdf:
        for line in lines:
            m = re.match(r"^\s*(\d{2}/\d{4})\b", line)
            if m:
                periodo_pdf = m.group(1)
                break

    # Fallback: nombre del archivo
    raw_periodo = periodo_pdf or extract_periodo_from_filename(path.name)

    if raw_periodo:
        parts = raw_periodo.split("/")
        if len(parts) == 2:
            mm, yyyy = parts[0].zfill(2), parts[1]
            meta["periodo_iso"] = f"{yyyy}-{mm}"
            meta["periodo_display"] = f"{mm}/{yyyy}"
        else:
            meta["periodo_iso"] = raw_periodo
            meta["periodo_display"] = raw_periodo

    if not meta["periodo_iso"]:
        meta["warnings"].append({
            "codigo": "PERIODO_NO_DETECTADO",
            "severidad": "warning",
            "mensaje": "No se pudo detectar el período del documento",
            "detalle": {}
        })
        logger.warning("[f931] No se pudo detectar el período")

    # CUIT
    m = re.search(r"C\.?U\.?I\.?T\.?\s*:?\s*(\d{2}-\d{8}-\d)", full_text, re.IGNORECASE)
    if m:
        meta["cuit"] = m.group(1)

    # Contribuyente
    for line in lines:
        m = re.search(r"Contribuyente[:\s]+(.+)", line, re.IGNORECASE)
        if m:
            meta["contribuyente"] = m.group(1).strip()
            break

    # Fecha de emisión
    for line in lines:
        m = re.search(r"\d{1,2}\s+de\s+\w+\s+de\s+\d{4}", line, re.IGNORECASE)
        if m:
            meta["fecha_emision"] = m.group(0)
            break

    # ART contratada
    m = re.search(r"ART Contratada[:\s]+(\d+)\s*[-–]\s*(.+)", full_text, re.IGNORECASE)
    if m:
        meta["art_codigo"] = m.group(1)
        meta["art_nombre"] = m.group(2).strip()

    # Seguro colectivo
    m = re.search(r"Seguro Colectivo[:\s]+(\w+)\s*[-–]\s*(.+)", full_text, re.IGNORECASE)
    if m:
        meta["seguro_colectivo_codigo"] = m.group(1)
        meta["seguro_colectivo_nombre"] = m.group(2).strip()

    # Domicilio fiscal
    m = re.search(r"Domicilio Fiscal[:\s]+(.+)", full_text, re.IGNORECASE)
    if m:
        meta["domicilio_fiscal"] = m.group(1).strip()

    # Número verificador
    m = re.search(r"(?:Nro|N[úu]m)\.?\s*Verificador[:\s]*(\d+)", full_text, re.IGNORECASE)
    if m:
        meta["nro_verificador"] = m.group(1)

    # Usuario declarante
    for line in lines:
        m = re.search(r"Usuario[:\s]+(.+)", line, re.IGNORECASE)
        if m:
            meta["usuario_declarante"] = m.group(1).strip()
            break

    return meta


# ---------------------------------------------------------------------------
# Cabecera: datos generales del formulario
# ---------------------------------------------------------------------------

def _extract_cabecera(lines: list[str]) -> dict:
    full_text = "\n".join(lines)

    # Fix #1: "tipo_declaracion" era semánticamente incorrecto.
    # El PDF dice: "Mes - Año Orig. (0) - Rect. (1/9): 0"
    # El valor 0 = declaración original, 1..9 = rectificativa N.
    # Se renombra a "indicador_rectificativa" y se agrega campo legible "es_rectificativa".
    patterns = {
        "empleados_en_nomina":    r"Empleados en n[oó]mina[:\s]+(\d+)",
        "mes_anio":               r"Mes\s*-\s*A[ñn]o.*?(\d{2}/\d{4})",
        "secuencia":              r"Secuencia[:\s]+(\d+)",
        "indicador_rectificativa": r"Orig\.\s*\(0\)\s*-\s*Rect\.\s*\(1/9\)[:\s]*(\d)",
        "servicios_eventuales":   r"Servicios Eventuales[:\s]+(S[íi]|No)",
    }

    result = {}
    for field, pattern in patterns.items():
        m = re.search(pattern, full_text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            num = normalize_number(raw) if re.match(r"[\d.,]+", raw) else None
            entry = {
                "value": num if num is not None else raw,
                "raw": raw,
                "label": field,
            }
            # Enriquecer indicador_rectificativa con campo semántico legible
            if field == "indicador_rectificativa":
                entry["es_rectificativa"] = (num is not None and num > 0)
                entry["descripcion"] = "Original" if num == 0.0 else f"Rectificativa {int(num)}"
            result[field] = entry
        else:
            logger.warning(f"[f931] Campo cabecera no encontrado: {field}")

    return result


# ---------------------------------------------------------------------------
# Suma de remuneraciones 1..10
# ---------------------------------------------------------------------------

def _extract_sum_rem(lines: list[str]) -> list[dict]:
    """
    El F.931 tiene "Suma de Rem. N: valor" (no "Rem. Imponible").
    """
    result = []
    full_text = "\n".join(lines)

    pattern = re.compile(
        r"Suma de Rem\.\s*(\d{1,2})[:\s]*([\d.,]+)",
        re.IGNORECASE
    )

    for m in pattern.finditer(full_text):
        num = int(m.group(1))
        raw = m.group(2)
        result.append({
            "numero": num,
            "label": f"Suma de Rem. {num}",
            "value": normalize_number(raw),
            "raw": raw,
        })

    if not result:
        logger.warning("[f931] No se encontraron sumas de remuneraciones")

    return sorted(result, key=lambda x: x["numero"])


# ---------------------------------------------------------------------------
# Secciones I a VIII
# ---------------------------------------------------------------------------

def _extract_labeled_value(full_text: str, label_pattern: str,
                             field_name: str,
                             tipo_concepto: str = "declarado") -> Optional[dict]:
    """Helper: busca label y extrae el primer número que sigue.
    tipo_concepto puede ser: declarado | subtotal_calculado | a_pagar
    """
    m = re.search(label_pattern + r"[:\s]*([\d.,]+)", full_text, re.IGNORECASE)
    if m:
        raw = m.group(1)
        return {
            "value": normalize_number(raw),
            "raw": raw,
            "label": field_name,
            "tipo_concepto": tipo_concepto,
        }
    logger.warning(f"[f931] No encontrado: {field_name}")
    return None


def _extract_seccion_I(lines: list[str]) -> dict:
    """
    Régimen Nacional de Seguridad Social.

    Fix #2: en vez de buscar en todo el texto (lo que causaba que valores de
    la Sección II se asignaran a la I), acotamos el bloque de texto entre el
    header "I - REGIMEN NACIONAL DE SEGURIDAD SOCIAL" y el inicio de la
    Sección III o el fin de la Sección II.

    Estructura del PDF (líneas relevantes):
      "I - REGIMEN NACIONAL DE SEGURIDAD SOCIAL  II - REGIMEN NACIONAL DE OBRAS SOCIALES"
      "a1 - Total de aportes 3.122.675,83           a1 - Total de aportes 570.849,81"
      ...

    Como ambos headers están en la misma línea, separamos usando el índice
    de columna de cada valor: los valores de SS están antes del centro de la
    línea; los de OS están después. Para el texto plano sin coords usamos
    el bloque desde el header hasta "III - RETENCIONES".
    """
    # Construir bloque SS: desde encabezado I hasta encabezado III
    full = "\n".join(lines)

    # Intentar extraer solo la porción del texto correspondiente a SS
    # Buscamos el bloque entre "SEGURIDAD SOCIAL" y "RETENCIONES"
    m_start = re.search(r"I\s*-\s*REGIMEN NACIONAL DE SEGURIDAD SOCIAL", full, re.IGNORECASE)
    m_end   = re.search(r"III\s*-\s*RETENCIONES", full, re.IGNORECASE)

    if m_start and m_end:
        bloque = full[m_start.start():m_end.start()]
    elif m_start:
        bloque = full[m_start.start():]
    else:
        bloque = full
        logger.warning("[f931] No se encontró header Sección I; buscando en texto completo")

    # Para valores que comparten línea con OS, necesitamos quedarnos con
    # el PRIMER número de cada patrón (que corresponde a SS, no a OS).
    # El helper estándar ya toma el primer número después del label,
    # y como SS aparece antes que OS en cada línea, esto funciona.

    def first_value(text: str, label_pat: str, field: str,
                    tipo_concepto: str = "declarado") -> Optional[dict]:
        m = re.search(label_pat + r"[:\s-]*([\d.,]+)", text, re.IGNORECASE)
        if m:
            raw = m.group(1)
            return {
                "value": normalize_number(raw),
                "raw": raw,
                "label": field,
                "tipo_concepto": tipo_concepto,
            }
        logger.warning(f"[f931] Sección I - no encontrado: {field}")
        return None

    result = {}
    # tipo_concepto semántico por campo:
    # a1/b_/b1 = declarado (calculado por AFIP desde las rem. imponibles)
    # a2/b2 = declarado (créditos a favor del contribuyente)
    # subtotal = subtotal_calculado (suma de líneas anteriores, no es operando)
    # a3/contribuciones_a_pagar/retenciones = a_pagar (monto final a ingresar)
    fields_ss = {
        "a1_total_aportes":          (r"a1\s*-\s*Total de aportes",                  "declarado"),
        "a2_aportes_a_favor":        (r"a2\s*-\s*Aportes a favor",                   "declarado"),
        "a3_aportes_ss_a_pagar":     (r"a3\s*-?\s*Aportes S\.S\. a pagar",           "a_pagar"),
        "b_asig_fam_pagadas":        (r"b\s*-\s*Asignaciones familiares pagadas",     "declarado"),
        "b1_total_contribuciones":   (r"b1\s*-\s*Total de contribuciones",            "declarado"),
        "b2_asig_compensadas":       (r"b2\s*-\s*Asignaciones compensadas",           "declarado"),
        "b3_detraccion_art23":       (r"b3\s*-\s*Detracci[oó]n art\.\s*23",          "declarado"),
        "subtotal_contrib_ss":       (r"Subtotal contribuciones S\.S\.",              "subtotal_calculado"),
        "contribuciones_ss_a_pagar": (r"Contribuciones S\.S\. a pagar",              "a_pagar"),
    }

    for field, (pat, tipo) in fields_ss.items():
        v = first_value(bloque, pat, field, tipo)
        if v:
            result[field] = v

    # Retenciones SS
    m = re.search(r"Retenciones\s+([\d.,]+)", bloque, re.IGNORECASE)
    if m:
        result["retenciones_ss"] = {
            "value": normalize_number(m.group(1)),
            "raw": m.group(1),
            "label": "retenciones_ss",
            "tipo_concepto": "a_pagar",
        }

    return result


def _extract_seccion_II(lines: list[str]) -> dict:
    """
    Régimen Nacional de Obras Sociales.

    Fix #2: acotamos el bloque entre "II - REGIMEN NACIONAL DE OBRAS SOCIALES"
    y "III - RETENCIONES". Como el header de SS y OS están en la misma línea,
    buscamos los labels exclusivos de OS (Aportes O.S., contribuciones O.S.)
    que no tienen equivalente en SS con esa forma.

    Para los campos compartidos (a1 - Total de aportes, b1 - Total de
    contribuciones) tomamos el SEGUNDO valor en la línea correspondiente,
    que pertenece a la columna OS.
    """
    full = "\n".join(lines)

    # Bloque II: desde header OS hasta III-RETENCIONES
    m_start = re.search(r"II\s*-\s*REGIMEN NACIONAL DE OBRAS SOCIALES", full, re.IGNORECASE)
    m_end   = re.search(r"III\s*-\s*RETENCIONES", full, re.IGNORECASE)

    if m_start and m_end:
        bloque = full[m_start.start():m_end.start()]
    elif m_start:
        bloque = full[m_start.start():]
    else:
        bloque = full
        logger.warning("[f931] No se encontró header Sección II; buscando en texto completo")

    # Helper: extrae el SEGUNDO valor numérico de una línea que contiene el label.
    # Las líneas de doble columna tienen: "label_ss  valor_ss  label_os  valor_os"
    # Al buscar en el bloque OS, el primer número es el valor OS correcto
    # (porque recortamos desde el header OS).
    def first_value_in_block(text: str, label_pat: str, field: str,
                              tipo_concepto: str = "declarado") -> Optional[dict]:
        m = re.search(label_pat + r"[:\s-]*([\d.,]+)", text, re.IGNORECASE)
        if m:
            raw = m.group(1)
            return {
                "value": normalize_number(raw),
                "raw": raw,
                "label": field,
                "tipo_concepto": tipo_concepto,
            }
        logger.warning(f"[f931] Sección II - no encontrado: {field}")
        return None

    result = {}

    unique_os_fields = {
        "a3_aportes_os_a_pagar":     (r"a3\s*-\s*Aportes O\.S\. a pagar",            "a_pagar"),
        "b2_excedentes_contrib_os":  (r"b2\s*-\s*Excedentes de contribuciones a favor", "declarado"),
        "subtotal_contrib_os":       (r"Subtotal contribuciones O\.S\.",               "subtotal_calculado"),
        "contribuciones_os_a_pagar": (r"Contribuciones O\.S\. a pagar",               "a_pagar"),
    }

    for field, (pat, tipo) in unique_os_fields.items():
        v = first_value_in_block(bloque, pat, field, tipo)
        if v:
            result[field] = v

    MONTO = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")

    shared_fields = {
        "a1_total_aportes_os":        (r"a1\s*-\s*Total de aportes",        "declarado"),
        "a2_aportes_a_favor_os":      (r"a2\s*-\s*Aportes a favor",         "declarado"),
        "b1_total_contribuciones_os": (r"b1\s*-\s*Total de contribuciones",  "declarado"),
    }

    for field, (pat, tipo) in shared_fields.items():
        found = False
        for line in lines:
            if re.search(pat, line, re.IGNORECASE):
                nums = MONTO.findall(line)
                if len(nums) >= 2:
                    raw = nums[1]
                elif len(nums) == 1:
                    raw = nums[0]
                else:
                    continue
                result[field] = {
                    "value": normalize_number(raw),
                    "raw": raw,
                    "label": field,
                    "tipo_concepto": tipo,
                }
                found = True
                break
        if not found:
            logger.warning(f"[f931] Sección II - no encontrado: {field}")

    # Retenciones OS
    m = re.search(r"Retenciones\s+([\d.,]+)", bloque, re.IGNORECASE)
    if m:
        result["retenciones_os"] = {
            "value": normalize_number(m.group(1)),
            "raw": m.group(1),
            "label": "retenciones_os",
            "tipo_concepto": "a_pagar",
        }

    return result


def _extract_seccion_III(lines: list[str]) -> dict:
    """Retenciones.
    tipo_concepto:
    - saldo anterior / retenciones del período / total = declarado
    - retenciones aplicadas_ss/os = a_pagar (se descuentan del saldo a ingresar)
    - saldo futuro = declarado (remanente para el período siguiente)
    """
    ft = "\n".join(lines)
    fields = [
        ("saldo_retenciones_periodo_anterior", r"Saldo retenciones per[íi]odo anterior",          "declarado"),
        ("retenciones_del_periodo",            r"Retenciones del per[íi]odo",                      "declarado"),
        ("total_retenciones",                  r"Total retenciones",                               "subtotal_calculado"),
        ("retenciones_aplicadas_ss",           r"Retenciones aplicadas a Seguridad Social",        "a_pagar"),
        ("retenciones_aplicadas_os",           r"Retenciones aplicadas a Obra Social",             "a_pagar"),
        ("saldo_retenciones_futuro",           r"Saldo de retenciones a per[íi]odo futuro",        "declarado"),
    ]

    result = {}
    for field, pattern, tipo in fields:
        v = _extract_labeled_value(ft, pattern, field, tipo)
        if v:
            result[field] = v
    return result


def _extract_seccion_VI(lines: list[str]) -> dict:
    """Ley de Riesgos de Trabajo."""
    ft = "\n".join(lines)

    result = {}

    # Cantidad de CUILES con ART y remun
    m = re.search(r"Cantidad de CUILES con ART\s+(\d+)\s+([\d.,]+)", ft, re.IGNORECASE)
    if m:
        result["cuiles_con_art"] = {"value": int(m.group(1)), "raw": m.group(1), "label": "Cantidad CUILES ART"}
        result["cuota_fija_art"] = {"value": normalize_number(m.group(2)), "raw": m.group(2), "label": "Cuota fija ART"}

    m = re.search(r"Remun\.\s*con ART\s+([\d.,]+)\s+([\d.,]+)", ft, re.IGNORECASE)
    if m:
        result["remun_con_art"] = {"value": normalize_number(m.group(1)), "raw": m.group(1), "label": "Remun. con ART"}
        result["calculo_art"] = {"value": normalize_number(m.group(2)), "raw": m.group(2), "label": "Cálculo ART"}

    m = re.search(r"L\.R\.T\.\s*total a pagar\s+([\d.,]+)", ft, re.IGNORECASE)
    if m:
        result["lrt_total_a_pagar"] = {"value": normalize_number(m.group(1)), "raw": m.group(1), "label": "LRT total a pagar"}

    # Ley 25.922
    m = re.search(r"Ley 25\.922.*?Porcentaje[:\s]*([\d.,]+).*?Resultado[:\s]*([\d.,]+)", ft, re.IGNORECASE | re.DOTALL)
    if m:
        result["ley_25922_porcentaje"] = {"value": normalize_number(m.group(1)), "raw": m.group(1), "label": "Ley 25922 %"}
        result["ley_25922_resultado"] = {"value": normalize_number(m.group(2)), "raw": m.group(2), "label": "Ley 25922 resultado"}

    # Ley 27.430 monto detraido
    m = re.search(r"Ley 27\.430.*?Monto Total Detra[íi]do[:\s]*([\d.,]+)", ft, re.IGNORECASE)
    if m:
        result["ley_27430_monto_detraido"] = {"value": normalize_number(m.group(1)), "raw": m.group(1), "label": "Ley 27.430 monto detraído"}

    return result


def _extract_seccion_VII(lines: list[str]) -> dict:
    """Seguro Colectivo de Vida Obligatorio."""
    ft = "\n".join(lines)
    result = {}

    m = re.search(r"Cuiles c/S\.C\.V\.O\.\s*-\s*Prima\s+(\d+)\s*-?\s*([\d.,]+)", ft, re.IGNORECASE)
    if m:
        result["cuiles_scvo"] = {"value": int(m.group(1)), "raw": m.group(1), "label": "Cuiles SCVO"}
        result["prima_scvo"] = {"value": normalize_number(m.group(2)), "raw": m.group(2), "label": "Prima SCVO"}

    m = re.search(r"Costo Emisi[oó]n[:\s]*([\d.,]+)", ft, re.IGNORECASE)
    if m:
        result["costo_emision"] = {"value": normalize_number(m.group(1)), "raw": m.group(1), "label": "Costo Emisión"}

    m = re.search(r"S\.C\.V\.O\.\s*a Pagar[:\s]*([\d.,]+)", ft, re.IGNORECASE)
    if m:
        result["scvo_a_pagar"] = {"value": normalize_number(m.group(1)), "raw": m.group(1), "label": "SCVO a Pagar"}

    return result


def _extract_seccion_VIII(lines: list[str]) -> dict:
    """
    Sección VIII - Montos que se ingresan.
    Los códigos (301, 351, etc.) están definidos por AFIP y son estables.
    Buscamos cada código y el valor que le sigue.
    """
    ft = "\n".join(lines)
    result = {}

    # Códigos AFIP con sus nombres
    codigos = {
        "351": "Contribuciones de Seguridad Social",
        "301": "Aportes de Seguridad Social",
        "360": "Contribuciones RENATRE",
        "352": "Contribuciones de Obra Social",
        "935": "Seg. Sepelio UATRE",
        "302": "Aportes de Obra Social",
        "270": "Vales Alimentarios/Cajas de alimentos",
        "312": "L.R.T.",
        "028": "Seguro Colectivo de Vida Obligatorio",
    }

    for codigo, nombre in codigos.items():
        pattern = rf"{codigo}\s*[-–]?\s*{re.escape(nombre[:20])}\s*([\d.,]+)"
        m = re.search(pattern, ft, re.IGNORECASE)
        if m:
            raw = m.group(1)
            result[f"cod_{codigo}"] = {
                "codigo": codigo,
                "nombre": nombre,
                "value": normalize_number(raw),
                "raw": raw,
                "categoria": "codigo_afip",
                "tipo_concepto": "a_pagar",
            }
        else:
            m = re.search(rf"\b{codigo}\b.*?([\d.,]+)", ft, re.IGNORECASE)
            if m:
                raw = m.group(1)
                result[f"cod_{codigo}"] = {
                    "codigo": codigo,
                    "nombre": nombre,
                    "value": normalize_number(raw),
                    "raw": raw,
                    "categoria": "codigo_afip",
                    "tipo_concepto": "a_pagar",
                }
            else:
                logger.warning(f"[f931] Código {codigo} ({nombre}) no encontrado")

    # Forma de pago
    m = re.search(r"Forma de Pago[:\s]+(\w+)", ft, re.IGNORECASE)
    if m:
        result["forma_de_pago"] = {"value": m.group(1), "raw": m.group(1), "label": "Forma de Pago"}

    return result


# ---------------------------------------------------------------------------
# Leyes especiales como conceptos dinámicos
# ---------------------------------------------------------------------------

def _extract_leyes_especiales(lines: list[str]) -> list[dict]:
    """
    Captura referencias a leyes/decretos que pueden variar por período.
    También captura cualquier "concepto nuevo" que no esté en los patrones fijos.
    """
    conceptos = []
    ley_re = re.compile(r"(Ley|Decreto|Resoluci[oó]n)\s*([\d./]+)\s*[:\-–]?\s*(.*?)\s*([\d.,]+)\s*$",
                         re.IGNORECASE)

    for line in lines:
        m = ley_re.match(line)
        if m:
            conceptos.append({
                "label": f"{m.group(1)} {m.group(2)} {m.group(3)}".strip(),
                "value": normalize_number(m.group(4)),
                "raw": m.group(4),
                "raw_line": line,
                "categoria": "ley_especial",
            })

    return conceptos