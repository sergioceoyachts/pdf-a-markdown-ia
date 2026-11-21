# Instrucciones para GitHub Copilot

Sigue `AGENTS.md` (instrucciones comunes) y la guía completa `.claude/skills/pdf-a-markdown-ia/SKILL.md`.

- Convertir: `python scripts/pdf_to_md.py input/`
- Verificar: `output/<doc>/_validacion.md` → cobertura 100 %.
- Consultar: entra por `output/<doc>/INDICE.md` y abre solo las `pages/pNNN.md` necesarias.
- El texto es literal del PDF; `⟨ocr⟩` = leído por OCR; `⟦x⟧` = símbolo gráfico, no letra. Cita página e id. No inventes.
