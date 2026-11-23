---
name: pdf-a-markdown-ia
description: "Converts any PDF (digital, scanned or mixed) into page-split Markdown to work with any AI (Claude, ChatGPT, Gemini, Copilot, local models) using as few tokens as possible. Saves images, wiring diagrams, schematics and tables apart in the lightest format (lossless WebP for diagrams, lossy only for photos), cross-referenced to their text and position. Runs free local OCR with Tesseract on scanned pages and text inside images. Also answers questions about already converted documents. Triggers: 'convert this PDF to markdown', 'scanned PDF to md', 'prepare this leaflet for ChatGPT/Gemini/Claude', 'extract diagrams and tables from the PDF', 'OCR this PDF', 'installation manual to markdown', 'use this PDF with AI without wasting tokens', 'process the PDFs in input', 'convierte este PDF', 'pasa el manual a markdown', or any question about a document already converted in output/."
---

# PDF to Markdown for any AI

Converts a PDF into a lightweight index and one `.md` file per PDF page. Figures, diagrams and tables are saved apart, in the smallest format that keeps detail, and stay linked to the text and position where they were. Works locally and for free: the PDF is never sent to any service.

Always reply in the user's language. Output files and labels are in Spanish; their meaning is given in brackets below.

**Golden rule: the PDF's native text is untouchable. It is never rewritten, summarised, translated, corrected or reordered. OCR output is a machine reading, not original text: it is always tagged `⟨ocr N %⟩` and never presented as verbatim.**

All commands run from the **kit root** (the folder containing `scripts/`, `input/` and `output/`).

---

## Step 1. Find the PDF

1. If the user gives a path, use it.
2. Otherwise, look for `input/*.pdf`.
3. If there are no PDFs, say: *"Copy the PDF into the `input/` folder (or tell me its path) and I'll convert it."*
4. If they want the output elsewhere, use `--out "<folder>"`. A subfolder named after the original PDF is created.

OCR languages: `spa+eng` by default. If the PDF is clearly in another language, add it, e.g. `--idiomas spa+eng+fra`. Common codes: `spa`, `eng`, `fra`, `deu`, `ita`, `por`, `cat`, `nld`.

---

## Step 2. Convert

Tell the user: *"Converting… The first time I install what's needed (all free)."* A manual with hundreds of pages takes a few minutes.

```bash
python scripts/pdf_to_md.py input/                                  # every PDF in input/
python scripts/pdf_to_md.py "input/manual.pdf" --idiomas spa+eng+fra
python scripts/pdf_to_md.py "input/manual.pdf" --out "D:/destination"
```

| Option | Effect |
|---|---|
| `--ocr auto` (default) | OCR on scanned pages, text inside images and tables with drawn text |
| `--ocr todo` | Also OCR on vector drawings that already contain text |
| `--ocr no` | No OCR (faster) |
| `--dpi 200` | Sharper figures. Vector diagrams are always rendered at 200 minimum |
| `--completo` | Adds `documento-completo.md` (full document). Only if the user asks |
| `--motor libre` (default) | pdfplumber (MIT) + pypdfium2 (Apache/BSD). Permissive licences, fine for commercial use |
| `--motor pymupdf` | Alternative engine with PyMuPDF (**AGPL-3.0**). Optional, for comparison |

Compare both engines: `python scripts/comparar_motores.py "<folder with PDFs>"` (needs `pymupdf` and `psutil`).

### Dependencies (all free, no sign-up)
- **pdfplumber, pypdfium2 and Pillow:** the script installs them with pip on first run.
- **Tesseract OCR:** if needed and missing, on Windows the script tries to install it with `winget` (Windows will ask for admin permission). If it cannot, the conversion **still runs** and warns. Manual: Windows `winget install -e --id UB-Mannheim.TesseractOCR` · macOS `brew install tesseract` · Linux `sudo apt install tesseract-ocr`.
- **OCR languages:** downloaded automatically from the official `tesseract-ocr/tessdata_fast` repository into `tessdata/`.

**Never use or suggest paid or sign-up services:** cloud OCR, AI APIs or online converters.

If it fails:
- `python` does not exist → retry with `py`, then `python3`. On Windows, `scripts\ejecutar-python.cmd scripts/pdf_to_md.py input/` tries all three. If none exists, explain how to install Python from python.org ticking «Add python.exe to PATH».
- «… se ha instalado, pero este Python no lo ve todavía» (installed, but this Python can't see it yet) → run the same command again.
- Password-protected PDF → ask for an unprotected copy.

---

## Step 3. Validate (mandatory)

1. Read `output/<doc>/_validacion.md`.
2. **Coverage must be 100 % with 0 broken references.** Coverage is measured against what is actually written in `pages/` and `tables/`. Headers, footers and page numbers are left out on purpose and do not count, so **any word listed under «Palabras no localizadas» (words not found) is really missing**. For each listed page, open it in the PDF and copy what is missing verbatim into its place in `pages/pNNN.md` (or `tables/…md` if it is a cell). Change nothing else. Then tell the user which pages and what was missing.
3. **Duplicated words: must be 0.** If there are any, open the page: it is usually text that appears both as a paragraph and inside a table. Keep each text once, where it sits in the PDF.
   **Adjacent words split apart:** compare the table with the PDF. If the script split something that belongs together (a value and its unit, a code and its meaning), join it in the right cell. If it is a real table column, leave it. Critical in wiring diagrams and technical tables.
4. **Graphic symbols (if `INDICE.md` has a «Símbolos gráficos» section).** `⟦x⟧` is a glyph from a pictogram font, not the letter x. Open each `images/glifo-*` image and replace «(sin describir)» (not described) in the INDICE table with what you see: the equivalent character and its name (`≥ greater than or equal`, `● filled dot`). Put the same in `"meaning"` under `symbols` in `manifest.json`. Do not touch the page text. If it cannot be made out, write «(no se distingue)» (cannot be made out).
5. **OCR section:** below 80 % confidence, warn that the page has unreliable readings and show the «lecturas dudosas» (doubtful readings).
6. **«tabla con texto en trazos vectoriales» warnings** (table with text drawn as vector strokes): cells filled by OCR are tagged `⟨ocr⟩`. If cells remain empty or doubtful, offer to review them by reading the table image and tag corrections `⟨img⟩value`.
7. **«OCR no disponible»** (OCR not available): explain which pages stayed as images only and give the install command.
8. Spot-check: open a diagram figure and check the crop includes the whole diagram and its dimensions.

---

## Step 4. Describe figures (optional, recommended for diagrams and assembly drawings)

Ask: *"Do you want me to describe the figures? I do it once, and afterwards no AI needs to open the images, which saves a lot of tokens."*

If they accept, for each figure (`manifest.json` → `items` of type `figure` without `"repeated": true`):
1. Open it.
2. Write 1 or 2 factual lines. In wiring diagrams: terminals, wire colours, connections and visible symbols. Example: *"3-pole terminal block D: L (brown) to terminal 1, N (blue) to terminal 2, PE (green-yellow) to terminal 3; supply 230 V~ 50 Hz."*
3. Append ` · desc: …` to the italic line under the image in `pages/pNNN.md`, and the same in the manifest's `"description"`.
4. Only what is visible. If something is ambiguous, «(no se distingue)». Never infer connections, measurements or steps that are not drawn or written.

---

## Step 5. Present the result

- Output path, number of pages, figures and tables, and total image size.
- Estimated total tokens and the heaviest page.
- Coverage, OCR summary (pages, average confidence) and warnings.
- How to use it with each AI: see `LEEME-IA.md`.

Offer: describe figures, higher resolution, another OCR language or convert another PDF.

---

## Query mode (already converted document)

1. Read **only** `output/<doc>/INDICE.md`. Its *Contenido* (contents) gives each chapter's page range (`→ p71–79`).
2. If the chapter makes the area clear, read only those `pages/pNNN.md`.
3. Otherwise, grep `output/<doc>/pages/`:
   - **Rank pages with matches in native text first, then pages that only match in `⟨ocr` lines** (readings from screenshots, rating plates, photos, drawn tables). Do not discard them: sometimes the answer is only there.
   - With many matches, narrow down with more specific terms.
4. `paginas.md` (one line per page) only if the index and search are not enough.
5. Open an image only if the answer depends on it and it has no `desc`.
6. Cite the page and id: *"Connection diagram (p2, figure p002-f1)"*. If the page starts with *Cabecera/pie: …* (header/footer), that line tells which section it belongs to.
7. If the answer relies on `⟨ocr⟩` text, say so and give the confidence.
8. `⟦x⟧` is a graphic symbol, not a letter: translate it with the «Símbolos gráficos» table in INDICE.md (`cos ϕ ⟦u⟧ 0,8` → `cos ϕ ≥ 0,8`).
9. Avoid `manifest.json` and `documento-completo.md`: they are the most expensive.
10. If something is not in the document, say so. Never invent, especially in wiring diagrams, measurements or safety warnings.
