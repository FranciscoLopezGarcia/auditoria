# px_laboral — Parsers de PDFs para Papel de Trabajo Laboral
Sistema de extracción automática de datos desde los 3 PDFs mensuales que alimentan el Papel de Trabajo (Px) Laboral de auditoría.

## ¿Qué problema resuelve?

Cada mes se reciben 3 PDFs por cliente:
| PDF | Descripción |
|-----|-------------|
| Asiento contable | Registra el devengamiento de sueldos con columnas DEBE/HABER |
| Borrador de DDJJ | Resumen generado por AFIP antes de presentar el F.931 |
| F.931 definitivo | Declaración jurada presentada ante AFIP/ARCA (SUSS) |

Hasta ahora esos datos se cargaban manualmente al papel de trabajo. Este sistema los extrae automáticamente y genera un JSON estructurado por cada PDF, con trazabilidad completa (valor numérico + texto original + etiqueta).

## Estructura del proyecto

px_laboral/
├── parsers/
│   ├── asiento_parser.py     # Parser del asiento contable
│   ├── borrador_parser.py    # Parser del borrador de DDJJ
│   └── f931_parser.py        # Parser del F.931 definitivo
├── utils/
│   └── pdf_text.py           # Funciones compartidas (extracción, normalización)
├── tests/
│   └── test_parsers.py       # Tests contra PDFs reales
├── run_parse.py              # Entrypoint CLI
└── requirements.txt

## Instalación

**Requisitos:** Python 3.10 o superior.

# 1. Clonar o copiar el proyecto
cd px_laboral

# 2. Crear entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

## Uso rápido

# Colocar los PDFs del mes en una carpeta, por ejemplo ./pdfs/
# Los nombres deben contener las palabras clave: "asiento", "borrador", "f931"

python run_parse.py --input "./pdfs" --output "./outputs"

Esto genera en `./outputs/`:
- `<nombre>_asiento.json`
- `<nombre>_borrador.json`
- `<nombre>_f931.json`
- `resumen.json` con estadísticas de campos extraídos por archivo

### Opciones del CLI

python run_parse.py --input "./pdfs" --output "./outputs" --log-level DEBUG

| Parámetro | Descripción | Default |
|-----------|-------------|---------|
| `--input` | Carpeta con los PDFs a procesar | obligatorio |
| `--output` | Carpeta donde se guardan los JSON | obligatorio |
| `--log-level` | Nivel de detalle del log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

## Convención de nombres de archivo

El sistema detecta qué parser usar según el nombre del archivo PDF:

| Si el nombre contiene... | Parser que se usa |
|--------------------------|-------------------|
| `asiento` | `asiento_parser` |
| `borrador` o `borra` | `borrador_parser` |
| `f931` o `931` | `f931_parser` |

Si el nombre no coincide con ninguno de estos patrones, el sistema intenta detectar el tipo leyendo las primeras líneas del PDF. Si tampoco puede, lo saltea y lo registra en `resumen.json`.

**Ejemplo de nombres válidos:**
Asiento_SUMPETROL_052025.pdf   ✓
SUMP-BORRADOR_05-25.pdf        ✓
SUMP-F931_05-25.pdf            ✓

## Estructura del JSON de salida
Todos los parsers generan el mismo esqueleto, independientemente del tipo de documento:
json
{
  "metadata": {
    "source_file": "SUMP-F931_05-25.pdf",
    "tipo_documento": "f931",
    "periodo_detectado": "05/2025",
    "cuit": "33-60549172-9",
    "contribuyente": "SUMPETROL S. A.",
    "fecha_emision": "05 de junio de 2025",
    "parser_version": "1.0.0"
  },
  "extracted": {
    "campos_principales": {
      "cantidad_empleados": {
        "value": 28,
        "raw": "28",
        "label": "cantidad_empleados"
      }
    },
    "tablas": {
      "seccion_VIII_montos": {
        "cod_301": {
          "codigo": "301",
          "nombre": "Aportes de Seguridad Social",
          "value": 3122675.83,
          "raw": "3.122.675,83"
        }
      }
    },
    "conceptos_dinamicos": [
      {
        "label": "Embargo judicial",
        "value": 129855.80,
        "raw": "129.855,80",
        "raw_line": "a EMBARGO JUDICIAL $ 129.855,80",
        "categoria": "cuenta_haber"
      }
    ]
  },
  "raw": {
    "text_excerpt": ["primeras 30 líneas del PDF..."],
    "pages_detected": 2,
    "parser_version": "1.0.0"
  }
}
### Criterio para campos ausentes
- Si un concepto aparece en el PDF con valor `$ -` o vacío → `value: null`, `raw: "$ -"`.
- Si un concepto directamente no aparece en el PDF → el campo no se incluye en el JSON (así se puede distinguir "no aplica para este cliente" de "vale cero").
- Los importes siempre se guardan como `float` con punto decimal (sin importar el formato original argentino con coma).

## Cómo funciona internamente
### `utils/pdf_text.py`

Es la base del sistema. Tiene tres funciones clave:

**`extract_text()`** — Extrae el texto del PDF como lista de líneas. Usa `pdfplumber` por defecto y cae automáticamente a `pymupdf` si hay algún error.

**`extract_words_with_coords()`** — En vez de texto plano, devuelve cada palabra con sus coordenadas `(x0, y0, x1, y1)`. Esto lo usa el parser del asiento para separar las columnas DEBE y HABER sin depender de posiciones fijas de píxeles.

**`normalize_number()`** — Convierte números en formato argentino a `float` estándar:
"27.380.973,46"  →  27380973.46
"$ 642.515,41"   →  642515.41
"$ -"            →  None

### `asiento_parser.py`

El más complejo porque el asiento tiene dos columnas (DEBE/HABER) que `pdfplumber` puede entregar mezcladas.

**Estrategia:** busca las palabras "DEBE" y "HABER" en la página para calibrar dinámicamente los umbrales de columna. Luego asigna cada palabra a su columna según su posición X. Si no puede obtener coordenadas, cae a un fallback basado en heurística de líneas (las cuentas que empiezan con "a " son del HABER).

Extrae:
- `campos_principales`: totales de cada sección (Sueldos y Jornales, Leyes Sociales, ART, etc.)
- `tablas.debe_haber`: todas las filas de la tabla con su columna
- `conceptos_dinamicos`: todos los conceptos con su importe, incluyendo variables como embargos, sindicatos, fondos de cese, etc.

### `borrador_parser.py`
El borrador es un HTML renderizado como PDF. El texto es más lineal pero tiene dos columnas visuales que a veces se entremezclan.
Extrae mediante regex:
- Cabecera: CUIT, contribuyente, período, obra social, tipo de empleador
- Las 11 remuneraciones imponibles con su descripción
- Totales generales (Seg. Social, Obra Social, LRT, SCVO)
- Detalle de Contribuciones SS y Aportes SS
- Detalle de Obra Social (contribuciones y aportes)
- Retenciones del período

### `f931_parser.py`
El más estructurado porque AFIP define labels fijos. Tiene secciones numeradas del I al VIII.
La **sección VIII** (Montos que se ingresan) es la más importante para el papel de trabajo, porque contiene los códigos de pago definitivos:
| Código | Concepto |
|--------|----------|
| 301 | Aportes de Seguridad Social |
| 351 | Contribuciones de Seguridad Social |
| 302 | Aportes de Obra Social |
| 352 | Contribuciones de Obra Social |
| 312 | L.R.T. |
| 028 | Seguro Colectivo de Vida Obligatorio |
| 360 | Contribuciones RENATRE |
| 270 | Vales Alimentarios |
| 935 | Seg. Sepelio UATRE |

---

## Correr los tests

```bash
# Copiar los PDFs de prueba a pdfs_ejemplo/
mkdir pdfs_ejemplo
cp /ruta/a/los/pdfs/*.pdf pdfs_ejemplo/

# Ejecutar tests
python tests/test_parsers.py
```

El script imprime un resumen por parser y guarda los JSON generados en `outputs_test/`.

---

## Dependencias

| Librería | Versión mínima | Rol |
|----------|---------------|-----|
| `pdfplumber` | 0.11.0 | Extracción principal (coordenadas de palabras) |
| `pymupdf` | 1.24.0 | Fallback de extracción |

Todo lo demás (`re`, `json`, `logging`, `pathlib`, `argparse`) es librería estándar de Python.

> **Nota:** `pymupdf` se instala con ese nombre en pip pero se importa en el código como `fitz`.

---

## Limitaciones conocidas y próximos pasos

- Los parsers **no cruzan datos entre documentos**. Esa será la siguiente etapa (normalización y consolidación).
- Algunos campos del asiento (IERIC, UOCRA) pueden capturar el importe parcial en vez del total cuando ambos aparecen en la misma línea. Se corregirá en la próxima iteración.
- El campo `contribuyente` en el borrador puede incluir la fecha si está en la misma línea del PDF.
- No escribe a Excel todavía. Eso vendrá después de la etapa de consolidación.