#!/usr/bin/env python3
"""
pdf_to_md.py (v2) - Convierte PDFs (digitales, escaneados o mixtos) en una
estructura Markdown optimizada para cualquier IA (Claude, ChatGPT, Gemini...)
gastando el minimo de tokens. Todo local y gratuito: PyMuPDF + Pillow + Tesseract.

Salida por documento (output/<nombre-pdf>/):
    INDICE.md        Punto de entrada ligero: capitulos con su rango de paginas
    paginas.md       Mapa pagina a pagina (tokens, figuras, tablas, tema)
    pages/p001.md    Texto literal de cada pagina, con tablas y figuras en su sitio
    images/          Imagenes y dibujos vectoriales en WebP (sin perdida para
                     planos/esquemas, con perdida solo para fotos)
    tables/          Cada tabla en .md y .csv
    refs.md          Referencias cruzadas: id -> pagina, posicion, seccion, texto ancla
    manifest.json    Metadatos completos (bbox, etiquetas, OCR, formato)
    _validacion.md   Cobertura de palabras PDF vs salida, OCR y avisos

El texto nativo del PDF nunca se modifica. Lo leido por OCR se marca siempre
como ⟨ocr⟩ con su confianza, porque es una lectura de maquina, no texto original.

Uso:
    python scripts/pdf_to_md.py input/manual.pdf
    python scripts/pdf_to_md.py input/                    (todos los PDF)
    python scripts/pdf_to_md.py input/ --idiomas spa+eng+fra --ocr todo
    python scripts/pdf_to_md.py input/ --ocr no --dpi 200 --completo
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ----------------------------------------------------------------- dependencias
def _pip_install(pkg, label):
    print(f"Instalando {label} (solo la primera vez)...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pkg])
    import importlib
    import site
    importlib.invalidate_caches()
    # pip pudo instalar en la carpeta de usuario recien creada (que Python no tenia en
    # sys.path al arrancar). Solo se anade si este Python la usa: nunca dentro de un venv
    # ni con -I / PYTHONNOUSERSITE, para no mezclar paquetes de otra instalacion.
    try:
        if sys.prefix == sys.base_prefix and site.ENABLE_USER_SITE:
            user_site = site.getusersitepackages()
            if user_site not in sys.path and Path(user_site).is_dir():
                site.addsitedir(user_site)
    except Exception:
        pass


def _load_pymupdf():
    try:
        import pymupdf  # noqa
        return pymupdf
    except ImportError:
        pass
    try:
        import fitz  # noqa  (nombre antiguo)
        return fitz
    except ImportError:
        pass
    _pip_install("pymupdf", "PyMuPDF")
    try:
        import pymupdf  # noqa
    except ImportError:
        raise SystemExit("PyMuPDF se ha instalado, pero este Python no lo ve todavia. "
                         "Vuelve a ejecutar el mismo comando.")
    return pymupdf


def _load_pillow():
    try:
        from PIL import Image, features  # noqa
    except ImportError:
        _pip_install("pillow", "Pillow")
        try:
            from PIL import Image, features  # noqa
        except ImportError:
            raise SystemExit("Pillow se ha instalado, pero este Python no lo ve todavia. "
                             "Vuelve a ejecutar el mismo comando.")
    if not features.check("webp"):
        raise SystemExit("Tu Pillow no tiene soporte WebP. Ejecuta: python -m pip install -U pillow")
    return Image


def _motor_elegido():
    """--motor libre|pymupdf (o variable PDF_MD_MOTOR). Se lee antes de argparse porque
    el motor se carga al importar."""
    m = os.environ.get("PDF_MD_MOTOR", "libre")
    for i, a in enumerate(sys.argv):
        if a == "--motor" and i + 1 < len(sys.argv):
            m = sys.argv[i + 1]
        elif a.startswith("--motor="):
            m = a.split("=", 1)[1]
    return m


MOTOR = _motor_elegido()
if MOTOR == "libre":
    # pdfplumber (MIT) + pypdfium2 (Apache/BSD): sin AGPL, apto para uso comercial
    import motor_libre as pymupdf  # noqa: E402
else:
    pymupdf = _load_pymupdf()
Image = _load_pillow()
Image.MAX_IMAGE_PIXELS = None   # planos muy grandes son legitimos

# ----------------------------------------------------------------- parametros
MARGIN_RATIO = 0.07          # franja sup/inf donde buscar cabeceras y pies
FURNITURE_MIN_SHARE = 0.5    # % de paginas en que debe repetirse
FURNITURE_CONSTANT_SHARE = 0.8   # identica en >= 80 % de paginas: se omite (va una vez al INDICE)
SYMBOL_TOKEN = re.compile(r"[A-Za-z]{1,2}")   # lo unico que escribe una fuente de pictogramas
SYM_L, SYM_R = "⟦", "⟧"      # marca de glifo de fuente de simbolos: ⟦p⟧ no es la letra p
MIN_FIG_SIDE = 16            # pt: ignora iconos/puntos mas pequenos
MIN_VECTOR_SIDE = 30         # pt: lado largo minimo de un dibujo vectorial
SMALL_MARK_MAX = 40           # pt: tamano maximo de una marca ("12x", codigo) a unir a su figura
COL_GAP = 6                  # pt: hueco minimo entre columnas de texto
COL_MIN_CHARS = 150          # caracteres minimos para considerar columna de texto
MIN_VECTOR_THIN = 6          # pt: lado corto minimo (tornillos y muelles finos si cuentan)
BACKGROUND_RATIO = 0.85      # figura que cubre >85 % de la pagina = fondo
TEXT_HEAVY_CHARS = 250       # un "dibujo" con tanto texto es un recuadro, no figura
VECTOR_TEXT_ITEMS = 400      # trazos dentro de una tabla a partir de los cuales hay texto dibujado
REPEAT_MIN_PAGES = 4        # imagen identica en >= N paginas (o 5 %) = decorativa
TOC_MAX_REPEAT = 3           # titulos que se repiten mas (DANGER, NOTE...) no van al indice
LABEL_GAP = 24             # pt alrededor de una figura donde buscar llamadas
LABEL_MAX_CHARS = 15         # longitud maxima de una llamada/cota
INLINE_TABLE_MAX_ROWS = 40  # tablas mayores solo se referencian en la pagina
INDEX_INLINE_PAGES = 40      # hasta N paginas el mapa de paginas va tambien dentro del INDICE
VECTOR_RENDER_DPI = 200      # planos/esquemas vectoriales: nitidez para cotas y bornes
PHOTO_MAX_PX = 2000          # fotos: lado maximo (las IAs reducen a ~1500-2000 px igualmente)
LINEART_MAX_PX = 3200        # planos: lado maximo (no se reduce por debajo para no perder cotas)
WEBP_PHOTO_QUALITY = 80      # calidad WebP solo para fotos
OCR_DPI = 300                # resolucion para OCR de paginas escaneadas y celdas
OCR_MIN_CONF = 50            # palabras OCR por debajo se descartan como ruido
OCR_DOUBT_CONF = 75          # por debajo se listan como "dudosas"
OCR_FIG_MIN_MEAN = 70        # figura cuyo OCR tiene media inferior = foto/textura sin texto real
OCR_FIG_MIN_PX = 120        # no se hace OCR de imagenes mas pequenas
TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{}.traineddata"
KIT_DIR = Path(__file__).resolve().parent.parent
WORKERS = max(1, min(8, os.cpu_count() or 1))   # hilos en paralelo para WebP y OCR de figuras
BULLETS = "•●▪■◦‣∙·"
POS_V = ("sup", "centro", "inf")
POS_H = ("izq", "centro", "dcha")


# ----------------------------------------------------------------- utilidades
def rect_tuple(r):
    return [round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)]


def position_label(r, page_rect):
    cx = (r.x0 + r.x1) / 2 / page_rect.width
    cy = (r.y0 + r.y1) / 2 / page_rect.height
    v = POS_V[min(2, int(cy * 3))]
    h = POS_H[min(2, int(cx * 3))]
    if v == "centro" and h == "centro":
        return "centro"
    return f"{v}-{h}" if h != "centro" else v


def overlap_ratio(inner, outer):
    """Fraccion del area de `inner` que cae dentro de `outer`."""
    inter = pymupdf.Rect(inner) & outer
    if inter.is_empty or inner.is_empty:
        return 0.0
    return inter.get_area() / max(inner.get_area(), 1e-6)


def center_in(r, outer):
    return outer.contains(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))


def norm_furniture(s):
    return re.sub(r"\d+", "#", s.strip().lower())


def words_of(text):
    """Tokens comparables para la validacion (ignora signos sueltos)."""
    text = text.replace("\xad", "")   # guion blando invisible: el .md lo quita al escribir
    return [w for w in re.split(r"\s+", text) if w and re.search(r"\w", w)]


def md_escape_text(s):
    """Asteriscos literales del PDF (notas al pie "English*", "*Factory default"):
    sin escapar, el Markdown los toma por cursiva y desaparecen al visualizarlo."""
    return s.replace("*", "\\*")


def md_escape_line(s):
    s = s.replace("­", "")  # guion blando invisible
    if re.match(r"^\d+\.\s", s):
        s = re.sub(r"^(\d+)\.", r"\1\\.", s)       # "2. Paso" -> "2\. Paso" (no lista renumerada)
    elif re.match(r"^(#|>|\+\s|=+$|-{3,}$)", s):
        s = "\\" + s
    return s


def strip_ocr(text):
    """Quita de un .md generado todo lo leido por OCR (bloques, colas de etiquetas, celdas)."""
    out = []
    for l in text.split("\n"):
        if l.startswith(">") or l.startswith("*Lecturas dudosas"):
            continue
        l = re.sub(r" · ⟨ocr[^⟩]*⟩:.*$", "", l)        # cola OCR de la linea de una figura
        l = re.sub(r"⟨ocr[^⟩]*⟩[^|]*", "", l)          # celda de tabla completada por OCR
        out.append(l)
    return "\n".join(out)


SCAFFOLD = re.compile(r"^(# Página \d+|<!--.*-->|> \*\*Tabla .*|!\[.*\]\(.*\))$")


def strip_scaffold(text):
    """Quita las lineas que añade el conversor (titulo de pagina, ids de figura, enlaces):
    no son texto del PDF y en la validacion taparian palabras que faltan ("37" de "Página 37")."""
    out = []
    for l in text.split("\n"):
        s = l.strip()
        if SCAFFOLD.match(s):
            continue
        m_fig = re.match(r"^\*p\d+-[ft]\d+ · [^·*]*(.*)$", s)
        if m_fig:                                   # linea de figura: solo cuentan sus etiquetas
            rest = m_fig.group(1)
            l = rest.split("etiquetas:", 1)[1] if "etiquetas:" in rest else ""
        elif s.startswith("*Cabecera/pie:"):
            l = s[len("*Cabecera/pie:"):]
        elif s.startswith("*⚠ "):
            continue
        out.append(l)
    return "\n".join(out)


def md_plain(s):
    """Texto de un .md generado, sin marcas de formato, para validarlo contra el PDF."""
    s = re.sub(r"<!--.*?-->", " ", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)                 # enlaces a imagenes
    s = s.replace(SYM_L, "").replace(SYM_R, "")
    s = s.replace("\\*", "\x00").replace("**", "").replace("*", " ").replace("\x00", "*")
    return re.sub(r"\\([\\|#>.+=\-])", r"\1", s)


def short(s, n=90):
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def est_tokens(text):
    return max(1, round(len(text) / 3.6))  # castellano ~3.6 caracteres/token


def merge_rects(rects, tol=4):
    rects = [pymupdf.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out = []
        while rects:
            r = rects.pop()
            grown = pymupdf.Rect(r.x0 - tol, r.y0 - tol, r.x1 + tol, r.y1 + tol)
            i = 0
            while i < len(rects):
                if grown.intersects(rects[i]):
                    r |= rects.pop(i)
                    grown = pymupdf.Rect(r.x0 - tol, r.y0 - tol, r.x1 + tol, r.y1 + tol)
                    changed = True
                else:
                    i += 1
            out.append(r)
        rects = out
    return rects


# ----------------------------------------------------------------- texto
def mark_symbol(t):
    """'p' de una fuente de pictogramas -> '⟦p⟧' (conserva los espacios de alrededor)."""
    return re.sub(r"\S+", lambda m: SYM_L + m.group() + SYM_R, t)


def line_text(line, bold_md=True, symbol_fonts=frozenset()):
    parts, raw = [], []
    for sp in line["spans"]:
        t = sp["text"]
        if sp["font"] in symbol_fonts:
            t = mark_symbol(t)
        raw.append(t)
        t = md_escape_text(t)
        is_bold = bool(sp["flags"] & 16) or "bold" in sp["font"].lower()
        parts.append((t, is_bold and t.strip() != ""))
    # fusiona tramos en negrita consecutivos
    md, buf, cur_bold = [], "", None
    for t, b in parts:
        if cur_bold is None or b == cur_bold or not t.strip():
            buf += t
            cur_bold = b if t.strip() else cur_bold
        else:
            md.append((buf, cur_bold))
            buf, cur_bold = t, b
    if buf:
        md.append((buf, cur_bold))
    out = ""
    for t, b in md:
        if b and bold_md and t.strip():
            lead = t[: len(t) - len(t.lstrip())]
            trail = t[len(t.rstrip()):]
            out += f"{lead}**{t.strip()}**{trail}"
        else:
            out += t
    return out.rstrip(), "".join(raw).strip()


def join_lines(lines_md):
    """Conserva cada linea tal cual (en Markdown un salto simple no cuesta
    mas que un espacio y asi nunca se fusionan pasos ni items de lista)."""
    out = []
    bullet_pending = False
    for ln in lines_md:
        s = re.sub(r"[ \t -​]+", " ", ln).strip()
        if not s or s.replace("*", "").strip() == "":
            continue
        if s.replace("*", "").strip() in BULLETS + "-–":   # viñeta sola en su linea
            bullet_pending = True
            continue
        if s[0] in BULLETS:
            s = "- " + s[1:].lstrip()
        elif bullet_pending:
            s = "- " + s
        bullet_pending = False
        out.append(md_escape_line(s))
    # negrita partida entre lineas: "**a**\n**b**" se deja; "** **" dentro de linea se limpia
    return "\n".join(re.sub(r"\*\*\s+\*\*", " ", x) for x in out)


# ----------------------------------------------------------------- analisis global
def analyze_document(doc):
    """Tamano de letra del cuerpo y cabeceras/pies repetidos."""
    sizes = Counter()
    margin_lines = Counter()
    margin_raw = {}          # clave normalizada -> textos reales distintos
    font_spans = Counter()   # fuente -> tramos con texto
    font_texty = set()       # fuentes que escriben palabras de verdad
    n = len(doc)
    for page in doc:
        h = page.rect.height
        seen = set()
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for ln in b["lines"]:
                txt = "".join(s["text"] for s in ln["spans"]).strip()
                for s in ln["spans"]:
                    sizes[round(s["size"], 1)] += len(s["text"].strip())
                    toks = s["text"].split()
                    if toks:
                        font_spans[s["font"]] += 1
                        if not all(SYMBOL_TOKEN.fullmatch(t) for t in toks):
                            font_texty.add(s["font"])
                y0, y1 = ln["bbox"][1], ln["bbox"][3]
                if txt and (y1 < h * MARGIN_RATIO or y0 > h * (1 - MARGIN_RATIO)):
                    key = norm_furniture(txt)
                    margin_raw.setdefault(key, set()).add(txt)
                    if key not in seen:
                        seen.add(key)
                        margin_lines[key] += 1
    body = sizes.most_common(1)[0][0] if sizes else 10.0
    furniture, constant = set(), set()
    if n >= 3:
        furniture = {k for k, c in margin_lines.items() if c / n >= FURNITURE_MIN_SHARE}
        # solo se omite la cabecera/pie IDENTICA en casi todo el documento (titulo, version).
        # Las que cambian (numero de prompt o capitulo, nombre de seccion) dicen a que parte
        # pertenece la pagina: se conservan en cada pagina.
        constant = {k for k in furniture
                    if len(margin_raw[k]) == 1 and margin_lines[k] / n >= FURNITURE_CONSTANT_SHARE}
    # fuente de simbolos/pictogramas (p. ej. "GraphSch", Wingdings): en todo el documento solo
    # escribe letras sueltas. Su "p" es un dibujo (punto, flecha, >=), no la letra p.
    symbol_fonts = {f for f in font_spans if f not in font_texty}
    return body, furniture, constant, symbol_fonts


def is_page_number(txt):
    return re.fullmatch(r"(p[aá]g(ina)?\.?\s*)?\d{1,4}(\s*(/|de|of)\s*\d{1,4})?", txt.strip().lower()) is not None


# ----------------------------------------------------------------- figuras
def collect_figures(page, tables_rects, dpi, warnings, pno, drawings=None):
    pr = page.rect
    figs = []  # dict(rect, xrefs, kind)

    for info in page.get_image_info(xrefs=True):
        r = pymupdf.Rect(info["bbox"]) & pr
        if r.is_empty or r.width < MIN_FIG_SIDE or r.height < MIN_FIG_SIDE:
            continue
        figs.append({"rect": r, "xrefs": [info.get("xref", 0)], "kind": "raster",
                     "transform": info.get("transform")})

    vec = []
    small = []
    try:
        if drawings is None:
            drawings = page.get_drawings()
        if drawings:
            for r in page.cluster_drawings(drawings=drawings):
                r = pymupdf.Rect(r) & pr
                # pieza larga y estrecha (tornillo, muelle, varilla): cuenta si su lado largo
                # llega al minimo; las lineas sueltas (lado corto < MIN_VECTOR_THIN) no
                if max(r.width, r.height) < MIN_VECTOR_SIDE or min(r.width, r.height) < MIN_VECTOR_THIN:
                    if not r.is_empty or (r.width > 0 or r.height > 0):
                        small.append(r)        # cantidad "12x" o codigo dibujados como trazos
                    continue
                if r.get_area() > pr.get_area() * 0.95:      # marco de pagina
                    continue
                if any(overlap_ratio(r, t) > 0.5 for t in tables_rects):  # rejilla de tabla
                    continue
                vec.append(r)
    except Exception as e:  # versiones antiguas sin cluster_drawings
        warnings.append(f"p{pno}: no se pudieron agrupar dibujos vectoriales ({e})")

    if vec or figs:
        # trazos pequenos pegados a una figura (cantidad "12x", codigo de pieza, cota) se
        # dibujan como vectores y no son texto: se incluyen en el recorte de su figura para
        # que la imagen y el OCR los conserven. Un solo paso, sin encadenar.
        targets = vec + [f["rect"] for f in figs]
        for r in small:
            if max(r.width, r.height) > SMALL_MARK_MAX:
                continue
            near = [t for t in targets if pymupdf.Rect(t.x0 - LABEL_GAP, t.y0 - LABEL_GAP,
                                                          t.x1 + LABEL_GAP, t.y1 + LABEL_GAP).intersects(r)
                    or r.intersects(t)]
            if near:
                t = min(near, key=lambda t: abs((t.x0 + t.x1) / 2 - (r.x0 + r.x1) / 2)
                        + abs((t.y0 + t.y1) / 2 - (r.y0 + r.y1) / 2))
                t |= r
                if t not in vec:              # figura raster: pasa a recortarse como render
                    for f in figs:
                        if f["rect"] is t:
                            f["kind"], f["xrefs"] = "vector", []
    if vec:
        # si un raster cae dentro de un dibujo vectorial, forman una sola figura
        rects = vec + [f["rect"] for f in figs if any(f["rect"].intersects(v) for v in vec)]
        merged = merge_rects(rects)
        rasters_alone = [f for f in figs if not any(f["rect"].intersects(m) for m in merged)]
        figs = rasters_alone + [{"rect": m, "xrefs": [], "kind": "vector"} for m in merged]

    # descarta "figuras" que en realidad son recuadros de texto
    words = page.get_text("words")
    kept = []
    for f in figs:
        if f["kind"] == "vector":
            chars = sum(len(w[4]) for w in words if center_in(pymupdf.Rect(w[:4]), f["rect"]))
            if chars > TEXT_HEAVY_CHARS:
                continue
        kept.append(f)

    kept.sort(key=lambda f: (round(f["rect"].y0), f["rect"].x0))
    for f in kept:
        f["background"] = f["rect"].get_area() > pr.get_area() * BACKGROUND_RATIO
    return kept


# ----------------------------------------------------------------- OCR (Tesseract, local y gratis)
class OCR:
    """Envuelve el ejecutable de Tesseract. Si no esta, el OCR se desactiva
    con un aviso y la conversion sigue (nunca se bloquea)."""

    def __init__(self, langs, mode, warnings):
        self.langs, self.mode, self.warnings = langs, mode, warnings
        self.exe = None
        self.tessdata = None
        self.version = ""
        self.cache = {}
        self.tried_install = False
        if mode != "no":
            self._setup(install=False)

    @staticmethod
    def _find_exe():
        exe = shutil.which("tesseract")
        if exe:
            return exe
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
                     "/usr/bin", "/usr/local/bin", "/opt/homebrew/bin"):
            for cand in (Path(base) / "Tesseract-OCR" / "tesseract.exe", Path(base) / "tesseract"):
                if cand.is_file():
                    return str(cand)
        return None

    def _run(self, args, **kw):
        flags = 0x08000000 if os.name == "nt" else 0          # sin ventana de consola
        # un hilo por Tesseract: el paralelismo lo pone el script (varias imagenes a la vez)
        env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
        return subprocess.run([self.exe] + args, capture_output=True, creationflags=flags, env=env, **kw)

    def _langs_available(self, tessdata=None):
        args = ["--list-langs"] + (["--tessdata-dir", str(tessdata)] if tessdata else [])
        r = self._run(args)
        out = (r.stdout + r.stderr).decode("utf-8", "replace").splitlines()
        return {x.strip() for x in out if x.strip() and " " not in x.strip()}

    def _setup(self, install):
        self.exe = self._find_exe()
        if not self.exe and install and not self.tried_install:
            self.tried_install = True
            self._install()
            self.exe = self._find_exe()
        if not self.exe:
            return
        try:
            self.version = self._run(["--version"]).stdout.decode("utf-8", "replace").split("\n")[0].strip()
        except Exception:
            pass
        wanted = [x for x in self.langs.split("+") if x]
        if set(wanted) <= self._langs_available():
            return
        # faltan idiomas: se descargan gratis (repositorio oficial) a la carpeta del kit
        local = KIT_DIR / "tessdata"
        local.mkdir(exist_ok=True)
        for lang in set(wanted + ["eng"]):
            dst = local / f"{lang}.traineddata"
            if dst.exists():
                continue
            try:
                print(f"Descargando idioma OCR '{lang}' (gratis, solo la primera vez)...")
                urllib.request.urlretrieve(TESSDATA_URL.format(lang), dst)
            except Exception as e:
                self.warnings.append(f"OCR: no se pudo descargar el idioma '{lang}' ({e}).")
        if set(wanted) <= self._langs_available(local):
            self.tessdata = local
        else:
            have = self._langs_available(local) & set(wanted)
            if have:
                self.tessdata, self.langs = local, "+".join(sorted(have))
                self.warnings.append(f"OCR: se usara solo '{self.langs}'.")
            else:
                self.warnings.append("OCR desactivado: no hay ningun idioma disponible.")
                self.exe = None

    def _install(self):
        if os.name != "nt" or not shutil.which("winget"):
            return
        print("Instalando Tesseract OCR (gratis, codigo abierto). "
              "Windows puede pedirte permiso: pulsa 'Si'.")
        try:
            subprocess.run(["winget", "install", "-e", "--id", "UB-Mannheim.TesseractOCR",
                            "--accept-source-agreements", "--accept-package-agreements", "--silent"],
                           timeout=900)
        except Exception:
            pass

    def ensure(self):
        """Llamado cuando el documento REALMENTE necesita OCR (escaneos, texto en trazos)."""
        if self.mode != "no" and not self.exe and not self.tried_install:
            self._setup(install=True)
            if not self.exe:
                self.warnings.append(
                    "OCR no disponible: instala Tesseract (gratis) con "
                    "`winget install -e --id UB-Mannheim.TesseractOCR` y vuelve a convertir. "
                    "Mientras tanto esas zonas quedan solo como imagen.")
        return self.exe is not None

    @property
    def ready(self):
        return self.exe is not None

    def read(self, img, psm=3):
        """Devuelve lista de palabras: dict(text, conf, block, par, line, box)."""
        if not self.exe:
            return []
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        key = hashlib.sha1(img.tobytes()).hexdigest() + f"/{psm}"
        if key in self.cache:
            return self.cache[key]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "i.png"
            img.save(p)
            args = [str(p), "stdout", "-l", self.langs, "--psm", str(psm)]
            if self.tessdata:
                args += ["--tessdata-dir", str(self.tessdata)]
            try:
                # "-c tessedit_create_tsv=1" en vez del config "tsv": este ultimo vive en la
                # carpeta de instalacion y no se encuentra al usar el tessdata propio del kit
                r = self._run(args + ["-c", "tessedit_create_tsv=1"], timeout=180)
            except Exception as e:
                self.warnings.append(f"OCR: fallo en una imagen ({e}).")
                return []
        words = []
        for row in r.stdout.decode("utf-8", "replace").splitlines()[1:]:
            c = row.split("\t")
            if len(c) < 12 or not c[11].strip():
                continue
            try:
                conf = float(c[10])
            except ValueError:
                continue
            if conf < OCR_MIN_CONF or not re.search(r"\w", c[11]):
                continue
            words.append({"text": c[11].strip(), "conf": conf, "block": int(c[2]), "par": int(c[3]),
                          "line": int(c[4]), "box": (int(c[6]), int(c[7]), int(c[8]), int(c[9]))})
        self.cache[key] = words
        return words


def ocr_lines(words):
    """Agrupa palabras OCR en parrafos de lineas, respetando el orden de Tesseract."""
    paras, cur_key, cur_line, line_key = [], None, None, None
    for w in words:
        pk = (w["block"], w["par"])
        lk = pk + (w["line"],)
        if pk != cur_key:
            paras.append([])
            cur_key, line_key = pk, None
        if lk != line_key:
            paras[-1].append([])
            line_key = lk
        paras[-1][-1].append(w["text"])
    return ["\n".join(" ".join(l) for l in p) for p in paras if p]


def clean_figure_ocr(words):
    """Filtra el ruido tipico del OCR sobre fotos y dibujos: texturas y
    trazos leidos como letras ("Y =4 TR one Mos", "M", "ly,")."""
    if not words:
        return []
    raw_mean = sum(w["conf"] for w in words) / len(words)
    if raw_mean < OCR_FIG_MIN_MEAN:
        return []                                 # imagen sin texto real
    alnum = lambda s: len(re.sub(r"\W", "", s))
    line = lambda w: (w["block"], w["par"], w["line"])
    strong = [w for w in words if w["conf"] >= 80 or (w["conf"] >= 60 and alnum(w["text"]) >= 4)]
    strong_lines = {line(w) for w in strong}
    strong_ids = {id(w) for w in strong}
    # una palabra corta con confianza media se conserva si comparte linea con una lectura
    # fiable: prefijos de matricula/HIN ("IT" + "TSGLY16CD223"), unidades ("230 V"), etc.
    # Solo codigos en MAYUSCULAS (>= 2 letras) o con cifras: el ruido de texturas sale
    # casi siempre en minusculas ("ess", "vs", "ooo").
    kept = [w for w in words if id(w) in strong_ids or
            (w["conf"] >= 60 and line(w) in strong_lines and re.fullmatch(r"[\w°/.,:%~+-]+", w["text"])
             and (re.search(r"\d", w["text"]) or (w["text"].isupper() and alnum(w["text"]) >= 2)))]
    if sum(alnum(w["text"]) for w in kept) < 3:
        return []
    return kept


def ocr_compact(words):
    """Una linea: palabras de la misma linea con espacio, lineas con ' | '."""
    return " | ".join(" ".join(l.split()) for p in ocr_lines(words) for l in p.split("\n"))


def is_running_text(words):
    """Texto corrido (parrafos) frente a etiquetas sueltas de un plano."""
    lines = [l for p in ocr_lines(words) for l in p.split("\n")]
    return len(words) > 25 and len(words) / max(1, len(lines)) >= 4


def ocr_summary(words):
    if not words:
        return 0, []
    conf = round(sum(w["conf"] for w in words) / len(words))
    doubt = [w["text"] for w in words if w["conf"] < OCR_DOUBT_CONF]
    return conf, doubt


# ----------------------------------------------------------------- imagenes (WebP)
def flatten(img):
    """Transparencia -> fondo blanco (convertir a RGB sin mas la deja en negro
    y un esquema con fondo transparente desapareceria)."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.getchannel("A"))
        return bg
    if img.mode in ("CMYK", "P", "I", "F", "1", "I;16"):
        return img.convert("RGB")
    return img


def classify(img):
    """'lineart' (planos, esquemas, texto, iconos) o 'foto'. Y si es en grises."""
    small = img.convert("RGB").resize((min(200, img.width), min(200, img.height)), Image.NEAREST)
    colors = small.getcolors(maxcolors=50000) or []
    total = small.width * small.height
    gray = all(abs(r - g) < 10 and abs(g - b) < 10 for _, (r, g, b) in colors) if colors else False
    if not colors:
        return "foto", gray
    # en un plano/esquema/texto unos pocos colores (fondo + trazo + antialias) cubren casi todo;
    # en una foto (tambien en grises) los tonos estan repartidos
    top = sorted((c for c, _ in colors), reverse=True)
    concentration = sum(top[:16]) / total
    kind = "lineart" if concentration >= 0.80 else "foto"
    return kind, gray


def downscale(img, max_px):
    if max(img.size) <= max_px:
        return img
    k = max_px / max(img.size)
    return img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)


def encode_best(img, original=None, original_ext=None):
    """Elige el archivo MAS PEQUENO que no pierda contenido:
    - planos/esquemas/texto: WebP SIN perdida (lineas finas y cotas intactas)
    - fotos: WebP con perdida (calidad 80)
    - si el original del PDF ya es mas pequeno (y valido para ese tipo), se conserva."""
    img = flatten(img)
    kind, gray = classify(img)
    if gray and img.mode != "L":
        img = img.convert("L")
    img = downscale(img, LINEART_MAX_PX if kind == "lineart" else PHOTO_MAX_PX)
    buf = io.BytesIO()
    if kind == "lineart":
        img.save(buf, "WEBP", lossless=True, quality=100, method=4)
    else:
        img.save(buf, "WEBP", quality=WEBP_PHOTO_QUALITY, method=4)
    data, ext = buf.getvalue(), "webp"
    # el original solo gana si es menor y no degrada: jpeg para fotos, png para lineart
    if original and len(original) < len(data):
        if (kind == "foto" and original_ext in ("jpeg", "jpg")) or (kind == "lineart" and original_ext == "png"):
            data, ext = original, ("jpg" if original_ext == "jpeg" else original_ext)
    if ext == "webp":
        fmt = "webp sin pérdida" if kind == "lineart" else f"webp calidad {WEBP_PHOTO_QUALITY}"
    else:
        fmt = f"{ext} original del PDF (era más pequeño)"
    return data, ext, kind, fmt, img.size


def figure_image(doc, page, fig, dpi):
    """Devuelve (PIL.Image, bytes_originales|None, ext_original|None, origen)."""
    r = fig["rect"]
    if fig["kind"] == "raster" and fig["xrefs"] and fig["xrefs"][0]:
        xref = fig["xrefs"][0]
        t = fig.get("transform") or (1, 0, 0, 1, 0, 0)
        plain = abs(t[1]) < 1e-6 and abs(t[2]) < 1e-6 and t[0] > 0 and t[3] > 0
        if plain:
            try:
                info = doc.extract_image(xref)
                pix = pymupdf.Pixmap(doc, xref)
                if info.get("smask"):
                    pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, info["smask"]))   # conserva transparencia
                if pix.colorspace and pix.colorspace.n not in (1, 3):
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)                        # CMYK -> RGB
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                img.load()
                orig = info["image"] if not info.get("smask") else None
                return img, orig, info.get("ext"), "original"
            except Exception:
                pass
    clip = pymupdf.Rect(r.x0 - 2, r.y0 - 2, r.x1 + 2, r.y1 + 2) & page.rect
    rdpi = max(dpi, VECTOR_RENDER_DPI) if fig["kind"] == "vector" else dpi
    pix = page.get_pixmap(clip=clip, dpi=rdpi, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return img, None, None, "render"


def figure_job(img, orig, oext, ocr, want_ocr, native):
    """Trabajo de un hilo: codifica la figura y, si procede, lee su texto por OCR.
    Pillow (WebP) y Tesseract (proceso externo) trabajan en paralelo de verdad."""
    data, ext, kind, fmt, size = encode_best(img, orig, oext)
    words = []
    if want_ocr:
        oimg = flatten(img)
        if max(oimg.size) < 1000:
            oimg = oimg.resize((oimg.width * 2, oimg.height * 2), Image.LANCZOS)
        words = clean_figure_ocr([w for w in ocr.read(oimg, psm=11) if w["text"].lower() not in native])
    return {"data": data, "ext": ext, "kind_img": kind, "format": fmt, "px": list(size), "ocr_words": words}


# ----------------------------------------------------------------- tablas
def cell(s):
    if s is None:
        return ""
    return md_escape_text(" ".join(str(s).split("\n")).replace("|", "\\|").strip())


def _nearest(intervals, v):
    """Indice del intervalo (a, b) que contiene v o, si ninguno, el mas cercano.
    Si varios lo contienen (filas con celdas fusionadas en vertical), el mas estrecho."""
    best, bkey = None, None
    for i, iv in enumerate(intervals):
        if iv is None:
            continue
        a, b = iv
        d = 0 if a <= v <= b else min(abs(v - a), abs(v - b))
        key = (d, b - a)
        if bkey is None or key < bkey:
            best, bkey = i, key
    return best


def table_rows(page, tab, page_words=None):
    """Relee cada celda desde su zona del PDF: t.extract() puede perder
    espacios ("M4 x 16" -> "M4x16"), y eso altera medidas y codigos.
    NINGUNA palabra dentro de la tabla se pierde: si la rejilla detectada esta
    incompleta (ultima columna sin borde, cabecera fusionada, filas sin linea),
    la palabra va a la fila y columna que le corresponden por posicion."""
    try:
        tr = pymupdf.Rect(tab.bbox)
        if page_words is None:
            page_words = page.get_text("words")
        # cada PALABRA completa va a la celda que contiene su centro: asi no se
        # parten palabras que sobresalen del borde ("TANK" -> "TAN" + "NK")
        words = [w for w in page_words if center_in(pymupdf.Rect(w[:4]), tr)]
        grid = [list(row.cells) for row in tab.rows]
        if not grid:
            return tab.extract()
        ncol = max(len(r) for r in grid)
        for r in grid:
            r += [None] * (ncol - len(r))
        # ancho real de cada columna = su celda mas estrecha (las celdas fusionadas que
        # abarcan varias columnas, p. ej. una fila de titulo, harian creer que una columna
        # ocupa toda la tabla)
        col_x = []
        for ci in range(ncol):
            xs = [r[ci] for r in grid if r[ci]]
            c = min(xs, key=lambda c: c[2] - c[0]) if xs else None
            col_x.append((c[0], c[2]) if c else None)
        row_y = [(row.bbox[1], row.bbox[3]) for row in tab.rows]
        buckets = {}
        prev = None           # (palabra, celda) anterior en orden de lectura
        for w in sorted(words, key=lambda w: (w[5], w[6], w[7])):
            wr = pymupdf.Rect(w[:4])
            hit = next(((ri, ci) for ri, r in enumerate(grid) for ci, c in enumerate(r)
                        if c and center_in(wr, pymupdf.Rect(c))), None)
            if hit is None:   # fuera de toda celda detectada: se ubica por posicion
                ri = _nearest(row_y, (wr.y0 + wr.y1) / 2)
                ci = _nearest(col_x, (wr.x0 + wr.x1) / 2)
                hit = (ri or 0, ci or 0)
            # misma linea del PDF y separadas solo por un espacio normal: es una sola expresion
            # ("500 V") que el borde de una columna detectada no debe partir
            if prev and prev[1] != hit and (prev[0][5], prev[0][6]) == (w[5], w[6]):
                gap = w[0] - prev[0][2]
                if -1 <= gap < 0.5 * (w[3] - w[1]):
                    hit = prev[1]
                elif hit[0] != prev[1][0]:
                    # misma linea = misma linea base: nunca pueden ir a filas distintas
                    # ("WH: blanco" de una leyenda de colores no debe separarse de fila)
                    hit = (prev[1][0], hit[1])
            buckets.setdefault(hit, []).append(w)
            prev = (w, hit)
        # celda combinada que la rejilla parte en filas (hojas de calculo exportadas: sin lineas
        # entre filas): si un mismo parrafo del PDF continua en la fila siguiente de una columna,
        # es una sola celda. Se une en la primera; las demas quedan como fusionadas (None).
        # bloque del PDF -> columnas en que aparece, por fila: un bloque repartido en varias
        # columnas de la misma fila es una tabla/leyenda dentro de un bloque, no un parrafo
        row_block_cols = {}
        for (ri, ci), ws in buckets.items():
            for w in ws:
                row_block_cols.setdefault((ri, w[5]), set()).add(ci)
        merged = set()
        for ci in range(ncol):
            anchor, prev_blocks = None, set()
            for ri in range(len(grid)):
                ws = buckets.get((ri, ci))
                if not ws:
                    anchor, prev_blocks = None, set()
                    continue
                blocks = {w[5] for w in ws}
                shared = blocks & prev_blocks
                if anchor is not None and shared and all(row_block_cols[(ri, b)] == {ci} for b in shared):
                    buckets[(anchor, ci)].extend(buckets.pop((ri, ci)))
                    merged.add((ri, ci))
                else:
                    anchor = ri
                prev_blocks = blocks
        rows = []
        for ri, r in enumerate(grid):
            out = []
            for ci, c in enumerate(r):
                ws = sorted(buckets.get((ri, ci), []), key=lambda w: (w[5], w[6], w[7]))
                if (c is None and not ws) or (ri, ci) in merged:
                    out.append(None)          # celda fusionada con otra
                    continue
                lines, key = [], None
                for w in ws:
                    k = (w[5], w[6])
                    if k != key:
                        lines.append(w[4])
                        key = k
                    else:
                        lines[-1] += " " + w[4]
                out.append("\n".join(lines))
            rows.append(out)
        return rows
    except Exception:
        return tab.extract()


def _rows_and_score(page, tab, page_words=None):
    try:
        rows = table_rows(page, tab, page_words)
        return rows, sum(1 for r in rows for c in r if c)
    except Exception:
        return None, -1


def split_nested_tables(page, tables):
    """PyMuPDF a veces devuelve una "tabla" que CONTIENE otras: un falso agrupamiento de
    varias tablas (p. ej. dos columnas de tablas en un indice). Su texto saldria dos veces.
    Se quita la contenedora, se conservan las de dentro y se buscan tablas en las franjas
    que quedan libres (lo que no forme tabla sale como texto: nunca se pierde)."""
    inside = lambda i, o: i is not o and overlap_ratio(pymupdf.Rect(i.bbox), pymupdf.Rect(o.bbox)) > 0.9
    containers = [t for t in tables if any(inside(u, t) for u in tables)]
    if not containers:
        return tables
    kept = [t for t in tables if t not in containers]
    for c in containers:
        cr = pymupdf.Rect(c.bbox)
        inner = [pymupdf.Rect(u.bbox) for u in tables if inside(u, c)]
        ux0, ux1 = min(r.x0 for r in inner), max(r.x1 for r in inner)
        uy0, uy1 = min(r.y0 for r in inner), max(r.y1 for r in inner)
        strips = [pymupdf.Rect(cr.x0, cr.y0, ux0 - 1, cr.y1), pymupdf.Rect(ux1 + 1, cr.y0, cr.x1, cr.y1),
                  pymupdf.Rect(ux0, cr.y0, ux1, uy0 - 1), pymupdf.Rect(ux0, uy1 + 1, ux1, cr.y1)]
        for s in strips:
            if s.width < 40 or s.height < 20:
                continue
            # el analisis de maquetacion de PyMuPDF ignora el recorte: se desactiva y las
            # columnas se deducen del texto (estas tablas solo suelen tener lineas horizontales)
            found = []
            for kw in ({"use_layout": False}, {"use_layout": False, "vertical_strategy": "text"}):
                try:
                    found = [t for t in page.find_tables(clip=s, **kw).tables
                             if t.row_count >= 2 and t.col_count >= 2]
                except Exception:
                    found = []
                if found:
                    break
            for t in found:
                tr = pymupdf.Rect(t.bbox)
                if (t.row_count >= 2 and t.col_count >= 2
                        and not any(overlap_ratio(tr, pymupdf.Rect(k.bbox)) > 0.1 for k in kept)):
                    kept.append(t)
    return kept


def find_tables_best(page, page_words=None):
    """Detecta tablas con la rejilla normal y con una fina; para cada tabla se
    queda con la version que separa mas celdas (evita filas fusionadas, que
    mezclan p. ej. la cantidad de una pieza con la de otra).
    Devuelve [(tabla, filas)]: las filas ya leidas no se vuelven a leer."""
    base = [t for t in page.find_tables().tables if t.row_count >= 2 and t.col_count >= 2]
    if not base:
        return []
    base = split_nested_tables(page, base)
    try:
        fine = [t for t in page.find_tables(snap_tolerance=1, join_tolerance=1).tables
                if t.row_count >= 2 and t.col_count >= 2]
    except Exception:
        fine = []
    if page_words is None:
        page_words = page.get_text("words")
    out = []
    for t in base:
        r = pymupdf.Rect(t.bbox)
        best = (t, *_rows_and_score(page, t, page_words))
        for u in fine:
            ur = pymupdf.Rect(u.bbox)
            if overlap_ratio(ur, r) > 0.8 and overlap_ratio(r, ur) > 0.8:
                cand = (u, *_rows_and_score(page, u, page_words))
                if cand[2] > best[2]:
                    best = cand
        tab, rows, _ = best
        out.append((tab, rows if rows is not None else tab.extract()))
    return out


def page_tables(page, page_words=None):
    """Tablas de una pagina como datos simples (se pueden pasar entre procesos)."""
    res = []
    for t, rows in find_tables_best(page, page_words):
        try:
            cells = [[None if c is None else tuple(c) for c in r.cells] for r in t.rows]
        except Exception:
            cells = None
        res.append({"bbox": tuple(t.bbox), "rows": [list(r) for r in rows], "cells": cells})
    return res
# Nota: la deteccion de tablas NO se reparte entre procesos. Medido con un manual de
# 368 paginas en un i5 de 10 nucleos: con 2 procesos solo gana un 15 % y con 8 tarda MAS
# que en serie (las paginas con 100.000 trazos saturan memoria). En serie es lo mas fiable.


def vector_items_inside(drawings, rect):
    return sum(len(d["items"]) for d in drawings if overlap_ratio(pymupdf.Rect(d["rect"]), rect) > 0.8)


def reading_order(blocks):
    """Orden de lectura por columnas (corte XY). Antes se ordenaba por filas (y, x) y en una
    pagina a 3 columnas (avisos de seguridad en 20 idiomas) mezclaba un idioma con otro.
    - Primero se intenta separar en COLUMNAS, pero solo si cada columna tiene texto de verdad
      (>= COL_MIN_CHARS): asi los numeros de paso de IKEA no se separan de su dibujo.
    - Si no, en FRANJAS horizontales sin solape, y cada una se vuelve a analizar.
    - Si no se puede cortar, el orden de siempre: filas (y, x)."""
    def chars(group):
        return sum(len(b.get("raw", "")) for b in group if b["kind"] in ("text", "head"))

    def split(items, axis):
        lo, hi = ("x0", "x1") if axis == "x" else ("y0", "y1")
        gap = COL_GAP if axis == "x" else 0.5
        items = sorted(items, key=lambda b: getattr(b["rect"], lo))
        groups, cur, edge = [], [items[0]], getattr(items[0]["rect"], hi)
        for b in items[1:]:
            if getattr(b["rect"], lo) >= edge + gap:
                groups.append(cur)
                cur = []
            cur.append(b)
            edge = max(edge, getattr(b["rect"], hi))
        groups.append(cur)
        return groups

    def cut(items, depth=0):
        if len(items) <= 1 or depth > 30:
            return sorted(items, key=lambda x: (round(x["rect"].y0 / 3), x["rect"].x0))
        cols = split(items, "x")
        if len(cols) > 1 and all(chars(c) >= COL_MIN_CHARS for c in cols):
            return [b for c in cols for b in cut(c, depth + 1)]
        rows = split(items, "y")
        if len(rows) > 1:
            return [b for r in rows for b in cut(r, depth + 1)]
        return sorted(items, key=lambda x: (round(x["rect"].y0 / 3), x["rect"].x0))

    return cut(blocks)


def table_markdown(rows):
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [list(r) + [""] * (width - len(r)) for r in rows]
    head = [cell(c) for c in rows[0]]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * width]
    for r in rows[1:]:
        lines.append("| " + " | ".join(cell(c) for c in r) + " |")
    return "\n".join(lines)


# ----------------------------------------------------------------- conversion
def convert(pdf_path: Path, out_root: Path, dpi: int, completo: bool, ocr: "OCR"):
    ocr_stats = {"pages": [], "figures": 0, "cells": 0}
    warnings = []
    ocr.warnings = warnings          # avisos del OCR van al informe de este documento
    doc = pymupdf.open(pdf_path)
    if doc.needs_pass:
        raise SystemExit(f"'{pdf_path.name}' esta protegido con contrasena.")
    # carpeta = nombre original del PDF (solo se sustituyen caracteres prohibidos en Windows)
    slug = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", pdf_path.stem).rstrip(" .") or "documento"
    out = out_root / slug
    for sub in ("pages", "images", "tables"):
        (out / sub).mkdir(parents=True, exist_ok=True)
        for old in (out / sub).glob("*"):
            old.unlink()

    body_size, furniture_keys, furniture_constant, symbol_fonts = analyze_document(doc)
    symbols = {}             # (fuente, glifo) -> {"count", "page", "bbox"} para la leyenda
    running_by_page = {}     # pno -> cabeceras/pies que cambian (seccion, n.º de prompt...)
    furniture_seen = {}
    heading_sizes = set()
    pages_data = []
    hashes = {}
    items = []          # manifest de elementos no textuales
    headings = []
    validation = []
    npages = len(doc)
    pad = max(3, len(str(npages)))

    # ------- primera pasada: recoge bloques por pagina
    for pno, page in enumerate(doc, start=1):
        pr = page.rect
        d = page.get_text("dict", sort=True)
        text_blocks = [b for b in d["blocks"] if b["type"] == 0]
        page_words = page.get_text("words")
        # glifos de fuentes de pictogramas: se marcan ⟦p⟧ tambien en las tablas
        sym_rects = []
        for b in text_blocks:
            for ln in b["lines"]:
                for s in ln["spans"]:
                    if s["font"] in symbol_fonts and s["text"].strip():
                        sym_rects.append((pymupdf.Rect(s["bbox"]), s["font"]))
        words_marked = page_words
        if sym_rects:
            words_marked = []
            for w in page_words:
                wr = pymupdf.Rect(w[:4])
                font = next((f for r, f in sym_rects if center_in(wr, r)), None)
                if font is None:
                    words_marked.append(w)
                    continue
                e = symbols.setdefault((font, w[4]), {"count": 0, "page": pno, "bbox": tuple(wr)})
                e["count"] += 1
                words_marked.append(w[:4] + (mark_symbol(w[4]),) + tuple(w[5:]))

        try:
            tabs = page_tables(page, words_marked)
        except Exception as e:
            tabs = []
            warnings.append(f"p{pno}: fallo detectando tablas ({e})")
        tables_rects = [pymupdf.Rect(t["bbox"]) for t in tabs]

        try:
            page_drawings = page.get_drawings()
        except Exception:
            page_drawings = []
        figs = collect_figures(page, tables_rects, dpi, warnings, pno, page_drawings)
        fig_label_zones = [f for f in figs if not f["background"]]
        for f in figs:
            f["labels"] = []

        page_chars = sum(len(s["text"].strip()) for b in text_blocks for ln in b["lines"] for s in ln["spans"])
        img_area = sum(f["rect"].get_area() for f in figs if f["kind"] == "raster")
        scanned = page_chars < 10 and img_area > pr.get_area() * 0.3

        blocks = []
        out_words = []
        running = []
        for b in text_blocks:
            kept_md, kept_raw, sizes, all_bold = [], [], [], True
            for ln in b["lines"]:
                md, raw = line_text(ln, symbol_fonts=symbol_fonts)
                if not raw:
                    continue
                lr = pymupdf.Rect(ln["bbox"])
                # cabecera / pie / numero de pagina
                in_margin = lr.y1 < pr.height * MARGIN_RATIO or lr.y0 > pr.height * (1 - MARGIN_RATIO)
                # dentro de una tabla (p. ej. el cajetin de un plano) la linea es de la tabla:
                # si se tratara ademas como cabecera/pie saldria dos veces
                in_table = any(center_in(lr, t) for t in tables_rects)
                if in_margin and not in_table and (norm_furniture(raw) in furniture_keys or is_page_number(raw)):
                    if is_page_number(raw):
                        pass
                    elif norm_furniture(raw) in furniture_constant:
                        furniture_seen.setdefault(norm_furniture(raw), raw)
                    else:
                        running.append(raw)      # cabecera que cambia: se conserva en la pagina
                    out_words += words_of(raw)
                    continue
                # cada palabra va a UN solo sitio: a la tabla si su centro cae dentro (table_rows
                # la recoge), al texto si no. Asi no se pierde ni se duplica nada en los bordes.
                if any(lr.intersects(t) for t in tables_rects):
                    in_line = [w for w in words_marked if center_in(pymupdf.Rect(w[:4]), lr)]
                    rest = [w[4] for w in in_line
                            if not any(center_in(pymupdf.Rect(w[:4]), t) for t in tables_rects)]
                    if in_line and not rest:
                        continue
                    if rest and len(rest) < len(in_line):      # linea partida por el borde de la tabla
                        raw = " ".join(rest)
                        md = md_escape_text(raw)
                # dentro de una figura: pasa a ser etiqueta de la figura
                host = next((f for f in fig_label_zones if center_in(lr, f["rect"])), None)
                if host is None and len(raw) <= LABEL_MAX_CHARS:
                    # cota/llamada corta pegada al dibujo (p. ej. "C", "4x", "12x")
                    host = next((f for f in fig_label_zones
                                 if center_in(lr, pymupdf.Rect(f["rect"].x0 - LABEL_GAP, f["rect"].y0 - LABEL_GAP,
                                                               f["rect"].x1 + LABEL_GAP, f["rect"].y1 + LABEL_GAP))),
                                None)
                    if host is not None and host["kind"] == "vector":
                        host["rect"] |= lr      # la imagen renderizada incluira la llamada
                if host is not None:
                    host["labels"].append(raw)
                    out_words += words_of(raw)
                    continue
                kept_md.append(md)
                kept_raw.append(raw)
                out_words += words_of(raw)
                for s in ln["spans"]:
                    if s["text"].strip():
                        sizes.append(s["size"])
                        if not (s["flags"] & 16 or "bold" in s["font"].lower()):
                            all_bold = False
            if not kept_md:
                continue
            avg = sum(sizes) / len(sizes) if sizes else body_size
            raw_all = " ".join(kept_raw)
            is_head = (len(raw_all) <= 120 and len(re.findall(r"[^\W\d_]", raw_all)) >= 2
                       and not re.search(r"\.{5,}|…{2,}", raw_all)) and (   # no lineas de indice con puntos
                avg >= body_size * 1.18 or (all_bold and len(kept_raw) == 1 and avg >= body_size * 0.98
                                            and not raw_all.endswith((".", ":", ",")))
            )
            size_key = round(avg) if avg >= body_size * 1.18 else 0
            if is_head:
                heading_sizes.add(size_key)
            r = pymupdf.Rect(b["bbox"])
            blocks.append({"kind": "head" if is_head else "text", "rect": r, "md": kept_md,
                           "raw": raw_all, "size_key": size_key})

        for t in tabs:
            rows = t["rows"]
            for row in rows:
                for c in row:
                    if c:
                        out_words += words_of(str(c))
            trect = pymupdf.Rect(t["bbox"])
            vtext = vector_items_inside(page_drawings, trect) > VECTOR_TEXT_ITEMS
            blocks.append({"kind": "table", "rect": trect, "rows": rows, "vector_text": vtext,
                           "cells": t["cells"]})
        for f in figs:
            blocks.append({"kind": "fig", "rect": f["rect"], "fig": f})

        blocks = reading_order(blocks)

        # la validacion final se hace contra los ARCHIVOS escritos (ver mas abajo); aqui solo se
        # guardan las palabras del PDF y las de cabecera/pie/numero de pagina (omitidas a proposito)
        pdf_words = [w[4] for w in page_words]
        omitted = Counter()
        for b in text_blocks:
            for ln in b["lines"]:
                raw = "".join(s["text"] for s in ln["spans"]).strip()
                lr = pymupdf.Rect(ln["bbox"])
                in_margin = lr.y1 < pr.height * MARGIN_RATIO or lr.y0 > pr.height * (1 - MARGIN_RATIO)
                if raw and in_margin and (is_page_number(raw) or norm_furniture(raw) in furniture_constant):
                    omitted.update(words_of(raw))
        # pares de palabras contiguas de cada linea del PDF: deben seguir juntas en la salida
        # (detecta celdas que separan "500" de "V" o un codigo de su valor)
        pairs = []
        for b in text_blocks:
            for ln in b["lines"]:
                raw = "".join(s["text"] for s in ln["spans"]).strip()
                lr = pymupdf.Rect(ln["bbox"])
                in_margin = lr.y1 < pr.height * MARGIN_RATIO or lr.y0 > pr.height * (1 - MARGIN_RATIO)
                if in_margin and (is_page_number(raw) or norm_furniture(raw) in furniture_constant):
                    continue
                ws = words_of(raw)
                pairs += list(zip(ws, ws[1:]))
        validation.append((pno, Counter(words_of(" ".join(pdf_words))), omitted, pairs))
        pages_data.append((pno, page, blocks, scanned))
        running_by_page[pno] = running

    # niveles de titulo: tamanos grandes -> ##, siguiente -> ###, negrita -> ####
    big = sorted((s for s in heading_sizes if s), reverse=True)
    level_of = {s: min(2 + i, 4) for i, s in enumerate(big)}
    level_of[0] = 4

    # ------- segunda pasada: escribe paginas
    section = ""
    page_rows = []
    full_doc = []
    pages_lines = []
    needs_ocr = any(s for *_, s in pages_data) or any(
        b["kind"] == "table" and b.get("vector_text") for _, _, bl, _ in pages_data for b in bl)
    if needs_ocr:
        ocr.ensure()
    written_words = {}       # pno -> palabras realmente escritas (para la validacion)
    written_flat = {}        # pno -> texto escrito en una linea (para comprobar el orden)
    external_tables = {}     # pno -> tablas grandes enlazadas en tables/ (no van dentro de la pagina)
    pool = ThreadPoolExecutor(WORKERS)
    jobs, inflight = [], deque()
    for pno, page, blocks, scanned in pages_data:
        pr = page.rect
        pid = f"p{pno:0{pad}d}"
        lines = [f"<!-- {pdf_path.name} · pagina {pno}/{npages} -->", f"# Página {pno}", ""]
        if running_by_page.get(pno):
            lines += ["*Cabecera/pie: " + md_escape_text(" · ".join(running_by_page[pno])) + "*", ""]
        nfig = ntab = 0
        prev_text = ""
        pending = []  # figuras/tablas esperando texto posterior como ancla
        page_heads = []
        if scanned:
            if ocr.ready:
                pix = page.get_pixmap(dpi=OCR_DPI, alpha=False)
                words = ocr.read(Image.frombytes("RGB", (pix.width, pix.height), pix.samples), psm=3)
                conf, doubt = ocr_summary(words)
                ocr_stats["pages"].append((pno, conf, len(words)))
                lines += [f"> ⟨ocr · confianza {conf} %⟩ Página escaneada: texto leído por OCR, "
                          f"puede contener errores. La imagen de la página es la referencia.", ""]
                for para in ocr_lines(words):
                    lines += [join_lines(para.split("\n")), ""]
                if doubt:
                    lines += ["*Lecturas dudosas: " + ", ".join(f"`{d}`" for d in doubt[:40]) + "*", ""]
                prev_text = " ".join(w["text"] for w in words[:20])
            else:
                warnings.append(f"p{pno}: página escaneada sin OCR; queda solo como imagen.")
        for blk in blocks:
            k = blk["kind"]
            if k in ("text", "head"):
                body = join_lines(blk["md"])
                if k == "head":
                    lvl = level_of.get(blk["size_key"], 4)
                    title = re.sub(r"\s+", " ", " ".join(blk["md"]).replace("**", "")).strip()
                    lines += ["#" * lvl + " " + title, ""]
                    section = title
                    headings.append({"page": pno, "level": lvl, "text": title})
                    page_heads.append(title)
                else:
                    lines += [body, ""]
                for it in pending:
                    it["anchor_after"] = short(blk["raw"])
                pending = []
                prev_text = blk["raw"]
            elif k == "table":
                ntab += 1
                tid = f"{pid}-t{ntab}"
                rows = blk["rows"]
                ocr_cells = 0
                if blk.get("vector_text") and ocr.ready and blk.get("cells"):
                    # texto dibujado como trazos: OCR de la tabla ENTERA y cada palabra a la celda
                    # donde cae su centro (en CAD el texto suele salirse del borde de la fila y
                    # recortar celda a celda partiria lineas por la mitad)
                    tclip = blk["rect"] & pr
                    pix = page.get_pixmap(clip=tclip, dpi=OCR_DPI, alpha=False)
                    k = 72 / OCR_DPI
                    ows = ocr.read(Image.frombytes("RGB", (pix.width, pix.height), pix.samples), psm=11)
                    for w in ows:
                        x0, y0, bw, bh = w["box"]
                        w["rect"] = pymupdf.Rect(tclip.x0 + x0 * k, tclip.y0 + y0 * k,
                                                 tclip.x0 + (x0 + bw) * k, tclip.y0 + (y0 + bh) * k)
                    for ri, row in enumerate(rows):
                        for ci, val in enumerate(row):
                            try:
                                cr = blk["cells"][ri][ci]
                            except IndexError:
                                continue
                            if val or val is None or cr is None:   # con texto, o fusionada con otra
                                continue
                            cr = pymupdf.Rect(cr)
                            ws = [w for w in ows if center_in(w["rect"], cr)]
                            if not ws:
                                continue
                            lh = max(1.0, sorted(w["rect"].height for w in ws)[len(ws) // 2] * 0.6)
                            ws.sort(key=lambda w: (round(w["rect"].y0 / lh), w["rect"].x0))
                            conf, _ = ocr_summary(ws)
                            if len(re.sub(r"\W", "", "".join(w["text"] for w in ws))) <= 2 and conf < 95:
                                continue        # simbolo grafico leido como letras ("CO", "T"): no es texto
                            txt = " ".join(w["text"] if w["conf"] >= OCR_DOUBT_CONF else f"{w['text']}(?)"
                                           for w in ws)
                            row[ci] = f"⟨ocr {conf} %⟩{txt}"
                            ocr_cells += 1
                    ocr_stats["cells"] += ocr_cells
                md_tab = table_markdown(rows)
                (out / "tables" / f"{tid}.md").write_text(
                    f"<!-- {tid} · {pdf_path.name} · pagina {pno} · seccion: {section or '-'} -->\n\n{md_tab}\n",
                    encoding="utf-8")
                with open(out / "tables" / f"{tid}.csv", "w", newline="", encoding="utf-8-sig") as fh:
                    csv.writer(fh).writerows([[("" if c is None else str(c)) for c in r] for r in rows])
                pos = position_label(blk["rect"], pr)
                timg = None
                if blk.get("vector_text"):
                    # parte del texto es trazo vectorial (CAD): la imagen es la referencia fiel
                    clip = pymupdf.Rect(blk["rect"].x0 - 2, blk["rect"].y0 - 2,
                                        blk["rect"].x1 + 2, blk["rect"].y1 + 2) & pr
                    pix = page.get_pixmap(clip=clip, dpi=max(dpi, VECTOR_RENDER_DPI), alpha=False)
                    data, ext, *_ = encode_best(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
                    timg = f"images/{tid}.{ext}"
                    (out / timg).write_bytes(data)
                    if ocr_cells:
                        note = (f"{ocr_cells} celdas completadas por OCR (marcadas ⟨ocr⟩, verifícalas "
                                f"con la imagen)")
                    else:
                        note = "las celdas vacías pueden tener contenido: consulta la imagen"
                    lines += [f"![{tid}](../{timg})",
                              f"*⚠ {tid}: parte del texto de esta tabla está dibujado como trazos, "
                              f"no como texto; {note}.*"]
                    warnings.append(f"p{pno}: tabla {tid} con texto en trazos vectoriales; imagen en {timg}"
                                    + (f", {ocr_cells} celdas por OCR." if ocr_cells else ", sin OCR."))
                if len(rows) <= INLINE_TABLE_MAX_ROWS:
                    lines += [f"<!-- {tid} · {pos} -->", md_tab, ""]
                else:
                    lines += [f"> **Tabla {tid}** ({len(rows)} filas) → [tables/{tid}.md](../tables/{tid}.md)", ""]
                    external_tables.setdefault(pno, []).append(md_tab)
                it = {"id": tid, "type": "table", "page": pno, "bbox": rect_tuple(blk["rect"]),
                      "position": pos, "section": section, "anchor_before": short(prev_text),
                      "anchor_after": "", "file": f"tables/{tid}.md", "csv": f"tables/{tid}.csv",
                      "rows": len(rows), "cols": max((len(r) for r in rows), default=0),
                      "md": f"pages/{pid}.md", "image": timg}
                items.append(it)
                pending.append(it)
            else:
                f = blk["fig"]
                nfig += 1
                fid = f"{pid}-f{nfig}"
                pos = "pagina completa" if f["background"] else position_label(f["rect"], pr)
                labels = [re.sub(r"\s+", " ", x).strip() for x in f["labels"]]
                # el render se hace aqui (PyMuPDF no admite hilos); WebP y OCR van al pool
                img, orig, oext, origin = figure_image(doc, page, f, dpi)
                # OCR de la imagen: texto dentro de fotos/planos raster o dibujos sin texto nativo
                want = (ocr.ready and not scanned and min(img.size) >= OCR_FIG_MIN_PX and not f["background"]
                        and (f["kind"] == "raster" or ocr.mode == "todo" or not labels))
                native = {w.lower() for x in labels for w in x.split()}
                it = {"id": fid, "type": "figure", "page": pno, "bbox": rect_tuple(f["rect"]),
                      "position": pos, "kind": f["kind"], "origin": origin, "px": None,
                      "image_type": None, "format": None, "bytes": None,
                      "section": section, "anchor_before": short(prev_text), "anchor_after": "",
                      "labels": labels, "file": None, "md": f"pages/{pid}.md",
                      "ocr_text": "", "ocr_conf": 0, "ocr_doubtful": [], "ocr_paragraphs": [],
                      "description": "", "repeated": False}
                fu = pool.submit(figure_job, img, orig, oext, ocr, want, native)
                jobs.append((it, fu))
                inflight.append(fu)
                del img, orig
                # no acumular mas imagenes en memoria de las que el pool puede procesar
                while len(inflight) > WORKERS * 3:
                    inflight.popleft().result()
                lines += [it, ""]          # se resuelve al final (puede ser decorativa repetida)
                items.append(it)
                pending.append(it)
        first = next((b["raw"] for b in blocks if b["kind"] in ("text", "head")), "")
        pages_lines.append((pno, pid, lines))
        page_rows.append({"pno": pno, "pid": pid, "tokens": 0, "figs": nfig,
                          "tabs": ntab, "heads": page_heads, "first": short(first, 60)})

    # ------- figuras: recoge WebP + OCR del pool EN ORDEN (nombres y duplicados deterministas)
    file_pages = {}
    try:
        for it, fu in jobs:
            res = fu.result()
            h = hashlib.sha1(res["data"]).hexdigest()
            if h in hashes:
                name = hashes[h]
                it["origin"] += " (repetida)"
            else:
                name = f"{it['id']}.{res['ext']}"
                (out / "images" / name).write_bytes(res["data"])
                hashes[h] = name
            words = res["ocr_words"]
            if words:
                ocr_stats["figures"] += 1
            conf, doubt = ocr_summary(words)
            it.update({"file": f"images/{name}", "px": res["px"], "image_type": res["kind_img"],
                       "format": res["format"], "bytes": len(res["data"]),
                       "ocr_text": ocr_compact(words), "ocr_conf": conf, "ocr_doubtful": doubt,
                       "ocr_paragraphs": ocr_lines(words) if is_running_text(words) else []})
            file_pages.setdefault(it["file"], set()).add(it["page"])
    finally:
        pool.shutdown(wait=True)

    # ------- imagenes decorativas repetidas (logos, bandas): una vez en el INDICE
    rep_min = max(REPEAT_MIN_PAGES, round(npages * 0.05))
    repeated_files = {f for f, ps in file_pages.items() if len(ps) >= rep_min}
    for it in items:
        if it["type"] == "figure" and it["file"] in repeated_files and not it["labels"]:
            it["repeated"] = True
    for (pno, pid, lines), row in zip(pages_lines, page_rows):
        txt_lines = []
        for x in lines:
            if isinstance(x, dict):
                if x["repeated"]:
                    continue
                lab = (" · etiquetas: " + md_escape_text(" | ".join(x["labels"]))) if x["labels"] else ""
                if x["ocr_text"] and not x["ocr_paragraphs"]:
                    lab += f" · ⟨ocr {x['ocr_conf']} %⟩: {md_escape_text(x['ocr_text'])}"
                txt_lines += [f"![{x['id']}](../{x['file']})", f"*{x['id']} · {x['position']}{lab}*"]
                if x["ocr_paragraphs"]:
                    txt_lines += ["", f"> ⟨ocr · confianza {x['ocr_conf']} %⟩ Texto leído de la imagen {x['id']}:"]
                    for para in x["ocr_paragraphs"]:
                        txt_lines += [">", "> " + para.replace("\n", "\n> ")]
                if x["ocr_doubtful"]:
                    txt_lines.append("*Lecturas dudosas: " + ", ".join(f"`{d}`" for d in x["ocr_doubtful"][:30]) + "*")
            else:
                txt_lines.append(x)
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(txt_lines)).rstrip() + "\n"
        (out / "pages" / f"{pid}.md").write_text(text, encoding="utf-8")
        # lo que de verdad queda escrito para esta pagina: su .md + sus tablas enlazadas aparte
        # (lo leido por OCR no cuenta: no es texto original del PDF)
        plain = strip_scaffold(strip_ocr(text + "\n" + "\n".join(external_tables.get(pno, []))))
        written_words[pno] = Counter(words_of(md_plain(plain)))
        written_flat[pno] = " " + " ".join(words_of(md_plain(plain).replace("|", " "))) + " "
        full_doc.append(text)
        row["tokens"] = est_tokens(text)
        row["figs"] = sum(1 for x in lines if isinstance(x, dict) and not x["repeated"])

    # ------- validacion
    total = missing_total = 0
    dup_total, dup_lines = 0, []
    val_lines = []
    pair_total = pair_bad = 0
    pair_lines = []
    for pno, pdf_c, omitted_c, pairs in validation:
        flat = written_flat.get(pno, "")
        bad = [f"{a} {c}" for a, c in pairs if f" {a} {c} " not in flat]
        pair_total += len(pairs)
        pair_bad += len(bad)
        if bad:
            pair_lines.append(f"- p{pno}: " + ", ".join(f"`{x}`" for x in bad[:10]))
        miss = pdf_c - (written_words.get(pno, Counter()) + omitted_c)
        t = sum(pdf_c.values())
        m = sum(miss.values())
        total += t
        missing_total += m
        if m:
            val_lines.append(f"- p{pno}: {m} de {t} palabras no localizadas → "
                             + ", ".join(f"`{w}`×{c}" if c > 1 else f"`{w}`" for w, c in miss.most_common(15)))
        # palabras del PDF que salen MAS veces que en el PDF: texto duplicado
        extra = written_words.get(pno, Counter()) - pdf_c
        extra = Counter({w: c for w, c in extra.items() if w in pdf_c})
        if extra:
            dup_total += sum(extra.values())
            dup_lines.append(f"- p{pno}: " + ", ".join(f"`{w}`×{c}" if c > 1 else f"`{w}`"
                                                      for w, c in extra.most_common(15)))
    coverage = 100.0 if total == 0 else 100 * (total - missing_total) / total

    broken = [it["file"] for it in items if not (out / it["file"]).exists()]
    val = [f"# Validación · {pdf_path.name}", "",
           f"- Cobertura de palabras: **{coverage:.2f} %** ({total - missing_total}/{total})",
           f"- Palabras duplicadas: **{dup_total}**",
           f"- Orden: pares de palabras contiguas que se separan: **{pair_bad}** de {pair_total}",
           f"- Referencias rotas: **{len(broken)}**" + (": " + ", ".join(broken) if broken else ""),
           f"- Figuras: {sum(1 for i in items if i['type'] == 'figure')} · "
           f"Tablas: {sum(1 for i in items if i['type'] == 'table')}", ""]
    img_files = list((out / "images").glob("*"))
    img_bytes = sum(p.stat().st_size for p in img_files)
    fmt_count = Counter(it.get("format", "") for it in items if it["type"] == "figure" and "(repetida)" not in it.get("origin", ""))
    val += [f"- Imágenes: {len(img_files)} archivos · {img_bytes / 1048576:.1f} MB · "
            + " · ".join(f"{k}: {v}" for k, v in fmt_count.most_common() if k), ""]
    val += ["## OCR", ""]
    if ocr.mode == "no":
        val += ["- Desactivado (`--ocr no`).", ""]
    elif not ocr.ready:
        val += ["- Tesseract no disponible: no se ha hecho OCR.", ""]
    else:
        val += [f"- Motor: {ocr.version} · idiomas: `{ocr.langs}` · modo: {ocr.mode}",
                f"- Páginas escaneadas leídas: {len(ocr_stats['pages'])}"
                + (" (" + ", ".join(f"p{p} {c} %" for p, c, _ in ocr_stats["pages"]) + ")" if ocr_stats["pages"] else ""),
                f"- Figuras con texto leído por OCR: {ocr_stats['figures']}",
                f"- Celdas de tabla completadas por OCR: {ocr_stats['cells']}",
                "- Todo lo leído por OCR va marcado `⟨ocr⟩` con su confianza: no es texto original del PDF.", ""]
    if pair_lines:
        val += ["## Palabras contiguas que se separan", "",
                "Iban seguidas en una línea del PDF y en la salida no (suele ser una tabla que reparte una "
                "expresión en dos celdas: un valor y su unidad, un código y su significado). Comprueba en el "
                "PDF que la asociación se entiende; si es una columna real de la tabla, es correcto.", ""] + pair_lines + [""]
    if dup_lines:
        val += ["## Palabras duplicadas por página", "",
                "Salen en la salida más veces que en el PDF (texto repetido en el texto y en una tabla, "
                "o dos veces en una tabla). Revisa la página y deja cada texto una sola vez.", ""] + dup_lines + [""]
    if val_lines:
        val += ["## Palabras no localizadas por página", "",
                "Se comparan las palabras del PDF con lo que de verdad queda escrito en `pages/` y "
                "`tables/` (cabeceras, pies y números de página se omiten a propósito y no cuentan). "
                "Cada palabra listada falta en la salida: revisa la página contra el PDF.", ""] + val_lines + [""]
    if warnings:
        val += ["## Avisos", ""] + [f"- {w}" for w in warnings] + [""]
    (out / "_validacion.md").write_text("\n".join(val), encoding="utf-8")

    # ------- leyenda de glifos de fuentes de pictogramas: una imagen de cada uno
    sym_items = []
    for (font, g), e in sorted(symbols.items(), key=lambda kv: -kv[1]["count"]):
        r = pymupdf.Rect(e["bbox"])
        clip = pymupdf.Rect(r.x0 - 1.5, r.y0 - 1.5, r.x1 + 1.5, r.y1 + 1.5) & doc[e["page"] - 1].rect
        name = f"images/glifo-{re.sub(r'[^A-Za-z0-9]+', '', font)[:24]}-{'-'.join(str(ord(c)) for c in g)}"
        try:
            pix = doc[e["page"] - 1].get_pixmap(clip=clip, dpi=600, alpha=False)
            data, ext, *_ = encode_best(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
            (out / f"{name}.{ext}").write_bytes(data)
            img = f"{name}.{ext}"
        except Exception:
            img = None
        sym_items.append({"mark": f"{SYM_L}{g}{SYM_R}", "font": font, "count": e["count"],
                          "first_page": e["page"], "image": img, "meaning": ""})
    if sym_items:
        with open(out / "_validacion.md", "a", encoding="utf-8") as fh:
            fh.write("## Símbolos gráficos\n\n"
                     f"- {len(sym_items)} glifos de fuentes de símbolos ({', '.join(sorted(symbol_fonts))}) "
                     "marcados `⟦x⟧`: no son letras. Leyenda e imágenes en INDICE.md (sin describir).\n")

    # ------- refs.md
    refs = [f"# Referencias cruzadas · {pdf_path.name}", "",
            "| id | tipo | pág | posición | sección | texto anterior | archivo |",
            "|---|---|---:|---|---|---|---|"]
    for it in items:
        if it.get("repeated"):
            continue
        refs.append(f"| {it['id']} | {'figura' if it['type'] == 'figure' else 'tabla'} | {it['page']} | "
                    f"{it['position']} | {cell(short(it['section'], 40)) or '-'} | "
                    f"{cell(short(it['anchor_before'], 50)) or '-'} | [{it['file']}]({it['file']}) |")
    (out / "refs.md").write_text("\n".join(refs) + "\n", encoding="utf-8")

    # ------- manifest.json
    meta = doc.metadata or {}
    manifest = {
        "source": pdf_path.name,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "pages": npages,
        "page_size_pt": [round(doc[0].rect.width, 1), round(doc[0].rect.height, 1)] if npages else None,
        "pdf_metadata": {k: v for k, v in meta.items() if v},
        "body_font_size": body_size,
        "furniture": sorted(furniture_seen.values()),
        "symbols": sym_items,
        "headings": headings,
        "items": items,
        "coverage_pct": round(coverage, 2),
        "ocr": {"engine": ocr.version if ocr.ready else None, "languages": ocr.langs, "mode": ocr.mode,
                "scanned_pages": [{"page": p, "conf": c, "words": n} for p, c, n in ocr_stats["pages"]],
                "figures": ocr_stats["figures"], "table_cells": ocr_stats["cells"],
                "marker": "⟨ocr⟩ = texto leido por OCR (no original); conf = confianza media %"},
        "warnings": warnings,
        "coords": "bbox en puntos PDF [x0,y0,x1,y1], origen arriba-izquierda",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    # ------- INDICE.md
    title = meta.get("title") or (headings[0]["text"] if headings else pdf_path.stem)
    total_tokens = sum(r["tokens"] for r in page_rows)
    idx = [f"# {title}", "",
           f"Fuente: `{pdf_path.name}` · {npages} páginas · "
           f"{sum(r['figs'] for r in page_rows)} figuras · {sum(r['tabs'] for r in page_rows)} tablas · "
           f"~{total_tokens:,} tokens de texto en total · cobertura {coverage:.2f} %".replace(",", "."),
           "",
           "> **Para la IA:** elige las páginas con el *Contenido* (cada capítulo indica su rango) y lee "
           "solo esas `pages/pNNN.md`. Si no basta, `paginas.md` resume cada página en una línea, o busca "
           "con grep en `pages/`: primero las páginas con coincidencias en texto nativo y después las que "
           "solo coinciden en líneas `⟨ocr⟩`. Texto literal del PDF: no lo reescribas. `⟨ocr N %⟩` = leído por OCR, puede tener "
           "errores. Abre una imagen solo si hace falta. Cita siempre página e id.",
           ""]
    if sym_items:
        idx += ["## Símbolos gráficos", "",
                "`⟦x⟧` es un dibujo de una fuente de símbolos (punto, flecha, ≥, ≤…), **no la letra x**. "
                "Su significado está en la imagen del glifo y en la leyenda del propio PDF.", "",
                "| marca | significado | veces | 1.ª pág. | imagen |", "|---|---|---:|---:|---|"]
        for s in sym_items:
            im = f"[{Path(s['image']).name}]({s['image']})" if s["image"] else "—"
            idx.append(f"| `{s['mark']}` | (sin describir) | {s['count']} | {s['first_page']} | {im} |")
        idx.append("")
    if furniture_seen:
        idx += ["**Cabecera/pie repetido (omitido en las páginas):** "
                + " · ".join(f"«{v}»" for v in sorted(furniture_seen.values())), ""]
    rep_imgs = Counter(it["file"] for it in items if it.get("repeated"))
    if rep_imgs:
        idx += ["**Imágenes decorativas repetidas (omitidas en las páginas, ver manifest):** "
                + " · ".join(f"[{Path(f).name}]({f}) ×{c}" for f, c in rep_imgs.most_common()), ""]
    # indice: solo titulos de verdad (no DANGER/NOTE repetidos ni negritas sueltas)
    freq = Counter(h["text"].lower() for h in headings)
    toc_levels = {2, 3} if any(h["level"] <= 3 for h in headings) else {4}
    toc, last = [], None
    for h in headings:
        # capitulos numerados ("8 Equipo", "8.1 Panel") entran aunque usen la letra del cuerpo
        num = re.match(r"^(\d{1,3}(?:\.\d{1,3})?)\s+[^\W\d_]", h["text"])
        if not (h["level"] in toc_levels or num) or freq[h["text"].lower()] > TOC_MAX_REPEAT:
            continue
        if (h["text"], h["page"]) == last:
            continue
        last = (h["text"], h["page"])
        h = dict(h, depth=(1 + num.group(1).count(".")) if num else h["level"] - min(toc_levels))
        toc.append(h)
    if toc:
        # rango de cada capitulo: hasta la pagina anterior al siguiente del mismo nivel o superior
        idx += ["## Contenido", ""]
        for i, h in enumerate(toc):
            nxt = next((g["page"] for g in toc[i + 1:] if g["depth"] <= h["depth"] and g["page"] > h["page"]),
                       npages + 1)
            end = max(h["page"], nxt - 1)
            rng = f"p{h['page']}" if end == h["page"] else f"p{h['page']}–{end}"
            idx.append(f"{'  ' * h['depth']}- {short(h['text'], 70)} → {rng}")
        idx.append("")
    # mapa de paginas (una linea por pagina) en archivo aparte: en un manual grande es
    # ~70 % del indice y casi nunca hace falta entero
    first_toc = {}
    for h in toc:
        first_toc.setdefault(h["page"], h["text"])
    ptab = [f"Archivo: `pages/p{'N' * pad}.md`. fig/tab = figuras y tablas propias de la página.",
            "", "| pág | ~tok | fig | tab | contenido |", "|---:|---:|---:|---:|---|"]
    for r in page_rows:
        topic = first_toc.get(r["pno"]) or r["first"]
        ptab.append(f"| {r['pno']} | {r['tokens']} | {r['figs'] or ''} | {r['tabs'] or ''} | "
                    f"{cell(short(topic, 50)) or '—'} |")
    (out / "paginas.md").write_text("\n".join([f"# Páginas · {pdf_path.name}", ""] + ptab) + "\n",
                                    encoding="utf-8")
    if not toc or npages <= INDEX_INLINE_PAGES:
        idx += ["## Páginas", ""] + ptab + [""]
    else:
        idx += [f"Mapa página a página ({npages} líneas): [paginas.md](paginas.md)", ""]
    if warnings:
        idx += [f"**Avisos de la conversión:** {len(warnings)}, ver [_validacion.md](_validacion.md).", ""]
    (out / "INDICE.md").write_text("\n".join(idx), encoding="utf-8")

    if completo:
        (out / "documento-completo.md").write_text("\n---\n\n".join(full_doc), encoding="utf-8")

    doc.close()
    return {"out": out, "pages": npages, "figs": sum(r["figs"] for r in page_rows),
            "tabs": sum(r["tabs"] for r in page_rows), "coverage": coverage,
            "tokens": total_tokens, "warnings": warnings, "broken": broken}


def main():
    ap = argparse.ArgumentParser(description="PDF (digital, escaneado o mixto) -> Markdown optimizado para cualquier IA")
    ap.add_argument("ruta", help="PDF o carpeta con PDFs")
    ap.add_argument("--out", default=None, help="carpeta de salida (por defecto ./output junto a input)")
    ap.add_argument("--dpi", type=int, default=150, help="resolucion de figuras renderizadas (150; planos vectoriales min. 200)")
    ap.add_argument("--completo", action="store_true", help="genera tambien documento-completo.md")
    ap.add_argument("--ocr", choices=("auto", "no", "todo"), default="auto",
                    help="auto: paginas escaneadas, imagenes y texto en trazos; todo: tambien dibujos con texto; no: sin OCR")
    ap.add_argument("--idiomas", default="spa+eng",
                    help="idiomas OCR de Tesseract unidos por + (spa, eng, fra, deu, ita, por...). Por defecto spa+eng")
    ap.add_argument("--motor", choices=("pymupdf", "libre"), default=MOTOR,
                    help="pymupdf (AGPL) o libre: pdfplumber + pypdfium2 (MIT/Apache, uso comercial sin publicar codigo)")
    a = ap.parse_args()

    src = Path(a.ruta)
    pdfs = sorted(src.glob("*.pdf")) + sorted(src.glob("*.PDF")) if src.is_dir() else [src]
    pdfs = list(dict.fromkeys(pdfs))
    if not pdfs or not all(p.exists() for p in pdfs):
        raise SystemExit(f"No encuentro PDFs en: {src}")
    out_root = Path(a.out) if a.out else (src if src.is_dir() else src.parent).parent / "output"

    if not re.fullmatch(r"[a-z_]{3,}(\+[a-z_]{3,})*", a.idiomas):
        raise SystemExit("--idiomas debe ser como 'spa+eng' (codigos de Tesseract unidos por +)")
    ocr = OCR(a.idiomas, a.ocr, [])
    if a.ocr != "no":
        print(f"OCR: {ocr.version or 'Tesseract no encontrado (se intentara instalar si hace falta)'} · idiomas {ocr.langs}")
    for p in pdfs:
        print(f"→ {p.name}")
        r = convert(p, out_root, a.dpi, a.completo, ocr)
        print(f"  {r['pages']} págs · {r['figs']} figuras · {r['tabs']} tablas · "
              f"~{r['tokens']} tokens · cobertura {r['coverage']:.2f} %")
        print(f"  salida: {r['out']}")
        for w in r["warnings"]:
            print(f"  aviso: {w}")
        if r["broken"]:
            print(f"  REFERENCIAS ROTAS: {r['broken']}")


if __name__ == "__main__":
    main()
