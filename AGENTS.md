# Agent: PDF to Markdown for AI

> Shared instructions for any AI agent: OpenAI Codex, GitHub Copilot, Cursor, Windsurf, Gemini CLI, Aider, Claude Code…
> The full step-by-step guide is in [`.claude/skills/pdf-a-markdown-ia/SKILL.md`](.claude/skills/pdf-a-markdown-ia/SKILL.md). Read it before converting.

This project converts PDFs (digital, scanned or mixed) into page-split Markdown, with images, diagrams and tables saved apart and cross-referenced, so you can work with AI using as few tokens as possible. Everything is local and free.

Always reply in the user's language. Output files and some labels are in Spanish (`INDICE.md` = index, `paginas.md` = pages).

## Convert

```bash
python scripts/pdf_to_md.py input/                      # every PDF in input/
python scripts/pdf_to_md.py "input/x.pdf" --idiomas eng+spa --ocr auto --out output
```

- If `python` does not exist, use `py` or `python3` (on Windows, `scripts\ejecutar-python.cmd` tries all three).
- Free dependencies: pdfplumber, pypdfium2 and Pillow (installed automatically) and Tesseract for OCR. Without Tesseract the conversion still runs and warns.
- Do not use paid, sign-up or cloud services.
- After converting, read `output/<doc>/_validacion.md`. Coverage must be **100 %** with 0 broken references. Every word under «Palabras no localizadas» (words not found) is really missing from the output: copy it verbatim from the PDF into its page or table and tell the user.

## Query a converted document

1. Read **only** `output/<doc>/INDICE.md`. Its *Contenido* (contents) gives each chapter's page range (`→ p71–79`).
2. Read only the `pages/pNNN.md` you need. To search, grep `pages/` and rank pages with matches in native text first, then pages that only match in `⟨ocr` lines (do not discard them). Use `paginas.md` only if that is not enough.
3. The text is verbatim from the PDF: do not rewrite it. `⟨ocr N %⟩` means it was read by OCR and may contain errors. `⟦x⟧` is a graphic symbol (●, ≥, ✓…), not the letter x: its meaning is in the «Símbolos gráficos» (graphic symbols) table in INDICE.md.
4. Open images (`images/*.webp`) only if the answer depends on them.
5. Cite the page and id (`p004-f2`, `p005-t1`). Never invent anything that is not there, especially in wiring diagrams and safety warnings.
