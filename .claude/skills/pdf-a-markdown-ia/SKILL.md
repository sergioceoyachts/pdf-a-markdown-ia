---
name: pdf-a-markdown-ia
description: "Convierte cualquier PDF (digital, escaneado o mixto) en Markdown por páginas para trabajar con cualquier IA (Claude, ChatGPT, Gemini, Copilot, modelos locales) gastando el mínimo de tokens. Guarda imágenes, planos eléctricos, esquemas y tablas aparte en el formato más ligero (WebP sin pérdida para planos y con pérdida solo para fotos), con referencias cruzadas a su texto y posición. Hace OCR local y gratuito con Tesseract en páginas escaneadas y textos dentro de imágenes. También responde preguntas sobre documentos ya convertidos. Triggers: 'convierte este PDF', 'pasa el manual a markdown', 'PDF escaneado a md', 'prepara este folleto para ChatGPT/Gemini/Claude', 'extrae planos y tablas del PDF', 'haz OCR del PDF', 'manual de instalación a markdown', 'quiero usar este PDF con IA sin gastar tokens', 'procesa los PDF de input', 'convert this PDF to markdown', o cualquier pregunta sobre un documento ya convertido en output/."
---

# PDF a Markdown para cualquier IA

Convierte un PDF en un índice ligero y una página `.md` por cada página del PDF. Las figuras, los planos y las tablas se guardan aparte, en el formato más pequeño que no pierde detalle, y quedan enlazados al texto y a la posición donde estaban. Funciona en local y es gratis: no envía el PDF a ningún servicio.

**Regla fundamental: el texto nativo del PDF es intocable. No se reescribe, resume, traduce, corrige ni reordena. Lo que sale del OCR es una lectura de máquina, no texto original: siempre va marcado `⟨ocr N %⟩` y nunca se presenta como literal.**

Todos los comandos se ejecutan desde la **raíz del kit** (la carpeta que contiene `scripts/`, `input/` y `output/`).

---

## Paso 1. Localizar el PDF

1. Si el usuario da una ruta, usa esa.
2. Si no, busca `input/*.pdf`.
3. Si no hay PDFs, dile: *"Copia el PDF en la carpeta `input/` (o dime su ruta) y lo convierto."*
4. Si pide la salida en otra carpeta, usa `--out "<carpeta>"`. Se crea una subcarpeta con el nombre original del PDF.

Idiomas del OCR: por defecto `spa+eng`. Si el PDF está claramente en otro idioma, añádelo, por ejemplo `--idiomas spa+eng+fra`. Códigos frecuentes: `spa`, `eng`, `fra`, `deu`, `ita`, `por`, `cat`, `nld`.

---

## Paso 2. Convertir

Avisa: *"Convirtiendo… La primera vez instalo lo necesario (todo gratis)."* En un manual de cientos de páginas tarda unos minutos.

```bash
python scripts/pdf_to_md.py input/                                  # todos los PDF de input/
python scripts/pdf_to_md.py "input/manual.pdf" --idiomas spa+eng+fra
python scripts/pdf_to_md.py "input/manual.pdf" --out "D:/destino"
```

| Opción | Efecto |
|---|---|
| `--ocr auto` (por defecto) | OCR en páginas escaneadas, en texto dentro de imágenes y en tablas con texto dibujado |
| `--ocr todo` | Además, OCR de los dibujos vectoriales que ya tienen texto |
| `--ocr no` | Sin OCR (más rápido) |
| `--dpi 200` | Figuras más nítidas. Los planos vectoriales se generan siempre a un mínimo de 200 |
| `--completo` | Añade `documento-completo.md`. Solo si el usuario lo pide |
| `--motor libre` (por defecto) | pdfplumber (MIT) + pypdfium2 (Apache/BSD). Licencias permisivas, apto para uso comercial |
| `--motor pymupdf` | Motor alternativo con PyMuPDF (**AGPL-3.0**). Opcional, para comparar |

Comparar los dos motores: `python scripts/comparar_motores.py "<carpeta con PDFs>"` (necesita `pymupdf` y `psutil`).

### Dependencias (todas gratuitas, sin registro)
- **pdfplumber, pypdfium2 y Pillow:** el script las instala solo con pip la primera vez.
- **Tesseract OCR:** si hace falta y no está, en Windows el script intenta instalarlo con `winget` (Windows pedirá permiso de administrador). Si no se instala, la conversión **sigue igualmente** y avisa. Manual: Windows `winget install -e --id UB-Mannheim.TesseractOCR` · macOS `brew install tesseract` · Linux `sudo apt install tesseract-ocr`.
- **Idiomas del OCR:** se descargan solos del repositorio oficial `tesseract-ocr/tessdata_fast` a `tessdata/`.

**Nunca uses ni propongas servicios de pago o con registro:** OCR en la nube, APIs de IA ni conversores online.

Si falla:
- `python` no existe → repite con `py` y, si tampoco, con `python3`. En Windows, `scripts\ejecutar-python.cmd scripts/pdf_to_md.py input/` prueba los tres. Si no hay ninguno, explica cómo instalar Python desde python.org marcando «Add python.exe to PATH».
- «… se ha instalado, pero este Python no lo ve todavía» → ejecuta el mismo comando otra vez.
- PDF con contraseña → pide una copia sin protección.

---

## Paso 3. Verificar (obligatorio)

1. Lee `output/<doc>/_validacion.md`.
2. **La cobertura debe ser 100 % con 0 referencias rotas.** La cobertura se mide contra lo que de verdad queda escrito en `pages/` y `tables/`. Las cabeceras, los pies y los números de página se omiten a propósito y no cuentan, así que **cualquier palabra listada en «Palabras no localizadas» falta de verdad**. Para cada página listada, ábrela en el PDF y copia literalmente lo que falte en su sitio de `pages/pNNN.md` (o de `tables/…md` si es una celda). No cambies nada más. Después díselo al usuario: qué páginas y qué faltaba.
3. **Palabras duplicadas: debe ser 0.** Si hay alguna, abre la página: suele ser texto que sale a la vez como párrafo y dentro de una tabla. Deja cada texto una sola vez, en el sitio que ocupa en el PDF.
   **Palabras contiguas que se separan:** compara la tabla con el PDF. Si el script ha separado algo que va junto (un valor de su unidad, un código de su significado), júntalo en la celda correcta. Si es una columna real de la tabla, está bien así. Crítico en esquemas eléctricos y tablas técnicas.
4. **Símbolos gráficos (si `INDICE.md` tiene la sección «Símbolos gráficos»).** `⟦x⟧` es un glifo de una fuente de pictogramas, no la letra x. Abre cada imagen `images/glifo-*` y sustituye «(sin describir)» en la tabla del INDICE por lo que se ve: el carácter equivalente y su nombre (`≥ mayor o igual`, `● punto relleno`). Pon lo mismo en `"meaning"` de `symbols` en `manifest.json`. No toques el texto de las páginas. Si no se distingue, escribe «(no se distingue)».
5. **Sección OCR:** por debajo de 80 % de confianza, avisa de que esa página tiene lecturas poco fiables y muestra las «lecturas dudosas».
6. **Avisos «tabla con texto en trazos vectoriales»:** las celdas completadas por OCR van marcadas `⟨ocr⟩`. Si quedan celdas vacías o dudosas, ofrece revisarlas leyendo la imagen de la tabla y marca lo corregido `⟨img⟩valor`.
7. **«OCR no disponible»:** explica qué páginas quedaron solo como imagen y da el comando de instalación.
8. Por muestreo, abre una figura de plano y comprueba que el recorte incluye el plano entero y sus cotas.

---

## Paso 4. Describir figuras (opcional, recomendado en planos y montajes)

Pregunta: *"¿Quieres que describa las figuras? Lo hago una vez y después ninguna IA necesitará abrir las imágenes, lo que ahorra muchos tokens."*

Si acepta, para cada figura (`manifest.json` → `items` de tipo `figure` sin `"repeated": true`):
1. Ábrela.
2. Escribe 1 o 2 líneas factuales. En planos eléctricos: bornes, colores de cable, conexiones y símbolos visibles. Ejemplo: *"Regleta D de 3 polos: L (marrón) a borne 1, N (azul) a borne 2, PE (verde-amarillo) a borne 3; alimentación 230 V~ 50 Hz."*
3. Añade ` · desc: …` a la línea en cursiva bajo la imagen en `pages/pNNN.md`, y lo mismo en `"description"` del manifest.
4. Solo lo visible. Si algo es ambiguo, «(no se distingue)». Nunca deduzcas conexiones, medidas o pasos que no estén dibujados o escritos.

---

## Paso 5. Presentar el resultado

- Ruta de salida, número de páginas, figuras y tablas, y tamaño total de las imágenes.
- Tokens estimados en total y de la página más pesada.
- Cobertura, resumen del OCR (páginas, confianza media) y avisos.
- Cómo usarlo con cada IA: ver `LEEME-IA.md`.

Ofrece: describir figuras, más resolución, otro idioma de OCR o convertir otro PDF.

---

## Modo consulta (documento ya convertido)

1. Lee **solo** `output/<doc>/INDICE.md`. Su *Contenido* da el rango de páginas de cada capítulo (`→ p71–79`).
2. Si el capítulo deja clara la zona, lee únicamente esas `pages/pNNN.md`.
3. Si no, busca con grep en `output/<doc>/pages/`:
   - **Ordena primero las páginas con coincidencias en texto nativo y después las que solo coinciden en líneas `⟨ocr`** (lecturas de capturas, placas, fotos, tablas dibujadas). No las descartes: a veces la respuesta solo está ahí.
   - Con muchas coincidencias, acota con términos más específicos.
4. `paginas.md` (una línea por página) solo si el índice y la búsqueda no bastan.
5. Abre una imagen solo si la respuesta depende de ella y no tiene `desc`.
6. Cita la página y el id: *"Esquema de conexión (p2, figura p002-f1)"*. Si la página empieza con *Cabecera/pie: …*, esa línea indica a qué sección pertenece.
7. Si la respuesta se apoya en texto `⟨ocr⟩`, dilo y da la confianza.
8. `⟦x⟧` es un símbolo gráfico, no una letra: tradúcelo con la tabla «Símbolos gráficos» del INDICE (`cos ϕ ⟦u⟧ 0,8` → `cos ϕ ≥ 0,8`).
9. Evita `manifest.json` y `documento-completo.md`: son lo más caro.
10. Si algo no está en el documento, dilo. No inventes, y menos en esquemas eléctricos, medidas o avisos de seguridad.
