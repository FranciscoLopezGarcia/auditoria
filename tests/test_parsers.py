"""
tests/test_parsers.py
----------------------
Test básico: corre los 3 parsers contra los PDFs de ejemplo y verifica
que se extrajeron los campos clave. También sirve como smoke test.

Uso:
    python tests/test_parsers.py

Requiere que los PDFs de ejemplo estén en ./pdfs_ejemplo/
"""

import sys
import json
import logging
from pathlib import Path

# Para importar los módulos locales sin instalar el paquete
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.asiento_parser import parse as parse_asiento
from parsers.borrador_parser import parse as parse_borrador
from parsers.f931_parser import parse as parse_f931
from utils.pdf_text import normalize_number

logging.basicConfig(level=logging.WARNING)  # Solo warnings en tests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_pdf(folder: Path, keywords: list[str]) -> Path | None:
    """Busca el PDF que contenga alguna de las palabras clave en el nombre."""
    for pdf in folder.glob("*.pdf"):
        name_lower = pdf.name.lower()
        if any(kw in name_lower for kw in keywords):
            return pdf
    return None


def assert_field(result: dict, path: str, description: str):
    """
    Verifica que un campo exista y tenga valor no nulo.
    path: "extracted.campos_principales.cuit" (dot notation)
    """
    parts = path.split(".")
    current = result
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            print(f"  ✗ FALTA: {description} (path: {path})")
            return False

    if current is not None and current != "":
        print(f"  ✓ {description}: {str(current)[:60]}")
        return True
    else:
        print(f"  ✗ NULO: {description} (path: {path})")
        return False


def count_non_null(d: dict, depth: int = 0) -> int:
    """Cuenta recursivamente los valores no nulos en un dict."""
    count = 0
    for v in d.values():
        if isinstance(v, dict):
            count += count_non_null(v, depth + 1)
        elif isinstance(v, list):
            count += len(v)
        elif v is not None:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_normalize_number():
    """Verifica la función de normalización de números."""
    print("\n[TEST] normalize_number")
    casos = [
        ("27.380.973,46", 27380973.46),
        ("$ 642.515,41", 642515.41),
        ("$ -", None),
        ("-", None),
        ("0,00", 0.0),
        ("9.371,04", 9371.04),
        ("", None),
        ("500.106,75", 500106.75),
    ]
    ok = 0
    for raw, expected in casos:
        result = normalize_number(raw)
        status = "✓" if result == expected else "✗"
        print(f"  {status} normalize_number({raw!r}) = {result} (esperado: {expected})")
        if result == expected:
            ok += 1
    print(f"  Resultado: {ok}/{len(casos)} casos OK")
    return ok == len(casos)


def test_asiento(pdf_path: Path) -> bool:
    print(f"\n[TEST] Asiento: {pdf_path.name}")
    result = parse_asiento(str(pdf_path))

    checks = [
        ("metadata.tipo_documento",        "tipo_documento"),
        ("metadata.periodo_detectado",     "período detectado"),
        ("extracted.campos_principales",   "campos_principales no vacío"),
        ("schema_version",                 "schema_version"),
    ]

    ok = all(assert_field(result, path, desc) for path, desc in checks)

    # Verificaciones específicas del asiento SUMPETROL
    campos = result.get("extracted", {}).get("campos_principales", {})
    conceptos = result.get("extracted", {}).get("conceptos_dinamicos", [])
    tabla = result.get("extracted", {}).get("tablas", {}).get("debe_haber", [])

    print(f"  → campos_principales extraídos: {len(campos)}")
    print(f"  → conceptos_dinamicos extraídos: {len(conceptos)}")
    print(f"  → filas tabla debe_haber: {len(tabla)}")

    # Verificar que haya al menos algún concepto
    if len(conceptos) == 0 and len(tabla) == 0:
        print("  ✗ No se extrajeron conceptos ni tabla!")
        ok = False
    else:
        print("  ✓ Al menos una estructura de datos extraída")

    return ok


def test_borrador(pdf_path: Path) -> bool:
    print(f"\n[TEST] Borrador: {pdf_path.name}")
    result = parse_borrador(str(pdf_path))

    checks = [
        ("metadata.cuit",          "CUIT"),
        ("metadata.contribuyente", "contribuyente"),
        ("metadata.periodo_iso",   "período ISO"),
        ("metadata.periodo_display", "período display"),
        ("schema_version",         "schema_version"),
    ]

    ok = all(assert_field(result, path, desc) for path, desc in checks)

    # Verificar que total_general tiene excluir_de_normalizacion
    totales = result.get("extracted", {}).get("tablas", {}).get("totales_generales", {})
    tg = totales.get("total_general", {})
    if tg.get("excluir_de_normalizacion") is True and tg.get("categoria") == "total_global_no_operativo":
        print("  ✓ total_general: categoria y excluir_de_normalizacion correctos")
    else:
        print("  ✗ total_general: falta categoria o excluir_de_normalizacion")
        ok = False

    # Verificar subtotal_contrib_ss tiene categoria subtotal_tecnico
    css = result.get("extracted", {}).get("tablas", {}).get("contribuciones_seguridad_social", {})
    stcss = css.get("subtotal_contrib_ss", {})
    if stcss.get("categoria") == "subtotal_tecnico":
        print("  ✓ subtotal_contrib_ss: categoria subtotal_tecnico correcta")
    else:
        print("  ✗ subtotal_contrib_ss: falta categoria subtotal_tecnico")
        ok = False

    # Verificar descripcion_limpia en rem imponible 10
    rem_imponibles = result.get("extracted", {}).get("tablas", {}).get("remuneraciones_imponibles", [])
    print(f"  → rem. imponibles extraídas: {len(rem_imponibles)}")
    if rem_imponibles:
        ri1 = next((r for r in rem_imponibles if r["numero"] == 1), None)
        if ri1:
            print(f"  → Rem. Imponible 1: {ri1['value']:,.2f}" if ri1['value'] else "  → Rem. Imponible 1: nulo")
        ri10 = next((r for r in rem_imponibles if r["numero"] == 10), None)
        if ri10 and "descripcion_limpia" in ri10:
            print(f"  ✓ Rem. 10 tiene descripcion_limpia: {ri10['descripcion_limpia']!r}")
        else:
            print("  ✗ Rem. 10 sin descripcion_limpia")

    totales = result.get("extracted", {}).get("tablas", {}).get("totales_generales", {})
    print(f"  → totales generales extraídos: {len(totales)}")
    campos = result.get("extracted", {}).get("campos_principales", {})
    print(f"  → campos_principales: {len(campos)}")

    return ok


def test_f931(pdf_path: Path) -> bool:
    print(f"\n[TEST] F.931: {pdf_path.name}")
    result = parse_f931(str(pdf_path))

    checks = [
        ("metadata.cuit",            "CUIT"),
        ("metadata.contribuyente",   "contribuyente"),
        ("metadata.periodo_iso",     "período ISO"),
        ("metadata.periodo_display", "período display"),
        ("schema_version",           "schema_version"),
    ]

    ok = all(assert_field(result, path, desc) for path, desc in checks)

    # Sección VIII: verificar categoria y tipo_concepto en cada código
    sec_viii = result.get("extracted", {}).get("tablas", {}).get("seccion_VIII_montos", {})
    print(f"  → códigos sección VIII extraídos: {len(sec_viii)}")
    codigos_clave = ["cod_301", "cod_351", "cod_312", "cod_028"]
    for cod in codigos_clave:
        if cod in sec_viii:
            entry = sec_viii[cod]
            has_cat = entry.get("categoria") == "codigo_afip"
            has_tipo = entry.get("tipo_concepto") == "a_pagar"
            nombre = entry.get("nombre", "")[:25]
            check = "✓" if (has_cat and has_tipo) else "✗"
            print(f"    {check} {cod} ({nombre}): {entry['value']:,.2f}")
            if not (has_cat and has_tipo):
                ok = False

    # Sección I: verificar tipo_concepto
    sec_i = result.get("extracted", {}).get("tablas", {}).get("seccion_I_seg_social", {})
    a3 = sec_i.get("a3_aportes_ss_a_pagar", {})
    if a3.get("tipo_concepto") == "a_pagar":
        print(f"  ✓ sec I a3_aportes_ss_a_pagar tipo_concepto=a_pagar")
    else:
        print(f"  ✗ sec I a3 sin tipo_concepto correcto: {a3.get('tipo_concepto')}")
        ok = False

    # Sumas de remuneraciones
    print(f"  → sumas de remuneraciones extraídas: {len(result.get('extracted', {}).get('tablas', {}).get('suma_remuneraciones', []))}")

    return ok


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def main():
    # Buscar PDFs en la carpeta pdfs_ejemplo (o en el directorio actual)
    search_dirs = [
        Path("pdfs_ejemplo"),
        Path("."),
        Path("../"),
    ]

    pdf_dir = None
    for d in search_dirs:
        if list(d.glob("*.pdf")):
            pdf_dir = d
            break

    if not pdf_dir:
        print("ERROR: No se encontraron PDFs en pdfs_ejemplo/ ni en el directorio actual.")
        print("Copiar los PDFs de prueba a pdfs_ejemplo/ y volver a ejecutar.")
        sys.exit(1)

    print(f"Buscando PDFs en: {pdf_dir.resolve()}")
    print("=" * 60)

    results = {}

    # Test de normalize_number (no requiere PDFs)
    results["normalize_number"] = test_normalize_number()

    # Encontrar y testear cada PDF
    asiento_pdf = find_pdf(pdf_dir, ["asiento"])
    borrador_pdf = find_pdf(pdf_dir, ["borrador", "borra"])
    f931_pdf = find_pdf(pdf_dir, ["f931", "931"])

    if asiento_pdf:
        results["asiento"] = test_asiento(asiento_pdf)
    else:
        print("\n⚠ No se encontró PDF de asiento (buscar 'asiento' en nombre)")

    if borrador_pdf:
        results["borrador"] = test_borrador(borrador_pdf)
    else:
        print("\n⚠ No se encontró PDF de borrador (buscar 'borrador' en nombre)")

    if f931_pdf:
        results["f931"] = test_f931(f931_pdf)
    else:
        print("\n⚠ No se encontró PDF de F.931 (buscar 'f931' en nombre)")

    # Resumen final
    print("\n" + "=" * 60)
    print("RESUMEN:")
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {status}: {test_name}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\n{passed}/{total} tests pasaron")

    # Guardar outputs JSON de ejemplo en ./outputs_test/
    output_dir = Path("outputs_test")
    output_dir.mkdir(exist_ok=True)

    for pdf_path, parser_func, tipo in [
        (asiento_pdf, parse_asiento, "asiento"),
        (borrador_pdf, parse_borrador, "borrador"),
        (f931_pdf, parse_f931, "f931"),
    ]:
        if pdf_path:
            try:
                result = parser_func(str(pdf_path))
                out_path = output_dir / f"{tipo}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"\nJSON guardado: {out_path}")
            except Exception as e:
                print(f"\nError guardando {tipo}.json: {e}")


if __name__ == "__main__":
    main()