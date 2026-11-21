# Contexto para Gemini CLI

Las instrucciones de este proyecto son las mismas para todas las IAs y están en `AGENTS.md`. La guía completa paso a paso está en `.claude/skills/pdf-a-markdown-ia/SKILL.md`. Síguelas.

Resumen:
- Convertir: `python scripts/pdf_to_md.py input/` (todo local y gratis; OCR con Tesseract, idiomas `spa+eng` por defecto).
- Verificar: `output/<doc>/_validacion.md` → cobertura 100 % y 0 referencias rotas.
- Consultar: empieza por `output/<doc>/INDICE.md` y lee solo las páginas necesarias. Al buscar, primero coincidencias en texto nativo y después en líneas `⟨ocr⟩`.
- El texto es literal del PDF y `⟨ocr⟩` indica que se leyó por OCR. Cita la página y el id, y no inventes.
