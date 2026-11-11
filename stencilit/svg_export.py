"""SVG export (units in mm), compatible with Silhouette Studio and Inkscape.

Text written into the exported files (titles, layer names, comments, swatches, file names) follows
the interface language: English by default, French with lang="fr".
"""
from __future__ import annotations

import contextvars
import io
import json
import math
import zipfile

import cv2
import numpy as np

from .pdf_sheet import Pdf, wrap
from .pipeline import (Result, bgr_hex, layer_stats, positioning, registration_shapes, simulate, simulate_sheet,
                       support_overlap)

CUT = 'fill="none" stroke="#ff0000" stroke-width="0.1"'

# ---------------------------------------------------------------- export language
_LANG = contextvars.ContextVar("stencilit_export_lang", default="en")
_FR = {
    "StencilIt - Silhouette Studio file: one compound path per stencil (openings, sheet outline and marks)":
        "StencilIt - fichier Silhouette Studio : un tracé composé par pochoir (ouvertures, contour de la feuille et repères)",
    "Stencils for Silhouette Studio": "Pochoirs pour Silhouette Studio",
    "Layer": "Couche", "outline": "contours", "colour": "couleur", "material": "matériau", "custom": "personnalisé",
    "blade": "lame", "force": "force", "speed": "vitesse", "passes": "passes",
    "Stencil layer": "Pochoir couche", "Overview of all layers": "Aperçu de toutes les couches",
    "StencilIt - overview (do not cut)": "StencilIt - aperçu (ne pas découper)",
    "Registration dimensions (do not cut)": "Cotes de calage (ne pas découper)",
    "StencilIt stencils": "Pochoirs StencilIt",
    "StencilIt - Inkscape project: one layer per stencil, image and previews as background layers":
        "StencilIt - projet Inkscape : un calque par pochoir, image et aperçus en calques de fond",
    "Support": "Support", "Original image (layout)": "Image d'origine (mise en page)",
    "Preview (flat colours)": "Aperçu (aplats)", "Preview (simulated render)": "Aperçu (rendu simulé)",
    "Layer colours (do not cut)": "Couleurs des couches (ne pas découper)",
    "Colours (spraying order)": "Couleurs (ordre de pulvérisation)",
    "Registration: from the support's top-left corner (mm), crosses": "Calage : depuis le coin haut-gauche du support (mm), croix",
    "Sheet edges: left": "Bords de la feuille : gauche", "top": "haut",
    "top-left": "haut-gauche", "top-right": "haut-droite", "bottom-left": "bas-gauche", "bottom-right": "bas-droite",
    # file names
    "layer": "couche", "of": "sur", "overview": "apercu", "simulated_render": "rendu_simule",
    "outline_mask": "masque_contours", "subject_mask": "masque_sujet", "_outline": "_contours",
    "spray_sheet": "fiche_pulverisation",
    # PDF spraying sheet
    "Spraying sheet": "Fiche de pulvérisation", "Stencil sheet": "Feuille du pochoir", "Image": "Image",
    "Layer colours (spraying order)": "Couleurs des couches (ordre de pulvérisation)",
    "RGB": "RVB", "cut": "découpe", "bridges": "ponts",
    "Support (no paint)": "Support (pas de peinture)",
    "Tone left to the bare support": "Teinte laissée au support nu",
    "Ruler registration, from the support's top-left corner": "Calage à la règle, depuis le coin haut-gauche du support",
    "Pencil a cross at each dimension, then lay each layer with its cross windows on the marks.":
        "Tracez au crayon une croix à chaque cote, puis posez chaque couche en alignant ses fenêtres en croix sur les traits.",
    "Cross": "Croix", "from the left": "depuis la gauche", "from the top": "depuis le haut",
    "from the right": "depuis la droite", "from the bottom": "depuis le bas", "off the support": "hors du support",
    "Sheet edges": "Bords de la feuille", "from the left edge": "du bord gauche", "from the top edge": "du haut",
    "from the right edge": "de la droite", "from the bottom edge": "du bas",
    "Registration": "Calage",
    "The sheet goes around the support: lay each layer with the support's corners in its registration marks.":
        "La feuille entoure le support : posez chaque couche en plaçant les angles du support dans ses repères de calage.",
    "Spray the layers in order, from the first to the last; let each coat dry before laying the next stencil.":
        "Pulvérisez les couches dans l'ordre, de la première à la dernière ; laissez sécher chaque passe avant de poser le pochoir suivant.",
    "Simulated render": "Rendu simulé",
}
_CORNERS_EN = {"haut-gauche": "top-left", "haut-droite": "top-right", "bas-gauche": "bottom-left", "bas-droite": "bottom-right"}


def T(en: str) -> str:
    """Text in the export language (English source string)."""
    return _FR.get(en, en) if _LANG.get() == "fr" else en


def _corner(fr_name: str) -> str:
    return T(_CORNERS_EN.get(fr_name, fr_name))


def _f(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


CORNER_DEG = 55  # beyond this change of direction, the vertex stays a sharp corner


def path_d(pts: np.ndarray, smooth: bool, tol_mm: float = 0.12) -> str:
    """Closed outline -> SVG path.

    Smoothing: the tangent at each vertex follows (next - previous); handles are limited to a third
    of the current segment AND so that the curve never strays more than ~1.5 x the tolerance from
    the chord (no "belly" on long straight segments); sharp corners (> CORNER_DEG) are kept.
    """
    max_bulge = max(0.15, 1.5 * tol_mm)
    pts = np.asarray(pts, np.float64)
    n = len(pts)
    if not smooth or n < 4:
        return "M" + " L".join(f"{_f(x)},{_f(y)}" for x, y in pts) + " Z"
    prev = pts - np.roll(pts, 1, axis=0)
    nxt = np.roll(pts, -1, axis=0) - pts
    lp = np.linalg.norm(prev, axis=1) + 1e-9
    ln = np.linalg.norm(nxt, axis=1) + 1e-9
    cos_turn = (prev * nxt).sum(axis=1) / (lp * ln)
    corner = cos_turn < math.cos(math.radians(CORNER_DEG))
    tang = prev / lp[:, None] + nxt / ln[:, None]
    tang /= (np.linalg.norm(tang, axis=1) + 1e-9)[:, None]
    tang[corner] = 0
    parts = [f"M{_f(pts[0][0])},{_f(pts[0][1])}"]
    for i in range(n):
        j = (i + 1) % n
        seg = ln[i]
        u = nxt[i] / seg
        h = []
        for t in (tang[i], tang[j]):
            s = abs(t[0] * u[1] - t[1] * u[0])  # sin(angle between tangent and chord)
            h.append(min(seg / 3, max_bulge / (0.75 * s)) if s > 1e-6 else seg / 3)
        c1 = pts[i] + tang[i] * h[0]
        c2 = pts[j] - tang[j] * h[1]
        if corner[i] and corner[j]:
            parts.append(f"L{_f(pts[j][0])},{_f(pts[j][1])}")
        else:
            parts.append(f"C{_f(c1[0])},{_f(c1[1])} {_f(c2[0])},{_f(c2[1])} {_f(pts[j][0])},{_f(pts[j][1])}")
    return " ".join(parts) + " Z"


def _marks(res: Result, layer_index: int) -> list[str]:
    """Sheet outline, registration marks and layer-number notches."""
    p = res.params
    W, H = res.sheet_mm
    out = []
    if p.sheet_outline:
        out.append(f'<rect x="0" y="0" width="{_f(W)}" height="{_f(H)}" {CUT}/>')
    shapes, _ = registration_shapes(res, layer_index)
    for s in shapes:
        if s["type"] == "poly":
            d = "M" + " L".join(f"{_f(x)},{_f(y)}" for x, y in s["pts"]) + " Z"
            out.append(f'<path {CUT} d="{d}"/>')
        else:
            out.append(f'<circle cx="{_f(s["cx"])}" cy="{_f(s["cy"])}" r="{_f(s["r"])}" {CUT}/>')
    return out


def _header(W, H, title, comment=""):
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<!-- {comment} -->\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_f(W)}mm" height="{_f(H)}mm" '
            f'viewBox="0 0 {_f(W)} {_f(H)}">\n<title>{title}</title>\n')


def _num(v: float) -> str:
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return s.replace(".", ",") if _LANG.get() == "fr" else s


def positioning_text(res: Result) -> str | None:
    """Ruler dimensions on one line (sheet laid inside the support), None otherwise."""
    if res.params.sheet_mode == "around" or not res.params.reg_dims:
        return None
    pos = positioning(res)
    marks = " ; ".join(f"{_corner(m['coin'])} x={_num(m['x'])} y={_num(m['y'])}" for m in pos["reperes"])
    f = pos["feuille"]
    head = T("Registration: from the support's top-left corner (mm), crosses")
    return (f"{head} {marks}. "
            f"{T('Sheet edges: left')} {_num(f['gauche'])}, {T('top')} {_num(f['haut'])}.")


DIM = 'fill="none" stroke="#1565c0" stroke-width="0.25"'


def _dims_body(res: Result) -> list[str]:
    """Dimensions layer (sheet coordinates): support edge, dimension lines to each cross, values."""
    pos = positioning(res)
    ox, oy = res.sup_off_mm
    sw, sh = res.support_mm
    fs = 3.2
    body = [f'<rect x="{_f(ox)}" y="{_f(oy)}" width="{_f(sw)}" height="{_f(sh)}" {DIM} stroke-dasharray="2,1"/>']
    for m in pos["reperes"]:
        x, y = ox + m["x"], oy + m["y"]              # cross in sheet coordinates
        body.append(f'<path {DIM} stroke-dasharray="1,1" d="M{_f(ox)},{_f(y)} L{_f(x)},{_f(y)} '
                    f'M{_f(x)},{_f(oy)} L{_f(x)},{_f(y)}"/>')
        left = m["coin"].endswith("gauche")
        tx = x + (2 if left else -2)
        ty = y + (6 if m["coin"].startswith("haut") else -4)
        body.append(f'<text x="{_f(tx)}" y="{_f(ty)}" font-family="sans-serif" font-size="{fs}" fill="#1565c0" '
                    f'text-anchor="{"start" if left else "end"}">x {_num(m["x"])} · y {_num(m["y"])}</text>')
    return body


def layer_svg(res: Result, L, material: dict | None = None) -> str:
    """Cut file of one layer: openings, bridges included, plus registration marks."""
    p = res.params
    W, H = res.sheet_mm
    cut = (material or {}).get("cut", {})
    outline = f" ({T('outline')})" if L.kind == "outline" else ""
    comment = (f"StencilIt - {T('Layer').lower()} {L.index}/{len(res.layers)}{outline} - {T('colour')} {bgr_hex(L.color)} - "
               f"{T('material')}: {(material or {}).get('label', T('custom'))} - "
               f"{T('blade')} {cut.get('blade', '?')}, {T('force')} {cut.get('force', '?')}, "
               f"{T('speed')} {cut.get('speed', '?')}, {T('passes')} {cut.get('passes', '?')}")
    cal = positioning_text(res)
    if cal:
        comment += " - " + cal
    title = f"{T('Stencil layer')} {L.index}{' - ' + T('outline') if L.kind == 'outline' else ''} ({bgr_hex(L.color)})"
    s = [_header(W, H, title, comment)]
    s.append('<g id="cut">')
    if L.paths:
        d = " ".join(path_d(pts, p.smooth_curves, p.tolerance_mm) for pts in L.paths)
        s.append(f'<path fill-rule="evenodd" {CUT} d="{d}"/>')
    s.extend(_marks(res, L.index))
    s.append("</g>\n</svg>\n")
    return "\n".join(s)


def overview_svg(res: Result) -> str:
    """Overview of all layers as flat colours on the support (not for cutting)."""
    p = res.params
    W, H = res.sheet_mm
    s = [_header(W, H, T("Overview of all layers"), T("StencilIt - overview (do not cut)"))]
    bg = bgr_hex(res.support_color)
    s.append(f'<rect x="0" y="0" width="{_f(W)}" height="{_f(H)}" fill="#ffffff"/>')
    mx, my = res.sup_off_mm
    sw, sh = res.support_mm
    s.append(f'<rect x="{_f(mx)}" y="{_f(my)}" width="{_f(sw)}" height="{_f(sh)}" fill="{bg}" '
             f'stroke="#999" stroke-width="0.2"/>')
    for L in res.layers:     # openings always lie on the support: no clip-path needed
        d = " ".join(path_d(pts, p.smooth_curves, p.tolerance_mm) for pts in L.paths)
        s.append(f'<path fill-rule="evenodd" fill="{bgr_hex(L.color)}" '
                 f'd="{d}"><title>{T("Layer")} {L.index}</title></path>')
    if positioning_text(res):
        s.append(f'<g id="dimensions"><title>{T("Registration dimensions (do not cut)")}</title>')
        s.extend(_dims_body(res))
        s.append("</g>")
    s.append("</svg>\n")
    return "\n".join(s)


def _img_href(img: np.ndarray, quality: int = 92, max_side: int = 4000) -> str:
    """BGR image -> JPEG data URI (embedded in the SVG).

    Silhouette Studio compatibility (verified): an embedded image is drawn as a black rectangle when
    it carries a clip-path or when it is a PNG inside a hidden layer. Hence JPEG only, and the image
    itself is cropped to the pixel instead of being clipped. Silhouette sometimes draws part of a
    large image in black depending on the zoom (tile rendering): that is a Silhouette display bug,
    the file is correct, so full resolution is kept.
    """
    import base64
    h, w = img.shape[:2]
    k = max_side / max(h, w)
    if k < 1:
        img = cv2.resize(img, (max(1, round(w * k)), max(1, round(h * k))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def _layer(label: str, body: list[str], lid: str, visible: bool = True, locked: bool = False,
           opacity: float | None = None) -> str:
    style = [] if visible else ["display:none"]
    if opacity is not None:
        style.append(f"opacity:{opacity}")
    # hidden layer: style (Inkscape) + display attribute (read by other software, including
    # Silhouette Studio); when Inkscape shows the layer again, its style wins over the attribute.
    attrs = (f'id="{lid}" inkscape:groupmode="layer" inkscape:label="{label}"'
             + (f' style="{";".join(style)}"' if style else "")
             + ("" if visible else ' display="none"')
             + (' sodipodi:insensitive="true"' if locked else ""))
    return f"<g {attrs}>\n" + "\n".join(body) + "\n</g>"


def inkscape_svg(res: Result, material: dict | None = None) -> str:
    """Inkscape document: one layer per element, from back to front.

    Support (background, locked) · original image scaled and placed (locked) · flat-colour
    preview (hidden) · simulated render (hidden) · registration dimensions · one layer per
    stencil (cut lines + marks) in spraying order · colour swatches. Units: mm.
    """
    p = res.params
    ppm = p.px_per_mm
    W, H = res.sheet_mm
    mx, my = res.sup_off_mm
    sw, sh = res.support_mm
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f"<!-- {T('StencilIt - Inkscape project: one layer per stencil, image and previews as background layers')} -->",
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" '
        f'width="{_f(W)}mm" height="{_f(H)}mm" viewBox="0 0 {_f(W)} {_f(H)}">',
        f"<title>{T('StencilIt stencils')}</title>",
        f'<sodipodi:namedview id="namedview" inkscape:document-units="mm" pagecolor="#ffffff" '
        f'inkscape:current-layer="layer{len(res.layers):02d}"/>',
    ]
    # 1. Support
    out.append(_layer(T("Support"), [
        f'<rect id="support" x="{_f(mx)}" y="{_f(my)}" width="{_f(sw)}" height="{_f(sh)}" '
        f'fill="{bgr_hex(res.support_color)}" stroke="#999999" stroke-width="0.2"/>'
    ], "layer_support", locked=True))
    # 2. Original image, cropped / scaled / placed (part visible on the support)
    ih, iw = res.prepared.labels.shape
    x0, y0 = res.img_off_px[0] / ppm, res.img_off_px[1] / ppm
    out.append(_layer(T("Original image (layout)"), [
        f'<image id="original_image" x="{_f(x0)}" y="{_f(y0)}" width="{_f(iw / ppm)}" height="{_f(ih / ppm)}" '
        f'preserveAspectRatio="none" xlink:href="{_img_href(res.prepared.raw if res.prepared.raw is not None else res.prepared.resized)}"/>'
    ], "layer_image", locked=True))
    # 3. Flat preview: stencil openings as filled vector shapes, in spraying order
    body = []
    for L in res.layers:
        d = " ".join(path_d(pts, p.smooth_curves, p.tolerance_mm) for pts in L.paths)
        if d:
            body.append(f'<path fill-rule="evenodd" fill="{bgr_hex(L.color)}" '
                        f'd="{d}"><title>{T("Layer")} {L.index}</title></path>')
    out.append(_layer(T("Preview (flat colours)"), body, "layer_preview", visible=False, locked=True))
    # 4. Simulated render (airbrush blur): common area of sheet and support, cropped to the pixel
    #    (no clip-path, badly handled by some software)
    (sx0, sy0, sx1, sy1), (sox, soy) = support_overlap(res)
    body = []
    if sx1 > sx0 and sy1 > sy0:
        part = simulate_sheet(res)[sy0 + soy:sy1 + soy, sx0 + sox:sx1 + sox]
        body.append(f'<image id="simulated_render" x="{_f((sx0 + sox) / ppm)}" y="{_f((sy0 + soy) / ppm)}" '
                    f'width="{_f((sx1 - sx0) / ppm)}" height="{_f((sy1 - sy0) / ppm)}" '
                    f'preserveAspectRatio="none" xlink:href="{_img_href(part)}"/>')
    out.append(_layer(T("Preview (simulated render)"), body, "layer_render", visible=False, locked=True))
    # 5. Registration dimensions (sheet laid inside the support): not to be cut
    if positioning_text(res):
        out.append(_layer(T("Registration dimensions (do not cut)"), _dims_body(res), "layer_dimensions", locked=True))
    # 6. One layer per stencil (cut lines + registration marks), last one on top
    n = len(res.layers)
    for L in res.layers:
        kind = f" - {T('outline')}" if L.kind == "outline" else ""
        body = []
        if L.paths:
            d = " ".join(path_d(pts, p.smooth_curves, p.tolerance_mm) for pts in L.paths)
            body.append(f'<path fill-rule="evenodd" {CUT} d="{d}"/>')
        body.extend(_marks(res, L.index))
        out.append(_layer(f"{T('Layer')} {L.index:02d}/{n:02d}{kind} ({bgr_hex(L.color)})", body,
                          f"layer{L.index:02d}"))
    # 7. Swatches: one square per layer (≈ 50 × 50 px) in a column left of the sheet, with its code
    out.append(_layer(T("Layer colours (do not cut)"), _swatch_body(res), "layer_colours", locked=True))
    out.append("</svg>\n")
    return "\n".join(out)


def _marks_d(res: Result, layer_index: int) -> list[str]:
    """Sheet outline and registration marks as path data, one closed subpath each (circles as
    4 cubic Béziers), to merge them with the openings into a single compound path."""
    W, H = res.sheet_mm
    out = []
    if res.params.sheet_outline:
        out.append(f"M0,0 L{_f(W)},0 L{_f(W)},{_f(H)} L0,{_f(H)} Z")
    shapes, _ = registration_shapes(res, layer_index)
    k = 0.5522847498                              # Bézier approximation of a quarter circle
    for sh in shapes:
        if sh["type"] == "poly":
            out.append("M" + " L".join(f"{_f(x)},{_f(y)}" for x, y in sh["pts"]) + " Z")
        else:
            cx, cy, r = sh["cx"], sh["cy"], sh["r"]
            c = k * r
            out.append(f"M{_f(cx + r)},{_f(cy)} "
                       f"C{_f(cx + r)},{_f(cy + c)} {_f(cx + c)},{_f(cy + r)} {_f(cx)},{_f(cy + r)} "
                       f"C{_f(cx - c)},{_f(cy + r)} {_f(cx - r)},{_f(cy + c)} {_f(cx - r)},{_f(cy)} "
                       f"C{_f(cx - r)},{_f(cy - c)} {_f(cx - c)},{_f(cy - r)} {_f(cx)},{_f(cy - r)} "
                       f"C{_f(cx + c)},{_f(cy - r)} {_f(cx + r)},{_f(cy - c)} {_f(cx + r)},{_f(cy)} Z")
    return out


def silhouette_svg(res: Result, material: dict | None = None) -> str:
    """Cut file for Silhouette Studio: only the stencils, one layer each, and in each layer a
    SINGLE path holding all its cut lines (openings + sheet outline + registration marks).

    Silhouette Studio ignores part of the shapes of a layer made of many separate polygons;
    a single compound path per layer is cut entirely (verified by the author). No image, no
    preview, no hidden layer: nothing that is not cut. Units: mm.
    """
    p = res.params
    W, H = res.sheet_mm
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f"<!-- {T('StencilIt - Silhouette Studio file: one compound path per stencil (openings, sheet outline and marks)')} -->",
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{_f(W)}mm" height="{_f(H)}mm" viewBox="0 0 {_f(W)} {_f(H)}">',
        f"<title>{T('Stencils for Silhouette Studio')}</title>",
    ]
    n = len(res.layers)
    for L in res.layers:
        kind = f" - {T('outline')}" if L.kind == "outline" else ""
        parts = [path_d(pts, p.smooth_curves, p.tolerance_mm) for pts in L.paths]
        parts += _marks_d(res, L.index)
        label = f"{T('Layer')} {L.index:02d}/{n:02d}{kind} ({bgr_hex(L.color)})"
        out.append(_layer(label, [f'<path id="cut{L.index:02d}" {CUT} d="{" ".join(parts)}"/>'],
                          f"layer{L.index:02d}"))
    out.append("</svg>\n")
    return "\n".join(out)


SWATCH_MM = 50 * 25.4 / 96        # 50 px at 96 dpi ≈ 13.23 mm


def _swatch_body(res: Result) -> list[str]:
    """Colour squares aligned left, one below the other in spraying order, placed outside the page
    (left of the sheet) so they interfere neither with cutting nor with the preview."""
    sq, gap, fs = SWATCH_MM, 3.0, 3.2
    text_w = 30.0                                  # room for the text right of each square
    x0 = -(sq + 2 + text_w + 6)                    # column left of the sheet
    body = [f'<text x="{_f(x0)}" y="-3" font-family="sans-serif" font-size="{fs}" font-weight="bold" '
            f'fill="#333333">{T("Colours (spraying order)")}</text>']
    bg = bgr_hex(res.support_color)
    for k, L in enumerate(res.layers):
        y = k * (sq + gap)
        hx = bgr_hex(L.color)
        name = f"{T('Layer')} {L.index}" + (f" ({T('outline')})" if L.kind == "outline" else "")
        body.append(f'<rect x="{_f(x0)}" y="{_f(y)}" width="{_f(sq)}" height="{_f(sq)}" rx="0.8" fill="{hx}" '
                    f'stroke="#666666" stroke-width="0.2"><title>{name}: {hx}</title></rect>')
        body.append(f'<text x="{_f(x0 + sq + 2)}" y="{_f(y + sq / 2 - 1)}" font-family="sans-serif" '
                    f'font-size="{fs}" fill="#333333">{name}</text>')
        body.append(f'<text x="{_f(x0 + sq + 2)}" y="{_f(y + sq / 2 + fs + 0.5)}" font-family="monospace" '
                    f'font-size="{fs}" font-weight="bold" fill="#111111">{hx}</text>')
    y = len(res.layers) * (sq + gap)               # reminder: support colour
    body.append(f'<rect x="{_f(x0)}" y="{_f(y)}" width="{_f(sq)}" height="{_f(sq)}" rx="0.8" fill="{bg}" '
                f'stroke="#666666" stroke-width="0.2" stroke-dasharray="1,0.6"><title>{T("Support")}: {bg}</title></rect>')
    body.append(f'<text x="{_f(x0 + sq + 2)}" y="{_f(y + sq / 2 - 1)}" font-family="sans-serif" font-size="{fs}" '
                f'fill="#333333">{T("Support")}</text>')
    body.append(f'<text x="{_f(x0 + sq + 2)}" y="{_f(y + sq / 2 + fs + 0.5)}" font-family="monospace" '
                f'font-size="{fs}" font-weight="bold" fill="#111111">{bg}</text>')
    return body


def _mm(v: float) -> str:
    return f"{_num(v)} mm"


def sheet_pdf(res: Result, name: str) -> bytes:
    """Spraying sheet (A4 PDF): formats, layer colours in spraying order, ruler registration
    dimensions and the simulated render."""
    pdf = Pdf()
    L0, R0 = 15.0, 195.0                       # text margins (mm)
    colon = " : " if _LANG.get() == "fr" else ": "
    pdf.text(L0, 20, f"StencilIt - {name}", 16, bold=True)
    pdf.text(L0, 27, T("Spraying sheet"), 11, color="#555555")

    # simulated render, top right
    sim = simulate(res)
    h, w = sim.shape[:2]
    k = min(1.0, 1400 / max(h, w))
    if k < 1:
        sim = cv2.resize(sim, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA)
    ok, jpg = cv2.imencode(".jpg", sim, [cv2.IMWRITE_JPEG_QUALITY, 88])
    sc = min(62.0 / sim.shape[1], 78.0 / sim.shape[0])
    iw, ih = sim.shape[1] * sc, sim.shape[0] * sc
    ix, iy = R0 - iw, 14.0
    pdf.image(jpg.tobytes(), sim.shape[1], sim.shape[0], ix, iy, iw, ih)
    pdf.rect(ix, iy, iw, ih, stroke="#999999", line_w=0.2)
    pdf.text(ix, iy + ih + 4, T("Simulated render"), 8, color="#777777")

    sw, sh = res.support_mm
    y = 38.0
    for label, value in ((T("Support"), f"{_num(sw)} x {_num(sh)} mm, {bgr_hex(res.support_color)}"),
                         (T("Stencil sheet"), f"{_num(res.sheet_mm[0])} x {_num(res.sheet_mm[1])} mm"),
                         (T("Image"), f"{_num(res.image_mm[0])} x {_num(res.image_mm[1])} mm")):
        pdf.text(L0, y, label, 9, color="#555555")
        pdf.text(L0 + 34, y, value, 9)
        y += 5.5

    # Layer colours (left column, beside the render while there is room)
    y = 66.0
    pdf.text(L0, y, T("Layer colours (spraying order)"), 12, bold=True)
    y += 4
    sq = 11.0

    def swatch_row(y, hx, title, sub, dash=False):
        pdf.rect(L0, y, sq, sq, fill=hx, stroke="#666666", line_w=0.25, dash=dash)
        r, g, b = (int(hx[i:i + 2], 16) for i in (1, 3, 5))
        pdf.text(L0 + sq + 4, y + 4.5, title, 10, bold=True)
        pdf.text(L0 + sq + 4, y + 9.5, hx, 10, mono=True)
        pdf.text(L0 + sq + 26, y + 9.5, f"{T('RGB')} {r}, {g}, {b}", 9, color="#444444")
        if sub:
            pdf.text(L0 + sq + 4, y + 14.0, sub, 8, color="#777777")

    row = sq + 7
    for L in res.layers:
        if y + row > 285:
            pdf.add_page()
            y = 20.0
        title = f"{T('Layer')} {L.index}" + (f" ({T('outline')})" if L.kind == "outline" else "")
        st = layer_stats(L)
        swatch_row(y, bgr_hex(L.color), title,
                   f"{T('cut')} {_num(st['cut_length_m'])} m, {st['bridges']} {T('bridges')}")
        y += row
    swatch_row(y, bgr_hex(res.support_color), T("Support (no paint)"), "", dash=True)
    y += sq + 4
    if res.support_label is not None:
        y += 4
        pdf.text(L0, y, f"{T('Tone left to the bare support')}{colon}"
                        f"{bgr_hex(res.prepared.palette[res.support_label])}", 9, color="#555555")
    y = max(y, iy + ih + 6)
    for line in wrap(T("Spray the layers in order, from the first to the last; let each coat dry before "
                       "laying the next stencil."), R0 - L0, 9):
        y += 5
        pdf.text(L0, y, line, 9, color="#333333")

    # Ruler registration
    y += 12
    if y > 235:
        pdf.add_page()
        y = 20.0
    pos = positioning(res)
    around = res.params.sheet_mode == "around" or not pos["reperes"]
    pdf.text(L0, y, T("Registration") if around else T("Ruler registration, from the support's top-left corner"),
             12, bold=True)
    y += 1
    if around:
        for line in wrap(T("The sheet goes around the support: lay each layer with the support's corners in "
                           "its registration marks."), R0 - L0, 9):
            y += 5
            pdf.text(L0, y, line, 9)
        return pdf.output()
    for line in wrap(T("Pencil a cross at each dimension, then lay each layer with its cross windows on "
                       "the marks."), R0 - L0, 9):
        y += 5
        pdf.text(L0, y, line, 9, color="#333333")
    y += 8
    cols = [L0, L0 + 46, L0 + 80, L0 + 114, L0 + 148]
    for x, head in zip(cols, (T("Cross"), T("from the left"), T("from the top"), T("from the right"),
                              T("from the bottom"))):
        pdf.text(x, y, head, 9, color="#555555")
    y += 1.8
    pdf.line(L0, y, R0, y)
    for m in pos["reperes"]:
        y += 6
        off = not m["sur_support"]
        col = "#c0501e" if off else "#000000"
        pdf.text(cols[0], y, _corner(m["coin"]) + (f" ({T('off the support')})" if off else ""), 9.5, color=col)
        pdf.text(cols[1], y, _mm(m["x"]), 10, bold=True, color=col)
        pdf.text(cols[2], y, _mm(m["y"]), 10, bold=True, color=col)
        pdf.text(cols[3], y, _mm(m["depuis_droite"]), 9.5, color=col)
        pdf.text(cols[4], y, _mm(m["depuis_bas"]), 9.5, color=col)
    f = pos["feuille"]
    y += 3
    pdf.line(L0, y, R0, y)
    txt = (f"{T('Sheet edges')} ({_mm(f['largeur'])} x {_mm(f['hauteur'])}){colon}{_mm(f['gauche'])} "
           f"{T('from the left edge')}, {_mm(f['haut'])} {T('from the top edge')}, {_mm(f['droite'])} "
           f"{T('from the right edge')}, {_mm(f['bas'])} {T('from the bottom edge')}.")
    for line in wrap(txt, R0 - L0, 9):
        y += 5.5
        pdf.text(L0, y, line, 9)
    return pdf.output()


PROJECT_VERSION = 1


def export_zip(res: Result, material: dict | None, name: str = "stencil",
               original: tuple[bytes | None, str] | None = None, mask_png: bytes | None = None,
               ui: dict | None = None, subject_png: bytes | None = None, lang: str = "en",
               subject_exact: bool = False) -> bytes:
    """Zip of the stencils + reloadable project (original image, masks, interface settings).

    The JSON keys of …_infos.json are a file format and stay unchanged whatever the language
    (projects reopen in both languages); only human-readable text and file names are translated.
    """
    token = _LANG.set("fr" if lang == "fr" else "en")
    try:
        buf = io.BytesIO()
        raw, ext = original or (None, ".png")
        img_file = f"{name}_original{ext}" if raw else None
        mask_file = f"{name}_{T('outline_mask')}.png" if mask_png else None
        subject_file = f"{name}_{T('subject_mask')}.png" if subject_png else None
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            if raw:
                z.writestr(img_file, raw)
            if mask_png:
                z.writestr(mask_file, mask_png)
            if subject_png:
                z.writestr(subject_file, subject_png)
            n = len(res.layers)
            for L in res.layers:
                kind = T("_outline") if L.kind == "outline" else ""
                z.writestr(f"{name}_{T('layer')}{L.index:02d}_{T('of')}{n:02d}{kind}_{bgr_hex(L.color)[1:]}.svg",
                           layer_svg(res, L, material))
            z.writestr(f"{name}_{T('overview')}.svg", overview_svg(res))
            z.writestr(f"{name}_inkscape.svg", inkscape_svg(res, material))
            z.writestr(f"{name}_silhouette.svg", silhouette_svg(res, material))
            ok, png = cv2.imencode(".png", simulate(res))
            z.writestr(f"{name}_{T('simulated_render')}.png", png.tobytes())
            z.writestr(f"{name}_{T('spray_sheet')}.pdf", sheet_pdf(res, name))
            info = {
                # Project: reopen this zip (or this file) in StencilIt with "Open a project…"
                "projet": {
                    "version": PROJECT_VERSION,
                    "logiciel": "StencilIt",
                    "nom": name,
                    "image": img_file,
                    "masque": mask_file,
                    "masque_sujet": subject_file,
                    "masque_sujet_exact": bool(subject_png and subject_exact),
                    "interface": ui,
                },
                "format_feuille_mm": [round(v, 1) for v in res.sheet_mm],
                "format_support_mm": [round(v, 1) for v in res.support_mm],
                "feuille_dans_support_mm": [round(v, 1) for v in res.sheet_rect_mm],
                "calage_a_la_regle": positioning(res) if res.params.sheet_mode != "around" else None,
                "format_image_mm": [round(v, 1) for v in res.image_mm],
                "couleur_support": bgr_hex(res.support_color),
                "teinte_laissee_au_support": (bgr_hex(res.prepared.palette[res.support_label])
                                             if res.support_label is not None else None),
                "calage": {"coins": res.params.reg_corners, "forme": res.params.reg_shape,
                           "taille_mm": res.params.reg_size_mm},
                "ordre_de_pulverisation": [
                    {"couche": L.index, "couleur": bgr_hex(L.color), **layer_stats(L)} for L in res.layers
                ],
                "materiau": material,
                "parametres": res.params.__dict__,
            }
            z.writestr(f"{name}_infos.json", json.dumps(info, ensure_ascii=False, indent=2))
        return buf.getvalue()
    finally:
        _LANG.reset(token)
