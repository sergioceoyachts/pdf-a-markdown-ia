# Context for Gemini CLI

This project's instructions are the same for every AI and live in `AGENTS.md`. The full step-by-step guide is in `.claude/skills/pdf-a-markdown-ia/SKILL.md`. Follow them, and reply in the user's language.

Summary:
- Convert: `python scripts/pdf_to_md.py input/` (all local and free; OCR with Tesseract, `spa+eng` languages by default).
- Check: `output/<doc>/_validacion.md` → 100 % coverage and 0 broken references.
- Query: start from `output/<doc>/INDICE.md` and read only the pages you need. When searching, native-text matches first, then `⟨ocr⟩` lines.
- The text is verbatim from the PDF and `⟨ocr⟩` means it was read by OCR. Cite the page and id, and never invent.
