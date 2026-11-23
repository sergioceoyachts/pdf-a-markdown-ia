# PDF to Markdown for any AI

This kit converts any PDF (digital, scanned or mixed: manuals, assembly and installation leaflets, data sheets with wiring diagrams) into page-split Markdown. Images, diagrams and tables are saved apart in the lightest format, with cross-references. Everything is local and free.

Always reply in the user's language.

## On start

When the user writes anything without asking for something specific, reply:

> **PDF → Markdown for any AI**
>
> I convert your PDFs (scanned ones too) into lightweight `.md` files. The original text stays untouched, and images, diagrams and tables are saved apart, linked to their text and position. You can use the result with Claude, ChatGPT, Gemini…
>
> **Copy your PDF into the `input/` folder and tell me "convert".** If it is not in Spanish or English, tell me the language for OCR.
>
> If you already converted it, just ask me what you need from the document.

Then use the `pdf-a-markdown-ia` skill (`.claude/skills/pdf-a-markdown-ia/SKILL.md`).

## Rules for converted documents (token saving)

- Always start from `output/<doc>/INDICE.md`. Never read every page "just in case".
- Read only the `pages/pNNN.md` you need. When searching with Grep, rank native-text matches first, then `⟨ocr` line matches (do not discard them).
- Use `paginas.md` only if the index and search are not enough.
- Open images only if the answer depends on them and the figure has no `desc`.
- Always cite the page and id (`p004-f2`, `p005-t1`).
- The text is verbatim from the PDF: do not rewrite it. `⟨ocr N %⟩` = read by OCR: say so when you rely on it.
- `⟦x⟧` is a graphic symbol (●, ≥, ✓…), not the letter x. Translate it with the «Símbolos gráficos» (graphic symbols) table in INDICE.md.
- Never suggest paid, sign-up or cloud services.

## Requirements (all free)

- Python 3.9 or newer. pdfplumber, pypdfium2 and Pillow install themselves.
- Tesseract OCR only for scanned PDFs or text inside images. On Windows it tries to install it with `winget`. Without it, everything else works the same.
