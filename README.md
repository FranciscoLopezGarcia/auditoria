# Px Laboral – Automatización de Papeles de Trabajo F931

Herramienta interna diseñada para contadores y auditores que automatiza la extracción, normalización y consolidación de información laboral a partir de los tres documentos mensuales clave:

- F931  
- Borrador  
- Asiento  

El sistema genera un archivo Excel consolidado listo para revisión contable, reduciendo trabajo manual y mejorando la consistencia de los papeles de trabajo.

---

## Objetivo del Proyecto

Automatizar el armado del papel de trabajo mensual vinculado a cargas sociales y sueldos, permitiendo:

- Reducir errores de carga manual  
- Estandarizar el análisis  
- Agilizar el proceso de revisión  
- Mejorar la trazabilidad  

---

## Público Objetivo

- Contadores  
- Auditores  
- Estudios contables  
- Usuarios con conocimientos básicos de informática  

No requiere conocimientos técnicos avanzados.

---

## Arquitectura Simplificada

El sistema está compuesto por:

### Backend (Python + FastAPI)

- Orquesta el procesamiento  
- Ejecuta el pipeline modular  
- Genera el archivo Excel final  

### Pipeline Modular

- Parsers (lectura de PDFs)  
- Normalizador (estandarización de conceptos)  
- Consolidación de fuentes  
- Generación de Excel  

### Frontend Simple (HTML + JavaScript)

- Permite cargar archivos desde el navegador  
- Ejecuta el procesamiento  
- Descarga el Excel consolidado  

### Ejecución Local

Todo el procesamiento ocurre en la computadora del usuario.  
No se envía información a servidores externos.

---

## Requisitos del Sistema

- Python 3.10 o superior  
- Sistema operativo Windows, Linux o macOS  
- Navegador moderno  
- Dependencias indicadas en `requirements.txt`  

---

## Instalación

### 1. Crear entorno virtual (recomendado)

```bash
python -m venv venv
````

Activar entorno:

**Windows**

```bash
venv\Scripts\activate
```

**Linux / macOS**

```bash
source venv/bin/activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

---

## Cómo Ejecutar el Backend

Desde la raíz del proyecto:

```bash
uvicorn app:app --reload
```

El servidor se iniciará en:

```
http://127.0.0.1:8000
```

Puede verificarse su funcionamiento ingresando a:

```
http://127.0.0.1:8000/docs
```

---

## Cómo Usar el Frontend

1. Abrir el archivo `frontend/index.html` en el navegador.
2. Cargar los tres PDFs correspondientes al período:

   * F931
   * Borrador
   * Asiento
3. Presionar **Procesar Archivos**.
4. Descargar el Excel generado automáticamente.

---

## Flujo Típico de Uso

1. Reunir los tres PDFs mensuales del cliente.
2. Levantar el backend.
3. Abrir el frontend.
4. Subir los documentos.
5. Descargar el Excel consolidado.
6. Revisar y archivar como papel de trabajo.

---

## Estructura General del Proyecto

```
backend/
  core/        Lógica de negocio (parsers, normalizer, excel, pipeline)
  cli/         Scripts de ejecución por línea de comandos
  tools/       Utilidades auxiliares
  output/      Archivos generados
  tests/       Pruebas internas

frontend/      Interfaz web simple
requirements.txt
app.py
```

---

## Limitaciones Actuales

* Diseñado para ejecución local.
* Requiere los tres PDFs del mismo período.
* No almacena historial de ejecuciones.
* No incluye gestión multiusuario.

---

## Privacidad y Seguridad

* Ejecución 100% local.
* No se transmiten datos a servidores externos.
* No se almacenan datos fuera del equipo del usuario.

---

## Buenas Prácticas

* Verificar que los tres PDFs correspondan al mismo período.
* Conservar el Excel generado junto con los documentos originales.
* No modificar manualmente el archivo Excel antes de la revisión final.

---

## Soporte

Ante dudas o mejoras, contactar al responsable interno del área de sistemas o automatización.
