# PDF a Markdown para cualquier IA

Este kit convierte cualquier PDF (digital, escaneado o mixto: manuales, folletos de montaje e instalación, fichas con planos eléctricos) en Markdown troceado por páginas. Imágenes, planos y tablas se guardan aparte en el formato más ligero y con referencias cruzadas. Todo es local y gratuito.

## Comportamiento al iniciar

Cuando el usuario escriba cualquier cosa y no haya pedido nada concreto, responde:

> **PDF → Markdown para cualquier IA**
>
> Convierto tus PDF (también los escaneados) en archivos `.md` ligeros. El texto original queda intacto, y las imágenes, planos y tablas se guardan aparte, enlazados a su texto y posición. El resultado lo puedes usar con Claude, ChatGPT, Gemini…
>
> **Copia tu PDF en la carpeta `input/` y dime "convierte".** Si está en un idioma distinto de español o inglés, dímelo para el OCR.
>
> Si ya lo convertiste, pregúntame directamente lo que necesites del documento.

Después usa la skill `pdf-a-markdown-ia` (`.claude/skills/pdf-a-markdown-ia/SKILL.md`).

## Reglas al trabajar con documentos convertidos (ahorro de tokens)

- Entrada siempre por `output/<doc>/INDICE.md`. Nunca leas todas las páginas «por si acaso».
- Lee solo los `pages/pNNN.md` necesarios. Al buscar con Grep, ordena primero las coincidencias en texto nativo y después las de líneas `⟨ocr` (no las descartes).
- `paginas.md` solo si el índice y la búsqueda no bastan.
- Abre imágenes solo si la respuesta depende de ellas y la figura no tiene `desc`.
- Cita siempre la página y el id (`p004-f2`, `p005-t1`).
- El texto es literal del PDF: no lo reescribas. `⟨ocr N %⟩` = leído por OCR: avisa cuando te apoyes en ello.
- `⟦x⟧` es un símbolo gráfico (●, ≥, ✓…), no la letra x. Tradúcelo con la tabla «Símbolos gráficos» del INDICE.
- Nunca propongas servicios de pago, con registro o en la nube.

## Qué necesita (todo gratis)

- Python 3.9 o superior. pdfplumber, pypdfium2 y Pillow se instalan solos.
- Tesseract OCR solo para escaneados o texto dentro de imágenes. En Windows se intenta instalar con `winget`. Sin él, todo lo demás funciona igual.
