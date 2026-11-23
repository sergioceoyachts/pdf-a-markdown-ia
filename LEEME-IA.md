# Instructions for the AI: PDF document converted to Markdown

> Works with **any AI**: ChatGPT, Gemini, Claude, Copilot, Mistral, local models…
> In web chat AIs, upload this file together with the document's `INDICE.md`, or paste the block below as your first message.
> (File name in Spanish: *LEEME-IA* = "AI read-me".)

```text
You will work with a PDF document converted to Markdown to save tokens.
Reply in my language.
Document folder structure (file names are in Spanish):
- INDICE.md: index of chapters with their page ranges (e.g. "→ p71–79"). ALWAYS START HERE.
- paginas.md: one line per page (tokens, figures, tables, topic). Only if the index is not enough.
- pages/pNNN.md: VERBATIM text of each page, with tables and figures in place.
- images/: figures and diagrams (WebP). Id: p004-f2 = figure 2 on page 4.
- tables/: each table as .md and .csv. Id: p005-t1 = table 1 on page 5.
- refs.md: id of each figure or table with its page, position, section and nearby text.

Rules:
1. Use INDICE.md to locate the information and ask me ONLY for the pages you need (for example "upload p012.md and p013.md"). If a searched word appears mostly in ⟨ocr⟩ lines (text read from screenshots or photos), prioritise pages where it appears in normal text, but do not discard the others: sometimes the answer is only in an image.
2. The text is verbatim from the original document: quote it as is, do not rewrite or complete it.
3. Anything tagged ⟨ocr N %⟩ or ⟨ocr⟩ was read by OCR and may contain errors; say so when you rely on it. Anything tagged ⟦x⟧ is a graphic symbol (●, ≥, ✓…), not the letter x: translate it with the «Símbolos gráficos» (graphic symbols) table in INDICE.md.
4. Under each figure there is a line with its id, position and labels (dimensions, terminals, part letters). Ask for the image only if you really need to see it.
5. Always cite the page and id: "(p2, figure p002-f1)".
6. If something is not in the document, say so. Never invent it, especially in wiring diagrams, measurements or safety steps.
```

## How to use it with each AI

| AI | How |
|---|---|
| **Claude Code** (VS Code / terminal) | Open the kit folder and ask. It reads `CLAUDE.md` and the skill automatically |
| **OpenAI Codex CLI** | Open the folder and ask. It reads `AGENTS.md` automatically |
| **Gemini CLI** | Open the folder and ask. It reads `GEMINI.md` automatically |
| **Cursor, Windsurf, Aider, Zed** | Open the folder and ask. They read `AGENTS.md` |
| **GitHub Copilot** (VS Code) | Open the folder and ask. It reads `.github/copilot-instructions.md` |
| **ChatGPT / Gemini / Claude web** | 1) Paste the block above. 2) Upload `INDICE.md`. 3) Upload only the pages it asks for |
| **ChatGPT Projects, Gemini Gems, Claude Projects** | Upload the `pages/` folder and `INDICE.md` as knowledge and set the block above as instructions |
