# Instructions for GitHub Copilot

Follow `AGENTS.md` (shared instructions) and the full guide `.claude/skills/pdf-a-markdown-ia/SKILL.md`. Reply in the user's language.

- Convert: `python scripts/pdf_to_md.py input/`
- Check: `output/<doc>/_validacion.md` → 100 % coverage.
- Query: start from `output/<doc>/INDICE.md` and open only the `pages/pNNN.md` you need.
- The text is verbatim from the PDF; `⟨ocr⟩` = read by OCR; `⟦x⟧` = graphic symbol, not a letter. Cite page and id. Never invent.
