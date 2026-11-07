"""Export SVG (unités en mm) compatible Silhouette Studio / Inkscape."""
from __future__ import annotations

import io
import json
import math
import zipfile

import cv2
import numpy as np

from .pipeline import (Result, bgr_hex, layer_stats, positioning, registration_shapes, simulate, simulate_sheet,
                       support_overlap)

CUT = 'fill="none" stroke="#ff0000" stroke-width="0.1"'


def _f(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


CORNER_DEG = 55  # au-delà de ce changement de direction, le sommet reste un angle vif


def path_d(pts: np.ndarray, smooth: bool, tol_mm: float = 0.12) -> str:
    """Contour fermé -> chemin SVG.

    Lissage : tangente en chaque sommet = direction (suivant - précédent), poignées
    bornées au tiers du segment courant ET de façon que la courbe ne s'écarte pas de
    la corde de plus de ~1,5 x la tolérance (pas de « ventre » sur les longs segments
    droits) ; les angles vifs (> CORNER_DEG) sont conservés.
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
            s = abs(t[0] * u[1] - t[1] * u[0])  # sin(angle tangente / corde)
            h.append(min(seg / 3, max_bulge / (0.75 * s)) if s > 1e-6 else seg / 3)
        c1 = pts[i] + tang[i] * h[0]
        c2 = pts[j] - tang[j] * h[1]
        if corner[i] and corner[j]:
            parts.append(f"L{_f(pts[j][0])},{_f(pts[j][1])}")
        else:
            parts.append(f"C{_f(c1[0])},{_f(c1[1])} {_f(c2[0])},{_f(c2[1])} {_f(pts[j][0])},{_f(pts[j][1])}")
    return " ".join(parts) + " Z"


def _marks(res: Result, layer_index: int) -> list[str]:
    """Contour de feuille, repères de calage et encoches du numéro de couche."""
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
    return f"{v:.1f}".replace(".", ",").replace(",0", "")


def positioning_text(res: Result) -> str | None:
    """Cotes à la règle en une ligne (feuille posée dans le support), None sinon."""
    if res.params.sheet_mode == "around" or not res.params.reg_dims:
        return None
    pos = positioning(res)
    marks = " ; ".join(f"{m['coin']} x={_num(m['x'])} y={_num(m['y'])}" for m in pos["reperes"])
    f = pos["feuille"]
    return (f"Calage : depuis le coin haut-gauche du support (mm), croix {marks}. "
            f"Bords de la feuille : gauche {_num(f['gauche'])}, haut {_num(f['haut'])}.")


DIM = 'fill="none" stroke="#1565c0" stroke-width="0.25"'


def _dims_body(res: Result) -> list[str]:
    """Calque de cotes (repère feuille) : bord du support, lignes de cote vers chaque croix, valeurs."""
    pos = positioning(res)
    ox, oy = res.sup_off_mm
    sw, sh = res.support_mm
    fs = 3.2
    body = [f'<rect x="{_f(ox)}" y="{_f(oy)}" width="{_f(sw)}" height="{_f(sh)}" {DIM} stroke-dasharray="2,1"/>']
    for m in pos["reperes"]:
        x, y = ox + m["x"], oy + m["y"]              # croix dans le repère feuille
        body.append(f'<path {DIM} stroke-dasharray="1,1" d="M{_f(ox)},{_f(y)} L{_f(x)},{_f(y)} '
                    f'M{_f(x)},{_f(oy)} L{_f(x)},{_f(y)}"/>')
        tx = x + (2 if m["coin"].endswith("gauche") else -2)
        anchor = "start" if m["coin"].endswith("gauche") else "end"
        ty = y + (6 if m["coin"].startswith("haut") else -4)
        body.append(f'<text x="{_f(tx)}" y="{_f(ty)}" font-family="sans-serif" font-size="{fs}" fill="#1565c0" '
                    f'text-anchor="{anchor}">x {_num(m["x"])} · y {_num(m["y"])}</text>')
    return body


def layer_svg(res: Result, L, material: dict | None = None) -> str:
    p = res.params
    W, H = res.sheet_mm
    cut = (material or {}).get("cut", {})
    comment = (f"StencilIt - couche {L.index}/{len(res.layers)}{' (contours)' if L.kind == 'outline' else ''} - couleur {bgr_hex(L.color)} - "
               f"matériau: {(material or {}).get('label', 'personnalisé')} - "
               f"lame {cut.get('blade', '?')}, force {cut.get('force', '?')}, "
               f"vitesse {cut.get('speed', '?')}, passes {cut.get('passes', '?')}")
    cal = positioning_text(res)
    if cal:
        comment += " - " + cal
    s = [_header(W, H, f"Pochoir couche {L.index}{' - contours' if L.kind == 'outline' else ''} ({bgr_hex(L.color)})", comment)]
    s.append(f'<g id="decoupe">')
    if L.paths:
        d = " ".join(path_d(pts, p.smooth_curves, p.tolerance_mm) for pts in L.paths)
        s.append(f'<path fill-rule="evenodd" {CUT} d="{d}"/>')
    s.extend(_marks(res, L.index))
    s.append("</g>\n</svg>\n")
    return "\n".join(s)


def overview_svg(res: Result) -> str:
    p = res.params
    W, H = res.sheet_mm
    s = [_header(W, H, "Aperçu de toutes les couches", "StencilIt - aperçu (ne pas découper)")]
    bg = bgr_hex(res.support_color)
    s.append(f'<rect x="0" y="0" width="{_f(W)}" height="{_f(H)}" fill="#ffffff"/>')
    mx, my = res.sup_off_mm
    sw, sh = res.support_mm
    s.append(f'<rect x="{_f(mx)}" y="{_f(my)}" width="{_f(sw)}" height="{_f(sh)}" fill="{bg}" '
             f'stroke="#999" stroke-width="0.2"/>')
    for L in res.layers:     # les ouvertures sont toujours sur le support : pas besoin de découpe (clip-path)
        d = " ".join(path_d(pts, p.smooth_curves, p.tolerance_mm) for pts in L.paths)
        s.append(f'<path fill-rule="evenodd" fill="{bgr_hex(L.color)}" '
                 f'd="{d}"><title>Couche {L.index}</title></path>')
    if positioning_text(res):
        s.append('<g id="cotes"><title>Cotes de calage (ne pas découper)</title>')
        s.extend(_dims_body(res))
        s.append("</g>")
    s.append("</svg>\n")
    return "\n".join(s)


def _img_href(img: np.ndarray, quality: int = 92, max_side: int = 4000) -> str:
    """Image BGR -> data URI JPEG (embarquée dans le SVG).

    Compatibilité Silhouette Studio (vérifiée) : une image embarquée s'affiche en rectangle noir
    si elle porte une découpe (clip-path) ou si c'est un PNG dans un calque masqué. Donc : JPEG
    uniquement, et recadrage de l'image elle-même au pixel près plutôt qu'une découpe.
    Silhouette affiche parfois une partie d'une grande image en noir (rendu par tuiles, selon le
    zoom) : c'est un défaut d'affichage de Silhouette, le fichier est correct. On garde la pleine
    résolution.
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
    # calque masqué : style (Inkscape) + attribut display (relu par d'autres logiciels, dont Silhouette
    # Studio) ; quand Inkscape réaffiche le calque, son style l'emporte sur l'attribut.
    attrs = (f'id="{lid}" inkscape:groupmode="layer" inkscape:label="{label}"'
             + (f' style="{";".join(style)}"' if style else "")
             + ("" if visible else ' display="none"')
             + (' sodipodi:insensitive="true"' if locked else ""))
    return f"<g {attrs}>\n" + "\n".join(body) + "\n</g>"


def inkscape_svg(res: Result, material: dict | None = None) -> str:
    """Document Inkscape : un calque par élément, du fond vers le dessus.

    Support (fond, verrouillé) · Image d'origine redimensionnée et mise en page (verrouillée)
    · Aperçu net (aplats vectoriels, masqué) · Rendu simulé (masqué) · un calque par pochoir
    (traits de coupe + repères), dans l'ordre de pulvérisation. Unités : mm.
    """
    p = res.params
    ppm = p.px_per_mm
    W, H = res.sheet_mm
    mx, my = res.sup_off_mm
    sw, sh = res.support_mm
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!-- StencilIt - projet Inkscape : un calque par pochoir, image et aperçus en calques de fond -->",
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" '
        f'width="{_f(W)}mm" height="{_f(H)}mm" viewBox="0 0 {_f(W)} {_f(H)}">',
        "<title>Pochoirs StencilIt</title>",
        f'<sodipodi:namedview id="namedview" inkscape:document-units="mm" pagecolor="#ffffff" '
        f'inkscape:current-layer="couche{len(res.layers):02d}"/>',
    ]
    # 1. Support
    out.append(_layer("Support", [
        f'<rect id="support" x="{_f(mx)}" y="{_f(my)}" width="{_f(sw)}" height="{_f(sh)}" '
        f'fill="{bgr_hex(res.support_color)}" stroke="#999999" stroke-width="0.2"/>'
    ], "calque_support", locked=True))
    # 2. Image d'origine, recadrée / redimensionnée / placée (partie visible sur le support)
    ih, iw = res.prepared.labels.shape
    x0, y0 = res.img_off_px[0] / ppm, res.img_off_px[1] / ppm
    out.append(_layer("Image d'origine (mise en page)", [
        f'<image id="image_origine" x="{_f(x0)}" y="{_f(y0)}" width="{_f(iw / ppm)}" height="{_f(ih / ppm)}" '
        f'preserveAspectRatio="none" xlink:href="{_img_href(res.prepared.resized)}"/>'
    ], "calque_image", locked=True))
    # 3. Aperçu net : aplats vectoriels des pochoirs, dans l'ordre de pulvérisation
    body = []
    for L in res.layers:
        d = " ".join(path_d(pts, p.smooth_curves, p.tolerance_mm) for pts in L.paths)
        if d:
            body.append(f'<path fill-rule="evenodd" fill="{bgr_hex(L.color)}" '
                        f'd="{d}"><title>Couche {L.index}</title></path>')
    out.append(_layer("Aperçu (aplats)", body, "calque_apercu", visible=False, locked=True))
    # 4 bis. Rendu simulé (flou de l'aérographe) : partie commune feuille / support, découpée au pixel
    #    (pas de clip-path, mal relu par certains logiciels)
    (sx0, sy0, sx1, sy1), (sox, soy) = support_overlap(res)
    body = []
    if sx1 > sx0 and sy1 > sy0:
        part = simulate_sheet(res)[sy0 + soy:sy1 + soy, sx0 + sox:sx1 + sox]
        body.append(f'<image id="rendu_simule" x="{_f((sx0 + sox) / ppm)}" y="{_f((sy0 + soy) / ppm)}" '
                    f'width="{_f((sx1 - sx0) / ppm)}" height="{_f((sy1 - sy0) / ppm)}" '
                    f'preserveAspectRatio="none" xlink:href="{_img_href(part)}"/>')
    out.append(_layer("Aperçu (rendu simulé)", body, "calque_rendu", visible=False, locked=True))
    # 4 ter. Cotes de calage (feuille posée dans le support) : ne pas découper
    if positioning_text(res):
        out.append(_layer("Cotes de calage (ne pas découper)", _dims_body(res), "calque_cotes", locked=True))
    # 5. Un calque par pochoir (traits de coupe + repères de calage), dernier = au-dessus
    n = len(res.layers)
    for L in res.layers:
        kind = " - contours" if L.kind == "outline" else ""
        body = []
        if L.paths:
            d = " ".join(path_d(pts, p.smooth_curves, p.tolerance_mm) for pts in L.paths)
            body.append(f'<path fill-rule="evenodd" {CUT} d="{d}"/>')
        body.extend(_marks(res, L.index))
        out.append(_layer(f"Couche {L.index:02d}/{n:02d}{kind} ({bgr_hex(L.color)})", body,
                          f"couche{L.index:02d}"))
    out.append("</svg>\n")
    return "\n".join(out)


PROJECT_VERSION = 1


def export_zip(res: Result, material: dict | None, name: str = "pochoir",
               original: tuple[bytes | None, str] | None = None, mask_png: bytes | None = None,
               ui: dict | None = None) -> bytes:
    """Zip des pochoirs + projet rechargeable (image d'origine, masque, réglages de l'interface)."""
    buf = io.BytesIO()
    raw, ext = original or (None, ".png")
    img_file = f"{name}_original{ext}" if raw else None
    mask_file = f"{name}_masque_contours.png" if mask_png else None
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if raw:
            z.writestr(img_file, raw)
        if mask_png:
            z.writestr(mask_file, mask_png)
        n = len(res.layers)
        for L in res.layers:
            kind = "_contours" if L.kind == "outline" else ""
            z.writestr(f"{name}_couche{L.index:02d}_sur{n:02d}{kind}_{bgr_hex(L.color)[1:]}.svg",
                       layer_svg(res, L, material))
        z.writestr(f"{name}_apercu.svg", overview_svg(res))
        z.writestr(f"{name}_inkscape.svg", inkscape_svg(res, material))
        ok, png = cv2.imencode(".png", simulate(res))
        z.writestr(f"{name}_rendu_simule.png", png.tobytes())
        info = {
            # Projet : rouvrir ce zip (ou ce fichier) dans StencilIt via « Ouvrir un projet… »
            "projet": {
                "version": PROJECT_VERSION,
                "logiciel": "StencilIt",
                "nom": name,
                "image": img_file,
                "masque": mask_file,
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
