"""Minimal PDF writer (no dependency): A4 pages with text, filled rectangles, lines and JPEG images.

Coordinates are in mm from the page's top-left corner. Text uses the standard Helvetica fonts with
WinAnsi encoding (Western European accents); characters outside cp1252 are replaced by "?".
"""
from __future__ import annotations

import zlib

PT = 72 / 25.4          # points per mm
A4 = (210.0, 297.0)

# Helvetica advance widths (1/1000 em) for ASCII 32..126; other characters use an average width
_HELV = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556,
         556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778,
         722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278,
         278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
         556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]


def text_width(s: str, size_pt: float, bold: bool = False) -> float:
    """Approximate width of a text in mm (Helvetica metrics; bold ~6 % wider)."""
    w = sum(_HELV[ord(c) - 32] if 32 <= ord(c) <= 126 else 556 for c in s)
    return w / 1000 * size_pt * (1.06 if bold else 1.0) / PT


def wrap(s: str, width_mm: float, size_pt: float, bold: bool = False) -> list[str]:
    lines, cur = [], ""
    for word in s.split():
        cand = f"{cur} {word}".strip()
        if cur and text_width(cand, size_pt, bold) > width_mm:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    return lines + ([cur] if cur else [])


def _esc(s: str) -> bytes:
    b = s.encode("cp1252", errors="replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return " ".join(f"{int(h[i:i + 2], 16) / 255:.3f}" for i in (0, 2, 4))


class Pdf:
    def __init__(self):
        self.pages: list[list[bytes]] = []
        self.images: list[tuple[bytes, int, int]] = []   # JPEG data, width, height (px)
        self.add_page()

    def add_page(self):
        self.pages.append([])

    def _op(self, s: str | bytes):
        self.pages[-1].append(s.encode("latin-1") if isinstance(s, str) else s)

    @staticmethod
    def _y(y_mm: float) -> float:
        return (A4[1] - y_mm) * PT

    def text(self, x: float, y: float, s: str, size: float = 10, bold: bool = False, color: str = "#000000",
             mono: bool = False):
        """Text whose baseline is at (x, y) mm."""
        font = "F3" if mono else ("F2" if bold else "F1")
        self._op(f"BT /{font} {size:.2f} Tf {_rgb(color)} rg {x * PT:.2f} {self._y(y):.2f} Td (".encode()
                 + _esc(s) + b") Tj ET")

    def rect(self, x: float, y: float, w: float, h: float, fill: str | None = None, stroke: str | None = None,
             line_w: float = 0.2, dash: bool = False):
        ops = [f"{line_w * PT:.2f} w", "[2 1.5] 0 d" if dash else "[] 0 d"]
        if fill:
            ops.append(f"{_rgb(fill)} rg")
        if stroke:
            ops.append(f"{_rgb(stroke)} RG")
        paint = "B" if fill and stroke else ("f" if fill else "S")
        ops.append(f"{x * PT:.2f} {self._y(y + h):.2f} {w * PT:.2f} {h * PT:.2f} re {paint}")
        self._op(" ".join(ops))

    def line(self, x0: float, y0: float, x1: float, y1: float, color: str = "#999999", line_w: float = 0.2):
        self._op(f"[] 0 d {line_w * PT:.2f} w {_rgb(color)} RG {x0 * PT:.2f} {self._y(y0):.2f} m "
                 f"{x1 * PT:.2f} {self._y(y1):.2f} l S")

    def image(self, jpeg: bytes, px_w: int, px_h: int, x: float, y: float, w: float, h: float):
        self.images.append((jpeg, px_w, px_h))
        n = len(self.images)
        self._op(f"q {w * PT:.2f} 0 0 {h * PT:.2f} {x * PT:.2f} {self._y(y + h):.2f} cm /Im{n} Do Q")

    def output(self) -> bytes:
        objs: list[bytes] = []          # object n is objs[n - 1]

        def add(body: bytes) -> int:
            objs.append(body)
            return len(objs)

        def stream(dict_entries: str, data: bytes) -> bytes:
            return f"<< {dict_entries} /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"

        enc = "/Encoding /WinAnsiEncoding"
        f1 = add(f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica {enc} >>".encode())
        f2 = add(f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold {enc} >>".encode())
        f3 = add(f"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold {enc} >>".encode())
        ims = [add(stream(f"/Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB "
                          f"/BitsPerComponent 8 /Filter /DCTDecode", data)) for data, w, h in self.images]
        xobj = " ".join(f"/Im{i + 1} {n} 0 R" for i, n in enumerate(ims))
        res = add(f"<< /Font << /F1 {f1} 0 R /F2 {f2} 0 R /F3 {f3} 0 R >> /XObject << {xobj} >> >>".encode())
        pages_id = len(objs) + 1 + 2 * len(self.pages)        # reserved after the page objects
        kids = []
        for ops in self.pages:
            content = add(stream("/Filter /FlateDecode", zlib.compress(b"\n".join(ops))))
            kids.append(add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {A4[0] * PT:.2f} "
                            f"{A4[1] * PT:.2f}] /Resources {res} 0 R /Contents {content} 0 R >>".encode()))
        add(f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode())
        catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
        out += f"trailer\n<< /Size {len(objs) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)
