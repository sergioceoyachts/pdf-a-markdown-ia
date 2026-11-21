# Agente: PDF a Markdown para IA

> Instrucciones comunes para cualquier agente de IA: OpenAI Codex, GitHub Copilot, Cursor, Windsurf, Gemini CLI, Aider, Claude Code…
> La guía completa paso a paso está en [`.claude/skills/pdf-a-markdown-ia/SKILL.md`](.claude/skills/pdf-a-markdown-ia/SKILL.md). Léela antes de convertir.

Este proyecto convierte PDFs (digitales, escaneados o mixtos) en Markdown por páginas, con imágenes, planos y tablas aparte y referencias cruzadas, para trabajar con IA gastando el mínimo de tokens. Todo es local y gratuito.

## Convertir

```bash
python scripts/pdf_to_md.py input/                      # todos los PDF de input/
python scripts/pdf_to_md.py "input/x.pdf" --idiomas spa+eng --ocr auto --out output
```

- Si `python` no existe, usa `py` o `python3` (en Windows, `scripts\ejecutar-python.cmd` prueba los tres).
- Dependencias gratuitas: pdfplumber, pypdfium2 y Pillow (se instalan solas) y Tesseract para el OCR. Sin Tesseract, la conversión sigue y avisa.
- No uses servicios de pago, con registro ni en la nube.
- Después de convertir, lee `output/<doc>/_validacion.md`. La cobertura debe ser **100 %** con 0 referencias rotas. Cada palabra de «Palabras no localizadas» falta de verdad en la salida: cópiala literalmente del PDF en su página o tabla y avisa al usuario.

## Consultar un documento convertido

1. Lee **solo** `output/<doc>/INDICE.md`. Su *Contenido* da el rango de páginas de cada capítulo (`→ p71–79`).
2. Lee únicamente los `pages/pNNN.md` necesarios. Para buscar, usa grep sobre `pages/` y ordena primero las páginas con coincidencias en texto nativo y después las que solo coinciden en líneas `⟨ocr` (no las descartes). `paginas.md` solo si lo anterior no basta.
3. El texto es literal del PDF: no lo reescribas. `⟨ocr N %⟩` significa que se leyó por OCR y puede tener errores. `⟦x⟧` es un símbolo gráfico (●, ≥, ✓…), no la letra x: su significado está en la tabla «Símbolos gráficos» del INDICE.
4. Abre imágenes (`images/*.webp`) solo si la respuesta depende de ellas.
5. Cita la página y el id (`p004-f2`, `p005-t1`). No inventes nada que no esté, sobre todo en esquemas eléctricos y advertencias de seguridad.
