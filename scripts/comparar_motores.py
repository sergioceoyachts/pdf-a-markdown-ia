"""comparar_motores.py - Compara el motor PyMuPDF (AGPL) con el libre (pdfplumber + pypdfium2):
tiempo, memoria pico y calidad. Referencia independiente del texto del PDF: PDFium.

Uso:  python comparar_motores.py <carpeta_con_pdfs> [prefijos...]
Salida: <carpeta>/../comparativa/ (out_pymupdf, out_libre, resultados.json)"""
import json, re, subprocess, sys, time, threading
from collections import Counter
from pathlib import Path
import psutil
import pypdfium2 as pdfium

SRC = Path(sys.argv[1])
HERE = SRC.parent / "comparativa"
HERE.mkdir(exist_ok=True)
SCRIPT = Path(__file__).resolve().parent / "pdf_to_md.py"
pdfs = sorted(SRC.glob("*.pdf"))
only = sys.argv[2:]  # filtros opcionales por prefijo
if only:
    pdfs = [p for p in pdfs if any(p.name.startswith(o) for o in only)]

def norm_tokens(text):
    out = []
    for t in re.split(r"\s+", text):
        t = t.strip(".,;:()[]{}\"'«»*|`!?¡¿").lower().replace("\xad", "")
        if t and re.search(r"\w", t):
            out.append(t)
    return out

def ref_words(pdf):
    d = pdfium.PdfDocument(str(pdf))
    c = Counter()
    for p in d:
        tp = p.get_textpage()
        c.update(norm_tokens(tp.get_text_range()))
    return c

def out_words(folder):
    txt = []
    for f in list((folder / "pages").glob("*.md")) + list((folder / "tables").glob("*.md")):
        s = f.read_text(encoding="utf-8")
        s = re.sub(r"<!--.*?-->", " ", s)
        s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)
        s = re.sub(r"⟨ocr[^⟩]*⟩", " ", s).replace("⟦", "").replace("⟧", "")
        s = s.replace("\\", "")
        txt.append(s)
    return Counter(norm_tokens("\n".join(txt)))

def run(pdf, motor, outdir):
    cmd = [sys.executable, "-W", "ignore", str(SCRIPT), str(pdf), "--out", str(outdir), "--motor", motor]
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    peak = 0
    ps = psutil.Process(p.pid)
    def watch():
        nonlocal peak
        while p.poll() is None:
            try:
                peak = max(peak, ps.memory_info().rss)
            except Exception:
                pass
            time.sleep(0.2)
    th = threading.Thread(target=watch); th.start()
    out, _ = p.communicate(); th.join()
    dt = time.perf_counter() - t0
    return dt, peak / 2**20, p.returncode, out.decode("utf-8", "replace")

def val(folder):
    v = (folder / "_validacion.md").read_text(encoding="utf-8")
    g = lambda pat: (re.search(pat, v) or [None, "?"])[1]
    m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    figs = sum(1 for i in m["items"] if i["type"] == "figure" and not i.get("repeated"))
    tabs = sum(1 for i in m["items"] if i["type"] == "table")
    imgbytes = sum((folder / "images" / f.name).stat().st_size for f in (folder / "images").glob("*"))
    tokens = sum(len(f.read_text(encoding="utf-8")) for f in (folder / "pages").glob("*.md")) / 3.6
    return {"cob_propia": g(r"Cobertura de palabras: \*\*([\d.]+) %"), "dup": g(r"duplicadas: \*\*(\d+)"),
            "pares_sep": g(r"se separan: \*\*(\d+)"), "rotas": g(r"rotas: \*\*(\d+)"),
            "figs": figs, "tabs": tabs, "img_mb": round(imgbytes / 2**20, 2), "tokens": round(tokens)}

res = []
for pdf in pdfs:
    ref = ref_words(pdf)
    total = sum(ref.values())
    row = {"pdf": pdf.name, "pags": len(pdfium.PdfDocument(str(pdf))), "ref_palabras": total}
    outs = {}
    for motor in ("pymupdf", "libre"):
        od = HERE / f"out_{motor}"
        dt, mb, rc, log = run(pdf, motor, od)
        folder = od / pdf.stem
        r = {"seg": round(dt, 1), "ram_mb": round(mb), "ok": rc == 0}
        if rc == 0:
            r.update(val(folder))
            ow = out_words(folder)
            outs[motor] = ow
            r["cob_ref"] = round(100 * sum((ref & ow).values()) / max(1, total), 2)
        else:
            r["error"] = log[-800:]
        row[motor] = r
        print(pdf.name, motor, r, flush=True)
    if len(outs) == 2:
        a, b = outs["pymupdf"], outs["libre"]
        row["coincidencia"] = round(100 * 2 * sum((a & b).values()) / max(1, sum(a.values()) + sum(b.values())), 2)
    res.append(row)
(HERE / "resultados.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print("FIN")
