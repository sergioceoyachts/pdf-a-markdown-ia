"""
motor_libre.py - Motor PDF con licencias permisivas para pdf_to_md.py.

Sustituye a PyMuPDF (AGPL) imitando SOLO la parte de su API que usa pdf_to_md.py:
    Rect, Point, Pixmap, csRGB, open() -> Document -> Page
    Page.rect, get_text("dict"|"words"), get_drawings(), cluster_drawings(),
    find_tables(), get_image_info(), get_pixmap()
    Document.extract_image(), metadata, needs_pass

Librerias (todas gratis y de uso comercial libre, sin obligacion de publicar codigo):
    pdfplumber / pdfminer.six  (MIT)          texto, fuentes, posiciones, dibujos, tablas
    pypdfium2 / PDFium         (Apache-2.0 / BSD-3)  renderizado y extraccion de imagenes

Coordenadas: como PyMuPDF, origen arriba-izquierda de la CropBox, en puntos, pagina ya rotada.
"""
from __future__ import annotations

import io
import math
import re
import subprocess
import sys

# ----------------------------------------------------------------- dependencias
def _ensure(mod, pkg):
    try:
        return __import__(mod)
    except ImportError:
        print(f"Instalando {pkg} (solo la primera vez)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pkg])
        import importlib
        import site
        importlib.invalidate_caches()
        try:
            if sys.prefix == sys.base_prefix and site.ENABLE_USER_SITE:
                us = site.getusersitepackages()
                if us not in sys.path:
                    site.addsitedir(us)
        except Exception:
            pass
        try:
            return __import__(mod)
        except ImportError:
            raise SystemExit(f"{pkg} se ha instalado, pero este Python no lo ve todavia. "
                             "Vuelve a ejecutar el mismo comando.")


pdfplumber = _ensure("pdfplumber", "pdfplumber")
pdfium = _ensure("pypdfium2", "pypdfium2")
import pypdfium2.raw as pdfium_c                       # noqa: E402
from pdfminer.layout import (LTAnno, LTChar, LTFigure,  # noqa: E402
                             LTTextBox, LTTextLine)
from PIL import Image                                  # noqa: E402

NAME = "libre (pdfplumber + pypdfium2)"
KEEP_OBJECTS_BUDGET = 300000  # tope total en memoria (~300 MB)
KEEP_OBJECTS_MAX = 15000    # paginas con mas objetos no se guardan en memoria (planos enormes)
MAX_CELL_WORDS = 35        # mas palabras en una celda = recuadro de texto, no tabla
LAPARAMS = {"line_margin": 0.5, "char_margin": 2.0, "word_margin": 0.1,
            "boxes_flow": 0.5, "all_texts": True}


# ----------------------------------------------------------------- geometria
class Point:
    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)


class Rect:
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, *a):
        if len(a) == 1:
            a = tuple(a[0])
        if len(a) == 0:
            a = (0, 0, 0, 0)
        self.x0, self.y0, self.x1, self.y1 = (float(v) for v in a[:4])

    # --- como PyMuPDF
    width = property(lambda s: max(0.0, s.x1 - s.x0))
    height = property(lambda s: max(0.0, s.y1 - s.y0))
    is_empty = property(lambda s: s.x0 >= s.x1 or s.y0 >= s.y1)
    tl = property(lambda s: Point(s.x0, s.y0))
    br = property(lambda s: Point(s.x1, s.y1))

    def get_area(self):
        return 0.0 if self.is_empty else (self.x1 - self.x0) * (self.y1 - self.y0)

    def __iter__(self):
        return iter((self.x0, self.y0, self.x1, self.y1))

    def __len__(self):
        return 4

    def __getitem__(self, i):
        return (self.x0, self.y0, self.x1, self.y1)[i]

    def __repr__(self):
        return f"Rect({self.x0:.1f}, {self.y0:.1f}, {self.x1:.1f}, {self.y1:.1f})"

    def __eq__(self, o):
        try:
            return tuple(self) == tuple(o)
        except TypeError:
            return False

    def __pos__(self):
        return Rect(self)

    def __and__(self, o):
        o = o if isinstance(o, Rect) else Rect(o)
        return Rect(max(self.x0, o.x0), max(self.y0, o.y0), min(self.x1, o.x1), min(self.y1, o.y1))

    def __or__(self, o):
        if isinstance(o, Point):
            return Rect(min(self.x0, o.x), min(self.y0, o.y), max(self.x1, o.x), max(self.y1, o.y))
        o = o if isinstance(o, Rect) else Rect(o)
        if o.is_empty:
            return Rect(self)
        if self.is_empty:
            return Rect(o)
        return Rect(min(self.x0, o.x0), min(self.y0, o.y0), max(self.x1, o.x1), max(self.y1, o.y1))

    def __ior__(self, o):
        """r |= otro: en el sitio, como PyMuPDF (el script cuenta con que la figura crezca)."""
        u = self | o
        self.x0, self.y0, self.x1, self.y1 = u.x0, u.y0, u.x1, u.y1
        return self

    def __hash__(self):
        return id(self)

    def intersects(self, o):
        o = o if isinstance(o, Rect) else Rect(o)
        if self.is_empty or o.is_empty:
            return False
        return self.x0 < o.x1 and o.x0 < self.x1 and self.y0 < o.y1 and o.y0 < self.y1

    def contains(self, p):
        if isinstance(p, Point):
            return self.x0 <= p.x <= self.x1 and self.y0 <= p.y <= self.y1
        r = p if isinstance(p, Rect) else Rect(p)
        return self.x0 <= r.x0 and self.y0 <= r.y0 and r.x1 <= self.x1 and r.y1 <= self.y1


# ----------------------------------------------------------------- imagenes
class _Colorspace:
    def __init__(self, n):
        self.n = n


csRGB = _Colorspace(3)


class Pixmap:
    """Pixmap minimo: Pixmap(doc, xref) | Pixmap(csRGB, pix) | page.get_pixmap()."""

    def __init__(self, a, b=None):
        if isinstance(a, Document):
            img = a._image_pil(b)
        elif isinstance(a, _Colorspace):
            img = b.img.convert("RGB")
        elif isinstance(a, Pixmap):              # Pixmap(pix, mask): sin smask en este motor
            img = a.img
        else:
            img = a
        self._set(img)

    def _set(self, img):
        self.img = img
        self.width, self.height = img.size
        n = {"L": 1, "1": 1, "RGB": 3, "RGBA": 3, "P": 3, "CMYK": 4}.get(img.mode, 3)
        self.colorspace = _Colorspace(n)

    @property
    def samples(self):
        return self.img.convert("RGB").tobytes()

    def tobytes(self, fmt="png"):
        buf = io.BytesIO()
        self.img.save(buf, "PNG")
        return buf.getvalue()


# ----------------------------------------------------------------- tablas
class _Row:
    def __init__(self, row, off):
        ox, oy = off
        self.cells = [None if c is None else (c[0] - ox, c[1] - oy, c[2] - ox, c[3] - oy) for c in row.cells]
        b = row.bbox
        self.bbox = (b[0] - ox, b[1] - oy, b[2] - ox, b[3] - oy)


class _Table:
    def __init__(self, t, off):
        ox, oy = off
        self._t = t
        b = t.bbox
        self.bbox = (b[0] - ox, b[1] - oy, b[2] - ox, b[3] - oy)
        self.rows = [_Row(r, off) for r in t.rows]
        self.row_count = len(self.rows)
        self.col_count = max((len(r.cells) for r in self.rows), default=0)

    def extract(self):
        return self._t.extract()


class _TableFinder:
    def __init__(self, tables):
        self.tables = tables


# ----------------------------------------------------------------- pagina
def _clean_font(name):
    if isinstance(name, bytes):
        name = name.decode("latin-1", "replace")
    return re.sub(r"^[A-Z]{6}\+", "", name or "")


class Page:
    def __init__(self, doc, index):
        self.parent = doc
        self.number = index
        self._pl = doc._pl.pages[index]
        cb = self._pl.cropbox
        self._off = (cb[0], cb[1])
        self.rect = Rect(0, 0, cb[2] - cb[0], cb[3] - cb[1])
        self._text = None        # (blocks, words) en cache
        self._drawings = None
        self._keep_objects = False   # objetos de pdfplumber guardados tras el 1.er analisis
        self._n_obj = 0
        self._used = False           # ya se buscaron tablas/dibujos: se puede soltar

    # --- conversion de coordenadas de pdfplumber a las de la pagina
    def _r(self, x0, top, x1, bottom):
        ox, oy = self._off
        return (x0 - ox, top - oy, x1 - ox, bottom - oy)

    def _heavy(self):
        """El documento solo guarda en memoria el analisis de la ultima pagina usada."""
        self.parent._touch(self.number)
        return self._pl

    # --- texto
    def _build_text(self):
        pl = self._heavy()
        layout = pl.layout
        H = pl.mediabox[3] - pl.mediabox[1]      # pdfminer: y hacia arriba sobre la MediaBox rotada
        mx0, my0 = pl.mediabox[0], pl.mediabox[1]

        def box(o):
            return self._r(o.x0 + mx0, H - o.y1 + my0, o.x1 + mx0, H - o.y0 + my0)

        boxes = []

        def walk(obj):
            for o in obj:
                if isinstance(o, LTTextBox):
                    boxes.append(o)
                elif isinstance(o, LTFigure):
                    walk(o)
        walk(layout)

        blocks, words = [], []
        seen = {}        # (letra, x, y) -> posiciones: la "falsa negrita" dibuja cada letra
                         # dos veces casi en el mismo sitio (desplazada < 1/4 de su anchura)

        W, Hp = self.rect.width, self.rect.height

        def dup(t, bb):
            # fuera de la hoja (texto colocado mas alla del borde): no se ve, como en PyMuPDF
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            if not (0 <= cx <= W and 0 <= cy <= Hp):
                return True
            if t.isspace():
                return False
            x, y = round(bb[0]), round(bb[1])
            tol_x = max(0.05, 0.25 * (bb[2] - bb[0]))
            tol_y = max(0.05, 0.25 * (bb[3] - bb[1]))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for px, py in seen.get((t, x + dx, y + dy), ()):
                        if abs(px - bb[0]) <= tol_x and abs(py - bb[1]) <= tol_y:
                            return True
            seen.setdefault((t, x, y), []).append((bb[0], bb[1]))
            return False

        # texto girado: se recoge de TODA la pagina (pdfminer deja sus espacios fuera de los
        # bloques de texto y sin ellos "4 x 81,5 = 326" se leeria "4x81,5=326")
        rotated = []

        def walk_rot(obj):
            for o in obj:
                if isinstance(o, LTChar):
                    if not o.upright:
                        rotated.append(o)
                elif isinstance(o, (LTTextBox, LTTextLine, LTFigure)) or type(o).__name__ in (
                        "LTTextGroupLRTB", "LTTextGroupTBRL"):
                    walk_rot(o)
        walk_rot(layout)

        for bno, tb in enumerate(boxes):
            lines = []
            for lno, tl in enumerate(x for x in tb if isinstance(x, LTTextLine)):
                spans, cur = [], None
                wcur, wno = None, 0
                for ch in tl:
                    if isinstance(ch, LTChar):
                        if not ch.upright:          # texto girado (cotas de planos): aparte
                            continue
                        t = ch.get_text()
                        bb = box(ch)
                        if dup(t, bb):
                            continue
                        font = _clean_font(ch.fontname)
                        size = round(ch.size, 2)
                        if cur is None or cur["font"] != font or abs(cur["size"] - size) > 0.05:
                            bold = "bold" in font.lower() or "black" in font.lower() or "heavy" in font.lower()
                            cur = {"text": "", "font": font, "size": size, "flags": 16 if bold else 0,
                                   "bbox": list(bb)}
                            spans.append(cur)
                        cur["text"] += t
                        b = cur["bbox"]
                        cur["bbox"] = [min(b[0], bb[0]), min(b[1], bb[1]), max(b[2], bb[2]), max(b[3], bb[3])]
                        if t.isspace():
                            if wcur:
                                words.append((*wcur["bb"], wcur["t"], bno, lno, wno))
                                wno += 1
                            wcur = None
                        else:
                            if wcur is None:
                                wcur = {"t": "", "bb": list(bb)}
                            wcur["t"] += t
                            w = wcur["bb"]
                            wcur["bb"] = [min(w[0], bb[0]), min(w[1], bb[1]), max(w[2], bb[2]), max(w[3], bb[3])]
                    elif isinstance(ch, LTAnno):
                        t = ch.get_text()
                        if t == "\n":
                            continue
                        if cur is not None:
                            cur["text"] += t
                        if t.isspace() and wcur:
                            words.append((*wcur["bb"], wcur["t"], bno, lno, wno))
                            wno += 1
                            wcur = None
                if wcur:
                    words.append((*wcur["bb"], wcur["t"], bno, lno, wno))
                for s in spans:
                    s["bbox"] = tuple(s["bbox"])
                if spans:
                    lines.append({"bbox": box(tl), "spans": spans, "dir": (1, 0), "wmode": 0})
            if lines:
                blocks.append({"type": 0, "number": bno, "bbox": box(tb), "lines": lines})
        self._rotated_lines(rotated, blocks, words, box, dup, len(boxes))
        self._text = (blocks, words)
        # tablas y dibujos usaran los objetos de la pagina: se sacan ya del analisis hecho
        # (si no, pdfminer volveria a leer la pagina entera) y se suelta el arbol de layout
        self._keep_objects = False
        try:
            n_obj = sum(len(v) for v in pl.objects.values())
            d = self.parent
            if n_obj <= KEEP_OBJECTS_MAX and d._kept_objects + n_obj <= KEEP_OBJECTS_BUDGET:
                self._keep_objects, self._n_obj = True, n_obj
                d._kept_objects += n_obj
        except Exception:
            pass
        if hasattr(pl, "_layout"):
            del pl._layout

    @staticmethod
    def _rotated_lines(chars, blocks, words, box, dup, bno):
        """pdfminer parte el texto girado (p. ej. cotas a 90 grados) en letras sueltas.
        Se agrupa como PyMuPDF: misma direccion y misma linea base, en orden de lectura
        a lo largo de su direccion. Cada linea girada es un bloque propio."""
        groups = {}
        for ch in chars:
            a, b = ch.matrix[0], ch.matrix[1]
            n = math.hypot(a, b) or 1.0
            ux, uy = a / n, b / n                       # direccion de escritura (pdfminer: y arriba)
            ox, oy = ch.matrix[4], ch.matrix[5]          # origen de la letra
            along = ox * ux + oy * uy
            perp = -ox * uy + oy * ux
            ang = round(math.degrees(math.atan2(uy, ux)))
            size = max(n, 0.1)                          # tamano real = escala de la matriz
            groups.setdefault((ang, round(perp / (0.3 * size))), []).append((along, ch, size, (ux, uy)))
        for (ang, _), items in sorted(groups.items(), key=lambda kv: kv[0]):
            items.sort(key=lambda it: it[0])
            runs, run, end = [], [], None
            for along, ch, size, u in items:
                adv = abs(ch.adv) * size if ch.adv else size * 0.5   # adv viene en unidades de fuente
                if run and along - end > 3 * size:          # hueco grande: otra linea
                    runs.append(run)
                    run = []
                run.append((along, ch, size, adv, end))
                end = along + adv
            if run:
                runs.append(run)
            for run in runs:
                text, wds, wcur, bbl = "", [], None, None
                for along, ch, size, adv, prev_end in run:
                    t = ch.get_text()
                    bb = box(ch)
                    if dup(t, bb):
                        continue
                    if prev_end is not None and along - prev_end > 0.25 * size and wcur:
                        wds.append(wcur)
                        wcur = None
                        text += " "
                    if t.isspace():
                        if wcur:
                            wds.append(wcur)
                        wcur = None
                        text += " "
                        continue
                    text += t
                    if wcur is None:
                        wcur = {"t": "", "bb": list(bb)}
                    wcur["t"] += t
                    w = wcur["bb"]
                    wcur["bb"] = [min(w[0], bb[0]), min(w[1], bb[1]), max(w[2], bb[2]), max(w[3], bb[3])]
                    bbl = bb if bbl is None else (min(bbl[0], bb[0]), min(bbl[1], bb[1]),
                                                  max(bbl[2], bb[2]), max(bbl[3], bb[3]))
                if wcur:
                    wds.append(wcur)
                text = " ".join(text.split())
                if not text or bbl is None:
                    continue
                ch0 = run[0][1]
                font = _clean_font(ch0.fontname)
                bold = "bold" in font.lower()
                na = math.hypot(ch0.matrix[0], ch0.matrix[1]) or 1.0
                u = (ch0.matrix[0] / na, ch0.matrix[1] / na)
                span = {"text": text, "font": font, "size": round(run[0][2], 2), "flags": 16 if bold else 0,
                        "bbox": tuple(bbl)}
                blocks.append({"type": 0, "number": bno, "bbox": tuple(bbl),
                               "lines": [{"bbox": tuple(bbl), "spans": [span], "dir": (u[0], -u[1]), "wmode": 0}]})
                for wno, w in enumerate(wds):
                    words.append((*w["bb"], w["t"], bno, 0, wno))
                bno += 1

    def get_text(self, kind="text", sort=False, **kw):
        if self._text is None:
            self._build_text()
        blocks, words = self._text
        if kind == "dict":
            bl = sorted(blocks, key=lambda b: (round(b["bbox"][1], 1), b["bbox"][0])) if sort else blocks
            return {"width": self.rect.width, "height": self.rect.height, "blocks": bl}
        if kind == "words":
            return list(words)
        return "\n".join("".join(s["text"] for s in ln["spans"]) for b in blocks for ln in b["lines"])

    # --- dibujos vectoriales
    def get_drawings(self):
        self._used = True
        if self._drawings is None:
            pl = self._heavy()
            out = []
            for o in pl.rects:
                out.append({"rect": Rect(self._r(o["x0"], o["top"], o["x1"], o["bottom"])), "items": [("re",)]})
            for o in pl.lines:
                out.append({"rect": Rect(self._r(o["x0"], o["top"], o["x1"], o["bottom"])), "items": [("l",)]})
            for o in pl.curves:
                n = max(1, len(o.get("pts") or ()) - 1)
                out.append({"rect": Rect(self._r(o["x0"], o["top"], o["x1"], o["bottom"])), "items": [("c",)] * n})
            self._drawings = out
        return self._drawings

    def cluster_drawings(self, clip=None, drawings=None, x_tolerance=3, y_tolerance=3, final_filter=True):
        """Misma idea que PyMuPDF: une los trazos vecinos (a <= 3 pt) en un rectangulo.
        Union-find con rejilla espacial: lineal aunque haya 100.000 trazos."""
        area = Rect(clip) if clip is not None else self.rect
        if drawings is None:
            drawings = self.get_drawings()
        rs = [d["rect"] for d in drawings
              if d["rect"].x0 >= area.x0 and d["rect"].x1 <= area.x1
              and d["rect"].y0 >= area.y0 and d["rect"].y1 <= area.y1]
        if not rs:
            return []
        # Igual que PyMuPDF: un grupo crece con todo trazo que toque (a <= 3 pt) su rectangulo.
        # Barrido ordenado por x: casi lineal aunque haya decenas de miles de trazos juntos.
        boxes = sorted({(r.x0, r.y0, r.x1, r.y1) for r in rs})
        tx, ty = x_tolerance, y_tolerance
        changed = True
        while changed:
            changed = False
            boxes.sort()
            out, active = [], []
            for b in boxes:
                active = [k for k in active if out[k][2] + tx >= b[0]]
                hit = None
                for k in active:
                    o = out[k]
                    if not (o[2] < b[0] - tx or o[0] > b[2] + tx or o[3] < b[1] - ty or o[1] > b[3] + ty):
                        hit = k
                        break
                if hit is None:
                    out.append(b)
                    active.append(len(out) - 1)
                else:
                    o = out[hit]
                    out[hit] = (min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3]))
                    changed = True
            boxes = out
        groups = {i: b for i, b in enumerate(boxes)}
        out = sorted((Rect(b) for b in set(groups.values())), key=lambda r: (r.y1, r.x0))
        if final_filter:
            out = [r for r in out if r.width > x_tolerance and r.height > y_tolerance]
        return out

    # --- tablas
    def find_tables(self, clip=None, vertical_strategy="lines", horizontal_strategy="lines",
                    snap_tolerance=3, join_tolerance=3, **kw):
        self._used = True
        pl = self._heavy()
        target = pl
        if clip is not None:
            c = Rect(clip) & self.rect
            if c.is_empty:
                return _TableFinder([])
            ox, oy = self._off
            target = pl.crop((c.x0 + ox, c.y0 + oy, c.x1 + ox, c.y1 + oy))
        settings = {"vertical_strategy": vertical_strategy, "horizontal_strategy": horizontal_strategy,
                    "snap_tolerance": snap_tolerance, "join_tolerance": join_tolerance}
        try:
            found = [_Table(t, self._off) for t in target.find_tables(settings)]
        except Exception:
            found = []
        return _TableFinder([t for t in found if self._real_table(t)])

    def _real_table(self, t):
        """Descarta rejillas sin contenido (recuadros de un plano, marcos de aviso): una tabla
        de verdad tiene texto en >= 2 filas y >= 2 columnas y en al menos un tercio de sus celdas.
        Lo descartado no se pierde: sale como texto normal."""
        x0, y0, x1, y1 = t.bbox
        words = [w for w in self.get_text("words")
                 if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1]
        cells =[(ri, ci, c) for ri, r in enumerate(t.rows) for ci, c in enumerate(r.cells) if c]
        if not cells:
            return False
        filled = {}
        for w in words:
            cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
            for ri, ci, c in cells:
                if c[0] <= cx <= c[2] and c[1] <= cy <= c[3]:
                    filled[(ri, ci)] = filled.get((ri, ci), 0) + 1
                    break
        rows = {r for r, _ in filled}
        cols = {c for _, c in filled}
        # una "celda" con un parrafo entero es un recuadro de texto (aviso, pasos con vinetas):
        # como tabla perderia su estructura; como texto queda igual que en el PDF
        if max(filled.values(), default=0) > MAX_CELL_WORDS:
            return False
        return len(rows) >= 2 and len(cols) >= 2 and len(filled) >= len(cells) / 3

    # --- imagenes
    def get_image_info(self, xrefs=False, **kw):
        """Imagenes Y sombreados (degradados) segun PDFium, como hace PyMuPDF: los iconos de
        aviso (triangulo ⚠) suelen ser sombreados y pdfplumber no los ve."""
        return [{"bbox": bb, "xref": key, "transform": tr}
                for key, bb, tr in self.parent._pdfium_images(self.number)]

    # --- renderizado (PDFium)
    def get_pixmap(self, clip=None, dpi=72, alpha=False, **kw):
        p = self.parent._pdfium_page(self.number)
        W, H = self.rect.width, self.rect.height
        scale = dpi / 72.0
        crop = (0, 0, 0, 0)
        if clip is not None:
            c = Rect(clip) & self.rect
            crop = (max(0.0, c.x0), max(0.0, H - c.y1), max(0.0, W - c.x1), max(0.0, c.y0))
        bm = p.render(scale=scale, crop=crop, draw_annots=True)
        return Pixmap(bm.to_pil().convert("RGB"))


# ----------------------------------------------------------------- documento
class Document:
    def __init__(self, path):
        self.name = str(path)
        self.needs_pass = False
        try:
            self._pl = pdfplumber.open(path, laparams=LAPARAMS)
            self._pdfium = pdfium.PdfDocument(str(path))
        except Exception as e:
            if "password" in str(e).lower() or "encrypt" in str(e).lower() or type(e).__name__ == "PDFPasswordIncorrect":
                self.needs_pass = True
                self._pl, self._pdfium, self._pages = None, None, []
                return
            raise
        self._pages = [None] * len(self._pl.pages)
        self._img_cache = {}       # pagina -> {clave: (bbox, matriz)}
        self._img_objs = {}        # clave -> objeto imagen de PDFium
        self._img_last = None      # (clave, PIL) ultima imagen decodificada
        self._pdfium_pages = {}
        self._last = None
        self._kept_objects = 0     # objetos guardados entre pasadas (tope KEEP_OBJECTS_BUDGET)

    def _touch(self, i):
        """Libera el analisis (pdfminer) y el render de la pagina anterior: memoria plana
        aunque el manual tenga cientos de paginas."""
        if self._last is not None and self._last != i:
            pg = self._pages[self._last]
            try:
                pp = self._pl.pages[self._last]
                keep = pg is not None and pg._keep_objects and not pg._used
                if not keep:                    # ya usada (o enorme): se suelta
                    pp.flush_cache()
                    if pg is not None and pg._keep_objects:
                        self._kept_objects -= pg._n_obj
                        pg._keep_objects = False
                if hasattr(pp, "_layout"):
                    del pp._layout
            except Exception:
                pass
            if pg is not None:
                pg._drawings = None
        self._last = i

    def _pdfium_page(self, i):
        p = self._pdfium_pages.get(i)
        if p is None:
            if len(self._pdfium_pages) > 4:
                for k in list(self._pdfium_pages)[:-2]:
                    self._pdfium_pages.pop(k)
            p = self._pdfium_pages[i] = self._pdfium[i]
        return p

    def _pdfium_images(self, i):
        """[(clave, bbox, matriz)] de imagenes y sombreados, en coordenadas de la pagina girada
        (las mismas que pdfplumber). Solo las imagenes de paginas sin giro se extraen tal cual
        (clave != 0); el resto se renderiza, que tambien es fiel."""
        if i in self._img_cache:
            return self._img_cache[i]
        res = []
        try:
            p = self._pdfium_page(i)
            rot = p.get_rotation() % 360
            l, b, r, t = p.get_cropbox()
            conv = {0: lambda x, y: (x - l, t - y), 90: lambda x, y: (y - b, x - l),
                    180: lambda x, y: (r - x, y - b), 270: lambda x, y: (t - y, r - x)}[rot]
            kinds = (pdfium_c.FPDF_PAGEOBJ_IMAGE, pdfium_c.FPDF_PAGEOBJ_SHADING)
            for n, obj in enumerate(p.get_objects(filter=kinds, max_depth=15)):
                x0, y0, x1, y1 = obj.get_bounds()
                (ax, ay), (bx, by) = conv(x0, y0), conv(x1, y1)
                bb = (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))
                key, tr = 0, (1, 0, 0, 1, 0, 0)
                if obj.type == pdfium_c.FPDF_PAGEOBJ_IMAGE and rot == 0 and obj.level == 0:
                    m = obj.get_matrix()
                    key, tr = f"{i}:{n}", (m.a, m.b, m.c, m.d, m.e, m.f)
                    self._img_objs[key] = obj
                res.append((key, bb, tr))
        except Exception:
            res = []
        self._img_cache[i] = res
        return res

    def _image_pil(self, key):
        """Imagen a su resolucion original CON su mascara de transparencia aplicada
        (sin ella, un esquema con fondo transparente saldria negro)."""
        hit = self._img_last
        if hit and hit[0] == key:
            return hit[1]
        obj = self._img_objs[key]
        img = obj.get_bitmap(render=True, scale_to_original=True).to_pil()
        if img.mode == "RGBA" and img.getchannel("A").getextrema()[0] == 255:
            img = img.convert("RGB")             # opaca: el canal alfa sobra
        self._img_last = (key, img)
        return img

    def extract_image(self, key):
        obj = self._img_objs[key]
        if self._image_pil(key).mode == "RGBA":  # con transparencia: el original sin mascara no vale
            return {"image": None, "ext": "png", "smask": 0}
        filters = obj.get_filters()
        if filters and filters[-1] == "DCTDecode":
            buf = io.BytesIO()
            obj.extract(buf, fb_format="png")
            return {"image": buf.getvalue(), "ext": "jpeg", "smask": 0}
        # resto (JBIG2, CCITT, Flate...): PNG del mapa de bits; en escaneos de 1 bit,
        # PNG de 1 bit (muy pequeno). encode_best se queda con el menor sin perdida.
        try:
            img = self._image_pil(key)
            if obj.get_metadata().bits_per_pixel == 1:
                img = img.convert("1")
            buf = io.BytesIO()
            img.save(buf, "PNG", optimize=True)
            return {"image": buf.getvalue(), "ext": "png", "smask": 0}
        except Exception:
            return {"image": None, "ext": "png", "smask": 0}

    def __len__(self):
        return len(self._pages)

    def __getitem__(self, i):
        if i < 0:
            i += len(self._pages)
        if self._pages[i] is None:
            self._pages[i] = Page(self, i)
        return self._pages[i]

    def __iter__(self):
        for i in range(len(self._pages)):
            yield self[i]

    @property
    def metadata(self):
        meta = {}
        for k, v in (self._pl.metadata or {}).items():
            if isinstance(v, bytes):
                v = v.decode("utf-8", "replace")
            if isinstance(v, (str, int, float)) and str(v).strip():
                meta[str(k).lower()] = str(v)
        return meta

    def close(self):
        try:
            self._pl.close()
            self._pdfium.close()
        except Exception:
            pass


def open(path):  # noqa: A001  (mismo nombre que pymupdf.open)
    return Document(path)
