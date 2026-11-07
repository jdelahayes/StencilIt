"""Chaîne de traitement : image -> couches de pochoir découpables.

Toutes les grandeurs physiques sont en millimètres ; le calcul se fait sur une
grille raster de `px_per_mm` pixels par millimètre puis les contours sont
vectorisés en mm.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace

import cv2
import numpy as np


@dataclass
class Params:
    # Support (surface peinte)
    support_w_mm: float = 210.0
    support_h_mm: float = 297.0
    support_color: str = "#ffffff"
    inner_margin_mm: float = 10.0  # marge de référence pour « ajuster au support »
    # Recadrage de l'image source (fractions 0..1)
    crop_x: float = 0.0
    crop_y: float = 0.0
    crop_w: float = 1.0
    crop_h: float = 1.0
    # Mise en page sur le support
    image_scale: float = 100.0     # % de la taille « ajustée au support »
    image_height_factor: float = 1.0  # étirement vertical (1 = proportions d'origine)
    image_pos_x: float = 50.0      # centre de l'image, en % de la largeur du support
    image_pos_y: float = 50.0      # centre de l'image, en % de la hauteur du support
    px_per_mm: float = 6.0
    # Simplification
    n_layers: int = 3              # nombre de pochoirs
    color_mode: str = "auto"       # auto | color | gray
    detail: float = 50.0           # 0 (très simplifié) .. 100 (très détaillé)
    layering: str = "cumulative"   # cumulative | exclusive
    skip_support: bool = True      # la teinte la plus proche du support n'a pas de pochoir
    # Pochoir de contours (détails clés estompés par le flou de l'aérographe)
    outline: bool = False
    outline_sensitivity: float = 50.0   # 0 = seulement les détails les plus marqués .. 100 = beaucoup de détails
    outline_width_mm: float = 0.8       # largeur du trait (au moins l'ouverture mini du matériau)
    outline_min_length_mm: float = 4.0  # longueur mini d'un trait
    outline_auto_color: bool = True     # couleur auto = teinte la plus contrastée avec le support
    outline_color: str = "#1e1e1e"
    # Contraintes du matériau
    min_opening_mm: float = 0.8    # largeur mini d'une ouverture
    min_strip_mm: float = 1.0      # largeur mini d'une bande de matière
    bridge_width_mm: float = 1.5
    min_area_mm2: float = 2.5
    double_bridge_area_mm2: float = 400.0
    min_bridges: int = 1           # nombre minimum de ponts par îlot (1 à 4)
    bridges: bool = True
    # Vectorisation
    tolerance_mm: float = 0.12
    smooth_curves: bool = True
    # Feuille du pochoir :
    #   around = support + marge tout autour (calage sur les angles du support)
    #   fit    = dans le support, ajustée au motif + bordure (calage sur croix tracées sur le support)
    #   fixed  = dans le support, taille fixe centrée sur le motif
    sheet_mode: str = "around"
    margin_mm: float = 15.0
    sheet_border_mm: float = 20.0
    sheet_w_mm: float = 304.8
    sheet_h_mm: float = 304.8
    reg_dims: bool = True          # cotes à la règle des croix (feuille dans le support)
    sheet_outline: bool = True
    machine_max_mm: float = 305.0  # largeur de coupe utile de la machine
    mat_w_mm: float = 304.8        # tapis de découpe (0 = sans tapis : seule la largeur compte)
    mat_h_mm: float = 304.8
    mat_orient: str = "portrait"   # portrait = sens d'entrée dans la machine ; paysage = tapis tourné d'1/4 de tour
    # Calage
    reg_corners: int = 4           # 0, 3 (détrompeur) ou 4
    reg_shape: str = "equerre"     # equerre | croix | rond
    reg_size_mm: float = 10.0
    layer_notches: bool = True     # encoches indiquant le n° de couche
    # Aperçu
    spray_mm: float = 0.4

    @classmethod
    def from_dict(cls, d: dict) -> "Params":
        p = cls()
        for f in fields(cls):
            if f.name in d and d[f.name] is not None:
                default = getattr(p, f.name)
                v = d[f.name]
                if isinstance(default, bool):
                    v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "on", "yes")
                else:
                    v = type(default)(v)
                setattr(p, f.name, v)
        p.n_layers = int(np.clip(p.n_layers, 1, 10))
        p.detail = float(np.clip(p.detail, 0, 100))
        p.px_per_mm = float(np.clip(p.px_per_mm, 2, 16))
        p.support_w_mm = float(np.clip(p.support_w_mm, 20, 3000))
        p.support_h_mm = float(np.clip(p.support_h_mm, 20, 3000))
        p.inner_margin_mm = float(np.clip(p.inner_margin_mm, 0, min(p.support_w_mm, p.support_h_mm) / 2 - 5))
        p.crop_x = float(np.clip(p.crop_x, 0, 0.98))
        p.crop_y = float(np.clip(p.crop_y, 0, 0.98))
        p.crop_w = float(np.clip(p.crop_w, 0.02, 1 - p.crop_x))
        p.crop_h = float(np.clip(p.crop_h, 0.02, 1 - p.crop_y))
        p.image_scale = float(np.clip(p.image_scale, 5, 1000))
        p.image_height_factor = float(np.clip(p.image_height_factor, 0.1, 10))
        p.image_pos_x = float(np.clip(p.image_pos_x, -100, 200))
        p.image_pos_y = float(np.clip(p.image_pos_y, -100, 200))
        p.min_bridges = int(np.clip(p.min_bridges, 1, 4))
        p.reg_corners = p.reg_corners if p.reg_corners in (0, 3, 4) else 4
        p.sheet_mode = p.sheet_mode if p.sheet_mode in ("around", "fit", "fixed") else "around"
        p.mat_orient = p.mat_orient if p.mat_orient in ("portrait", "landscape") else "portrait"
        p.margin_mm = float(np.clip(p.margin_mm, 0, 200))
        p.sheet_border_mm = float(np.clip(p.sheet_border_mm, 3, 200))
        p.sheet_w_mm = float(np.clip(p.sheet_w_mm, 30, 3000))
        p.sheet_h_mm = float(np.clip(p.sheet_h_mm, 30, 3000))
        if not p.support_color.startswith("#") or len(p.support_color) != 7:
            p.support_color = "#ffffff"
        if not p.outline_color.startswith("#") or len(p.outline_color) != 7:
            p.outline_color = "#1e1e1e"
        p.outline_sensitivity = float(np.clip(p.outline_sensitivity, 0, 100))
        p.outline_width_mm = float(np.clip(p.outline_width_mm, 0.2, 10))
        p.outline_min_length_mm = float(np.clip(p.outline_min_length_mm, 0, 200))
        return p


@dataclass
class Layout:
    src_rect: tuple    # (x0, y0, x1, y1) pixels de l'image source réellement utilisés
    img_mm: tuple      # (largeur, hauteur) de l'image entière (après recadrage) sur le support
    pos_mm: tuple      # (x, y) coin haut-gauche de l'image entière dans le support
    vis_mm: tuple      # (x0, y0, x1, y1) partie visible (dans le support)
    sheet_mm: tuple = (0.0, 0.0, 0.0, 0.0)  # (x0, y0, x1, y1) feuille du pochoir, repère du support


def sheet_rect(p: Params, vis_mm: tuple) -> tuple[float, float, float, float]:
    """Feuille du pochoir dans le repère du support (mm), selon le mode choisi."""
    SW, SH = p.support_w_mm, p.support_h_mm
    if p.sheet_mode == "around":
        m = p.margin_mm
        return (-m, -m, SW + m, SH + m)
    vx0, vy0, vx1, vy1 = vis_mm
    if p.sheet_mode == "fit":
        b = p.sheet_border_mm
        return (vx0 - b, vy0 - b, vx1 + b, vy1 + b)
    cx, cy = (vx0 + vx1) / 2, (vy0 + vy1) / 2
    return (cx - p.sheet_w_mm / 2, cy - p.sheet_h_mm / 2, cx + p.sheet_w_mm / 2, cy + p.sheet_h_mm / 2)


def crop_rect(p: Params, img_shape) -> tuple[int, int, int, int]:
    h, w = img_shape[:2]
    x0 = int(round(p.crop_x * w))
    y0 = int(round(p.crop_y * h))
    x1 = max(x0 + 2, min(w, int(round((p.crop_x + p.crop_w) * w))))
    y1 = max(y0 + 2, min(h, int(round((p.crop_y + p.crop_h) * h))))
    return x0, y0, x1, y1


def resolve_layout(p: Params, img_shape) -> tuple[Layout, list[str]]:
    """Place l'image recadrée sur le support.

    Taille de référence (100 %) = image ajustée dans le support moins la marge intérieure.
    Les parties qui dépassent du support sont rognées.
    """
    cx0, cy0, cx1, cy1 = crop_rect(p, img_shape)
    ar = (cy1 - cy0) / (cx1 - cx0)
    SW, SH = p.support_w_mm, p.support_h_mm
    avail_w = max(5.0, SW - 2 * p.inner_margin_mm)
    avail_h = max(5.0, SH - 2 * p.inner_margin_mm)
    warnings = []
    fit_w = min(avail_w, avail_h / ar)
    img_w = fit_w * p.image_scale / 100
    img_h = img_w * ar * p.image_height_factor
    x0 = p.image_pos_x / 100 * SW - img_w / 2
    y0 = p.image_pos_y / 100 * SH - img_h / 2
    vx0, vy0 = max(0.0, x0), max(0.0, y0)
    vx1, vy1 = min(SW, x0 + img_w), min(SH, y0 + img_h)
    if vx1 - vx0 < 2 or vy1 - vy0 < 2:
        warnings.append("L'image est entièrement hors du support : elle a été recentrée.")
        x0, y0 = (SW - img_w) / 2, (SH - img_h) / 2
        vx0, vy0 = max(0.0, x0), max(0.0, y0)
        vx1, vy1 = min(SW, x0 + img_w), min(SH, y0 + img_h)
    if (vx0 > x0 + 0.05) or (vy0 > y0 + 0.05) or (vx1 < x0 + img_w - 0.05) or (vy1 < y0 + img_h - 0.05):
        warnings.append("L'image dépasse du support : elle est rognée à ses bords (impression à fond perdu).")
    # Feuille du pochoir ; en taille fixe, le motif est limité à l'intérieur de la feuille (moins la bordure)
    sh_rect = sheet_rect(p, (vx0, vy0, vx1, vy1))
    if p.sheet_mode == "fixed":
        b = min(p.sheet_border_mm, (sh_rect[2] - sh_rect[0]) / 2 - 2, (sh_rect[3] - sh_rect[1]) / 2 - 2)
        ix0, iy0, ix1, iy1 = sh_rect[0] + b, sh_rect[1] + b, sh_rect[2] - b, sh_rect[3] - b
        nvx0, nvy0, nvx1, nvy1 = max(vx0, ix0), max(vy0, iy0), min(vx1, ix1), min(vy1, iy1)
        if max(nvx0 - vx0, nvy0 - vy0, vx1 - nvx1, vy1 - nvy1) > 0.05:
            warnings.append(f"Le motif est plus grand que la feuille ({p.sheet_w_mm:.0f} × {p.sheet_h_mm:.0f} mm, "
                            f"bordure {b:.0f} mm comprise) : il est rogné aux bords de la feuille.")
        vx0, vy0, vx1, vy1 = nvx0, nvy0, max(nvx1, nvx0 + 2), max(nvy1, nvy0 + 2)
    # partie de la source correspondant à la zone visible
    sx = (cx1 - cx0) / img_w
    sy = (cy1 - cy0) / img_h
    src = (int(round(cx0 + (vx0 - x0) * sx)), int(round(cy0 + (vy0 - y0) * sy)),
           int(round(cx0 + (vx1 - x0) * sx)), int(round(cy0 + (vy1 - y0) * sy)))
    src = (src[0], src[1], max(src[0] + 2, src[2]), max(src[1] + 2, src[3]))
    lay = Layout(src_rect=src, img_mm=(img_w, img_h), pos_mm=(x0, y0), vis_mm=(vx0, vy0, vx1, vy1),
                 sheet_mm=sh_rect)
    sheet_w = sh_rect[2] - sh_rect[0]
    sheet_h = sh_rect[3] - sh_rect[1]
    if p.sheet_mode != "around":
        out = [n for n, d in (("gauche", -sh_rect[0]), ("haut", -sh_rect[1]),
                              ("droit", sh_rect[2] - SW), ("bas", sh_rect[3] - SH)) if d > 0.5]
        if out:
            warnings.append("La feuille déborde du support (bord " + ", ".join(out) + ") : elle sera posée "
                            "à cheval sur le bord ; les croix hors du support ne pourront pas y être tracées.")
    if p.mat_w_mm > 0 and p.mat_h_mm > 0:
        land = p.mat_orient == "landscape"
        # dimensions physiques (largeur = sens de la machine) puis orientées comme sur le support
        mw, mh = (p.mat_h_mm, p.mat_w_mm) if land else (p.mat_w_mm, p.mat_h_mm)
        mat = (f"tapis de {p.mat_w_mm:g} × {p.mat_h_mm:g} mm".replace(".", ",")
               + (" (en paysage)" if land else ""))
        if p.mat_w_mm > p.machine_max_mm + 1:
            warnings.append(f"Le {mat} est plus large que la largeur de coupe de la machine "
                            f"({p.machine_max_mm:.0f} mm) : il ne passera pas dans la machine.")
        if sheet_w <= mw + 1e-6 and sheet_h <= mh + 1e-6:
            pass
        elif sheet_h <= mw + 1e-6 and sheet_w <= mh + 1e-6:
            warnings.append(f"La feuille ({sheet_w:.0f} × {sheet_h:.0f} mm) ne tient sur le {mat} qu'en la "
                            f"tournant d'un quart de tour : passez le tapis en "
                            f"{'portrait' if land else 'paysage'} (section Feuille du pochoir & calage).")
        else:
            fix = ("réduisez la marge autour du support, passez en « feuille dans le support »"
                   if p.sheet_mode == "around" else "réduisez la bordure ou la taille du motif")
            warnings.append(f"La feuille ({sheet_w:.0f} × {sheet_h:.0f} mm) dépasse le {mat} : {fix}, "
                            f"choisissez un tapis plus grand ou découpez en plusieurs morceaux.")
    elif min(sheet_w, sheet_h) > p.machine_max_mm:
        warnings.append(f"La feuille ({sheet_w:.0f} × {sheet_h:.0f} mm) est plus large que la largeur de coupe "
                        f"de la machine ({p.machine_max_mm:.0f} mm), même tournée : il faudra la découper en plusieurs morceaux.")
    elif sheet_w > p.machine_max_mm:
        warnings.append(f"La feuille fait {sheet_w:.0f} mm de large, plus que la largeur de coupe "
                        f"({p.machine_max_mm:.0f} mm) : faites-la passer tournée d'un quart de tour dans la machine.")
    return lay, warnings


def hex_to_bgr(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array((int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)), np.float32)


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------

def decode_image(data: bytes) -> np.ndarray:
    """Décode une image (avec gestion de la transparence -> fond blanc)."""
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("Image illisible")
    if img.dtype != np.uint8:
        img = cv2.convertScaleAbs(img, alpha=255.0 / max(1, img.max()))
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        a = img[..., 3:4].astype(np.float32) / 255.0
        img = (img[..., :3].astype(np.float32) * a + 255 * (1 - a)).astype(np.uint8)
    # limite raisonnable pour la mémoire
    h, w = img.shape[:2]
    s = 4000 / max(h, w)
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    return img


def is_grayscale(img: np.ndarray) -> bool:
    small = cv2.resize(img, (128, 128), interpolation=cv2.INTER_AREA).astype(np.int16)
    spread = small.max(axis=2) - small.min(axis=2)
    return float(np.percentile(spread, 95)) < 12


def disk(r: float) -> np.ndarray:
    r = max(1, int(round(r)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def remove_small(mask: np.ndarray, min_px: int, keep_border: bool = False) -> np.ndarray:
    """Supprime les composantes (blanches) de surface < min_px."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return mask
    keep = stats[:, cv2.CC_STAT_AREA] >= min_px
    keep[0] = False
    if keep_border:
        h, w = mask.shape
        x, y, bw, bh = (stats[:, i] for i in range(4))
        touches = (x == 0) | (y == 0) | (x + bw >= w) | (y + bh >= h)
        keep |= touches
        keep[0] = False
    return np.where(keep[lab], 255, 0).astype(np.uint8)


def lab_to_bgr(lab_colors: np.ndarray) -> np.ndarray:
    arr = np.clip(lab_colors, 0, 255).astype(np.uint8).reshape(1, -1, 3)
    return cv2.cvtColor(arr, cv2.COLOR_LAB2BGR).reshape(-1, 3)


def bgr_hex(c) -> str:
    b, g, r = (int(v) for v in c)
    return f"#{r:02x}{g:02x}{b:02x}"


# --------------------------------------------------------------------------
# 1-2. Prétraitement + quantification
# --------------------------------------------------------------------------

@dataclass
class Prepared:
    resized: np.ndarray      # image redimensionnée (référence)
    labels: np.ndarray       # carte d'étiquettes, triées du plus clair (0) au plus foncé
    palette: np.ndarray      # couleurs BGR triées clair -> foncé
    gray: bool
    off_px: tuple = (0, 0)   # position de la partie visible dans le support (px)


def prepare(img: np.ndarray, p: Params, lay: Layout) -> Prepared:
    ppm = p.px_per_mm
    sx0, sy0, sx1, sy1 = lay.src_rect
    src = img[sy0:sy1, sx0:sx1]
    vx0, vy0, vx1, vy1 = lay.vis_mm
    SW = int(round(p.support_w_mm * ppm))
    SH = int(round(p.support_h_mm * ppm))
    ox, oy = int(round(vx0 * ppm)), int(round(vy0 * ppm))
    W = max(4, min(SW - ox, int(round((vx1 - vx0) * ppm))))
    H = max(4, min(SH - oy, int(round((vy1 - vy0) * ppm))))
    h0, w0 = src.shape[:2]
    interp = cv2.INTER_AREA if W < w0 else cv2.INTER_CUBIC
    resized = cv2.resize(src, (W, H), interpolation=interp)

    gray = is_grayscale(src) if p.color_mode == "auto" else p.color_mode == "gray"
    d = p.detail / 100.0

    # Lissage préservant les contours, plus fort quand le détail est bas
    sm = resized.copy()
    iters = 1 + int(round((1 - d) * 3))
    for _ in range(iters):
        sm = cv2.bilateralFilter(sm, 7, 15 + (1 - d) * 55, 3 + (1 - d) * 6)

    k = p.n_layers + (1 if p.skip_support else 0)
    lab = cv2.cvtColor(sm, cv2.COLOR_BGR2LAB).astype(np.float32)
    feat = lab[..., :1] if gray else lab
    X = feat.reshape(-1, feat.shape[-1])

    rng = np.random.default_rng(0)
    idx = rng.choice(len(X), size=min(len(X), 60000), replace=False)
    cv2.setRNGSeed(0)
    k_eff = int(min(k, len(np.unique(X[idx].round(), axis=0))))
    k_eff = max(1, k_eff)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 0.2)
    _, _, centers = cv2.kmeans(X[idx], k_eff, None, crit, 3, cv2.KMEANS_PP_CENTERS)

    # Affectation de tous les pixels
    best = np.full(len(X), np.inf, np.float32)
    labels = np.zeros(len(X), np.int32)
    for i, c in enumerate(centers):
        dist = ((X - c) ** 2).sum(axis=1)
        upd = dist < best
        best[upd] = dist[upd]
        labels[upd] = i
    labels = labels.reshape(H, W)

    # Filtre majoritaire (simplification des formes)
    r = (0.15 + (1 - d) * 1.6) * p.px_per_mm
    labels = majority_filter(labels, len(centers), r)

    # Couleurs moyennes réelles (sur l'image lissée) et tri clair -> foncé
    lab_full = lab.reshape(H, W, 3)
    used = [i for i in range(len(centers)) if np.any(labels == i)]
    means = np.array([lab_full[labels == i].mean(axis=0) for i in used], np.float32)
    if gray:
        means[:, 1:] = 128
    order = np.argsort(-means[:, 0])
    remap = np.zeros(len(centers), np.int32)
    for new, old_pos in enumerate(order):
        remap[used[old_pos]] = new
    labels = remap[labels]
    palette = lab_to_bgr(means[order])
    return Prepared(resized=resized, labels=labels, palette=palette, gray=gray, off_px=(ox, oy))


def recommend_layers(img: np.ndarray, gray: bool, skip_lightest: bool, max_colors: int = 9) -> dict:
    """Recommande un nombre de pochoirs pour une image.

    On quantifie l'image (réduite) avec k = 1..max_colors teintes et on mesure l'écart
    moyen (ΔE) à l'image. On s'arrête au plus petit k qui :
      - atteint un écart jugé « bon » (ΔE <= cible), ou
      - n'est presque plus amélioré par une teinte de plus (coude de la courbe), ou
      - dont la teinte suivante ne couvrirait qu'une surface négligeable.
    """
    h, w = img.shape[:2]
    s = 240 / max(h, w)
    small = cv2.resize(img, (max(8, round(w * s)), max(8, round(h * s))), interpolation=cv2.INTER_AREA)
    small = cv2.bilateralFilter(small, 5, 30, 4)
    lab = cv2.cvtColor(small.astype(np.float32) / 255, cv2.COLOR_BGR2LAB).reshape(-1, 3)
    X = lab[:, :1].copy() if gray else lab.copy()
    target = 4.0 if gray else 7.0
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1)
    uniq = len(np.unique(X.round(1), axis=0))

    curve = []  # (k, ΔE, part de la plus petite teinte)
    for k in range(1, min(max_colors, uniq) + 1):
        cv2.setRNGSeed(0)
        _, lab_k, centers = cv2.kmeans(X, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
        lab_k = lab_k.ravel()
        err = float(np.sqrt(((X - centers[lab_k]) ** 2).sum(axis=1)).mean())
        share = float(np.bincount(lab_k, minlength=k).min() / len(lab_k))
        curve.append((k, err, share))

    # Teintes vraiment distinctes : centres de k max fusionnés s'ils sont proches (ΔE < 12)
    k_max, _, _ = curve[-1]
    cv2.setRNGSeed(0)
    _, lab_k, centers = cv2.kmeans(X, k_max, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    shares = np.bincount(lab_k.ravel(), minlength=k_max) / len(lab_k)
    kept = [c for c, sh in sorted(zip(centers, shares), key=lambda t: -t[1]) if sh >= 0.01]
    distinct = []
    for c in kept:
        if all(np.linalg.norm(c - d) >= (8 if gray else 12) for d in distinct):
            distinct.append(c)

    e1 = curve[0][1] or 1.0
    chosen, reason = curve[-1][0], "la courbe ne se stabilise pas : image riche en nuances"
    for idx in range(1, len(curve)):
        k, err, _ = curve[idx]
        if err <= target:
            chosen, reason = k, f"écart à l'original jugé bon (ΔE {err:.1f} ≤ {target:g})"
            break
        if idx + 1 < len(curve):
            gain = (err - curve[idx + 1][1]) / e1
            if curve[idx + 1][2] < 0.015:
                chosen, reason = k, "une teinte de plus ne couvrirait qu'une surface négligeable"
                break
            if gain < 0.04:
                chosen, reason = k, "une teinte de plus n'améliore presque plus le rendu"
                break

    offset = 1 if skip_lightest else 0
    rec = int(np.clip(chosen - offset, 1, 8))
    options = [{"layers": k - offset, "delta_e": round(err, 1)}
               for k, err, _ in curve if 1 <= k - offset <= 8]
    return {"layers": rec, "colors": chosen, "distinct_colors": len(distinct),
            "reason": reason, "curve": options, "gray": gray}


def majority_filter(labels: np.ndarray, k: int, r: float) -> np.ndarray:
    if r < 1:
        return labels
    acc = np.full(labels.shape, -1.0, np.float32)
    out = labels.copy()
    for i in range(k):
        m = (labels == i).astype(np.float32)
        if not m.any():
            continue
        b = cv2.GaussianBlur(m, (0, 0), r / 2)
        upd = b > acc
        out[upd] = i
        acc[upd] = b[upd]
    return out


# --------------------------------------------------------------------------
# 3-4. Couches + contraintes de découpe
# --------------------------------------------------------------------------

def clean_mask(mask: np.ndarray, p: Params, extra_area_mm2: float = 0.0) -> np.ndarray:
    ppm = p.px_per_mm
    m = mask
    r_open = p.min_opening_mm * ppm / 2
    if r_open >= 0.5:
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, disk(r_open))
    r_close = p.min_strip_mm * ppm / 2
    if r_close >= 0.5:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, disk(r_close))
    amin = int((p.min_area_mm2 + extra_area_mm2) * ppm * ppm)
    if amin > 1:
        m = remove_small(m, amin)
        m = 255 - remove_small(255 - m, amin, keep_border=True)
    return m


def add_bridges(opening: np.ndarray, p: Params, hidden: np.ndarray | None = None) -> list[tuple]:
    """Relie chaque îlot de matière au cadre. Modifie `opening` en place.

    `hidden` : masque des zones qui seront repeintes par une couche suivante ;
    un pont qui y passe sera invisible sur le résultat final -> privilégié.
    Renvoie la liste des ponts [(x1, y1, x2, y2)] en pixels.
    """
    ppm = p.px_per_mm
    bw = max(1, int(round(p.bridge_width_mm * ppm)))
    bridges = []
    double_px = p.double_bridge_area_mm2 * ppm * ppm
    n_islands = None
    short_islands = 0  # îlots qui n'ont pas pu recevoir le nombre de ponts demandé

    for _ in range(2000):
        # Composantes recalculées à chaque tour : un pont peut s'arrêter sur un autre îlot
        # (chaîne d'îlots), le groupe formé est alors relié au cadre au tour suivant.
        material = (opening == 0).astype(np.uint8)
        n, lab, stats, cents = cv2.connectedComponentsWithStats(material, connectivity=4)
        main = lab[0, 0]
        pending = [i for i in range(1, n) if i != main]
        if n_islands is None:
            n_islands = len(pending)
        if not pending:
            break
        is_main = lab == main
        src = np.where(is_main, 0, 255).astype(np.uint8)
        dist = cv2.distanceTransform(src, cv2.DIST_L2, 5)
        best = None
        for i in pending:
            x, y, w, h, _a = stats[i]
            sub_lab = lab[y:y + h, x:x + w]
            sub = np.where(sub_lab == i, dist[y:y + h, x:x + w], np.inf)
            j = int(np.argmin(sub))
            dv = float(sub.flat[j])
            if best is None or dv < best[0]:
                best = (dv, i, x + j % w, y + j // w)
        dv, i, px, py = best
        want = max(p.min_bridges, 2 if stats[i, cv2.CC_STAT_AREA] > double_px else 1)
        cands = _candidates(lab, i, stats[i], cents[i], dist, is_main, hidden, dv, ppm,
                            wide=want > 1, bw=bw)
        if not cands or min(c[0] for c in cands) >= 1e6:
            # aucun pont propre près de l'îlot : on cherche sur tout son pourtour, sans limite de longueur
            far = _candidates(lab, i, stats[i], cents[i], dist, is_main, hidden, dv, ppm,
                              wide=want > 1, bw=bw, unlimited=True)
            if far and min(c[0] for c in far) < 1e6:
                cands = far
        if not cands:
            q = _nearest(is_main, px, py, dv)
            if q:
                c = _clip_bridge(lab, i, px, py, q, bw)
                q = c[0] if c else q
            cands = [(dv, (px, py), q, 0.0)] if q else []
        chosen = _spread(cands, want)
        if len(chosen) < want:
            short_islands += 1
        drawn = False
        for _s, (ax, ay), q, _a in chosen:
            if q is not None and (ax, ay) != q:
                cv2.line(opening, (ax, ay), q, 0, thickness=bw, lineType=cv2.LINE_8)
                bridges.append((ax, ay, q[0], q[1]))
                drawn = True
        if not drawn:   # sécurité : rien n'a changé, on éviterait une boucle sans fin
            break
    return bridges, n_islands or 0, short_islands


def _spread(cands: list, want: int) -> list:
    """Choisit `want` ponts bien répartis autour de l'îlot (écart angulaire), au meilleur score.

    Les ponts « dégagés » passent d'abord (même moins bien répartis) ; ceux qui longent un bord
    (score ≥ 1e6) ne complètent la sélection qu'en dernier recours.
    """
    clean = [c for c in cands if c[0] < 1e6]
    chosen = _spread_in(clean, want, [])
    # Pas assez de place autour : un pont dégagé proche d'un autre vaut mieux qu'un pont qui longe
    # un bord -> on prend le dégagé le plus écarté (en angle) de ceux déjà choisis.
    while chosen and len(chosen) < want:
        rest = [c for c in clean if c not in chosen and all(c[1] != d[1] for d in chosen)]
        if not rest:
            break
        gap = lambda c: min(abs((c[3] - d[3] + math.pi) % (2 * math.pi) - math.pi) for d in chosen)
        chosen.append(max(rest, key=lambda c: (round(gap(c), 2), -c[0])))
    if len(chosen) < want:
        chosen = _spread_in(cands, want, chosen)
    return chosen


def _spread_in(cands: list, want: int, chosen: list) -> list:
    chosen = list(chosen)
    if not cands:
        return chosen
    if not chosen:
        chosen = [min(cands, key=lambda c: c[0])]
    sep = 2 * math.pi / want * 0.75
    while len(chosen) < want and sep >= math.radians(25):
        ok = [c for c in cands if c not in chosen and all(
            abs((c[3] - d[3] + math.pi) % (2 * math.pi) - math.pi) >= sep for d in chosen)]
        if ok:
            chosen.append(min(ok, key=lambda c: c[0]))
        else:
            sep *= 0.75  # pas assez de place : on accepte des ponts plus rapprochés
    return chosen


def _nearest(is_main, x, y, d):
    R = int(math.ceil(d)) + 3
    H, W = is_main.shape
    x0, x1 = max(0, x - R), min(W, x + R + 1)
    y0, y1 = max(0, y - R), min(H, y + R + 1)
    ys, xs = np.nonzero(is_main[y0:y1, x0:x1])
    if len(xs) == 0:
        return None
    d2 = (xs + x0 - x) ** 2 + (ys + y0 - y) ** 2
    k = int(np.argmin(d2))
    return int(xs[k] + x0), int(ys[k] + y0)


def _clip_bridge(lab, i, ax, ay, q, bw=1):
    """Raccourcit le pont [ancre -> q] pour qu'il ne passe que dans le vide.

    Après avoir quitté l'îlot `i`, le pont s'arrête sur la première matière rencontrée (cadre ou
    autre îlot : les îlots se relient alors en chaîne). S'il commence par traverser l'îlot `i` ou
    s'il le retraverse plus loin (ancre sur une face « arrière »), le candidat est rejeté (None).
    Sinon renvoie (arrivée, dégagé) ; dégagé = False si le pont longe ou frôle de la matière.
    """
    n = max(2, int(math.ceil(math.hypot(q[0] - ax, q[1] - ay))) + 1)
    lx = np.linspace(ax, q[0], n).round().astype(int)
    ly = np.linspace(ay, q[1], n).round().astype(int)
    v = lab[ly, lx]
    gap = np.flatnonzero(v == 0)
    if len(gap) == 0:          # matière immédiatement voisine
        return q, True
    s = gap[0]
    if s > 3:                  # le pont commencerait par traverser l'îlot (ancre côté opposé)
        return None
    hit = np.flatnonzero(v[s:] != 0)
    if len(hit) == 0:
        return q, _clear_of_material(lab, i, ax, ay, q, bw)
    h = s + hit[0]
    if v[h] == i:
        return None
    q = int(lx[h]), int(ly[h])
    return q, _clear_of_material(lab, i, ax, ay, q, bw)


def _clear_of_material(lab, i, ax, ay, q, bw):
    """Le pont se tient-il à distance de la matière en dehors de ses deux attaches ?

    On élargit le pont d'un dégagement de chaque côté ; hors des disques d'attache autour de
    l'ancre (rayon 1,5 × demi-largeur élargie : le pont doit quitter l'îlot à plus de ~40° de son
    bord) et de l'arrivée (rayon 2 ×, ~30°), cette bande ne doit toucher aucune matière. Cela
    écarte les ponts qui longent ou frôlent un bord, même quand ils restent entièrement dans le
    vide et paraissent « coller » à l'îlot.
    """
    half = bw / 2 + max(2.0, bw / 2)          # demi-largeur + dégagement
    r_dep = 1.5 * half + 1
    r_att = 2 * half + 1
    H, W = lab.shape
    r = int(math.ceil(half)) + 1
    x0, x1 = max(0, min(ax, q[0]) - r), min(W, max(ax, q[0]) + r + 1)
    y0, y1 = max(0, min(ay, q[1]) - r), min(H, max(ay, q[1]) + r + 1)
    band = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.line(band, (ax - x0, ay - y0), (q[0] - x0, q[1] - y0), 1, thickness=max(1, int(round(2 * half))))
    cv2.circle(band, (ax - x0, ay - y0), int(r_dep), 0, -1)
    cv2.circle(band, (q[0] - x0, q[1] - y0), int(r_att), 0, -1)
    touch = int((band.astype(bool) & (lab[y0:y1, x0:x1] != 0)).sum())
    return touch <= 1


def _candidates(lab, i, st, cent, dist, is_main, hidden, dmin, ppm, max_pts=96, wide=False, bw=1,
                unlimited=False):
    """Ponts candidats depuis le bord de l'îlot : (score, ancre, point du cadre, angle).

    Score = longueur pondérée par la part visible du pont (non repeinte ensuite).
    """
    x, y, w, h, _ = st
    m = (lab[y:y + h, x:x + w] == i).astype(np.uint8)
    border = m & ~cv2.erode(m, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0)
    ys, xs = np.nonzero(border)
    if len(xs) == 0:
        return []
    xs = xs + x
    ys = ys + y
    dd = dist[ys, xs]
    # Plusieurs ponts demandés : on accepte des ponts plus longs pour pouvoir les répartir
    limit = np.inf if unlimited else max(3 * dmin, dmin + 12 * ppm) * (4 if wide else 1)
    ok = dd <= limit
    xs, ys, dd = xs[ok], ys[ok], dd[ok]
    if len(xs) > max_pts:
        step = len(xs) / max_pts
        sel = (np.arange(max_pts) * step).astype(int)
        # garder toujours le point le plus proche
        sel = np.unique(np.append(sel, int(np.argmin(dd))))
        xs, ys, dd = xs[sel], ys[sel], dd[sel]
    out = []
    for ax, ay, d in zip(xs.tolist(), ys.tolist(), dd.tolist()):
        q = _nearest(is_main, ax, ay, d)
        if q is None:
            continue
        c = _clip_bridge(lab, i, ax, ay, q, bw)
        if c is None:   # le pont repasserait sur l'îlot lui-même
            continue
        q, clean = c
        length = math.hypot(q[0] - ax, q[1] - ay)
        vis = 1.0
        if hidden is not None and length > 0:
            n = max(2, int(length))
            lx = np.linspace(ax, q[0], n).round().astype(int)
            ly = np.linspace(ay, q[1], n).round().astype(int)
            vis = 1.0 - float(hidden[ly, lx].mean())
        score = (length + 1) * (0.15 + 0.85 * vis)
        if not clean:   # longe un bord : seulement en dernier recours
            score += 1e6
        out.append((score, (ax, ay), q, math.atan2(ay - cent[1], ax - cent[0])))
    return out


# --------------------------------------------------------------------------
# 5. Vectorisation
# --------------------------------------------------------------------------

def vectorize(opening: np.ndarray, p: Params) -> list[np.ndarray]:
    """Contours fermés en mm (liste de tableaux Nx2)."""
    ppm = p.px_per_mm
    cnts, _ = cv2.findContours(opening, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    sigma = max(0.8, 0.2 * ppm)
    eps = max(0.3, p.tolerance_mm * ppm)
    out = []
    for c in cnts:
        if len(c) < 6:
            continue
        pts = c[:, 0, :].astype(np.float32)
        pts = _smooth_closed(pts, sigma)
        approx = cv2.approxPolyDP(pts.reshape(-1, 1, 2), eps, True)[:, 0, :]
        if len(approx) < 3:
            continue
        out.append((approx + 0.5) / ppm)
    return out


def _smooth_closed(pts: np.ndarray, sigma: float) -> np.ndarray:
    n = len(pts)
    r = int(min(3 * sigma, (n - 1) // 2))
    if r < 1:
        return pts
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    ext = np.concatenate([pts[-r:], pts, pts[:r]])
    xs = np.convolve(ext[:, 0], k, mode="valid")
    ys = np.convolve(ext[:, 1], k, mode="valid")
    return np.stack([xs, ys], axis=1).astype(np.float32)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

@dataclass
class Layer:
    index: int               # 1..n (ordre de pulvérisation)
    color: np.ndarray        # BGR
    target: np.ndarray       # masque visé (zone image)
    opening: np.ndarray      # masque final des ouvertures (feuille entière)
    lost: np.ndarray         # détails perdus par les contraintes (zone image)
    bridges: list
    paths: list              # contours en mm (repère feuille)
    islands: int = 0         # nombre d'îlots reliés par des ponts
    short_islands: int = 0   # îlots n'ayant pas pu recevoir le minimum de ponts demandé
    kind: str = "color"      # "color" (aplat) ou "outline" (contours des détails clés)


@dataclass
class Result:
    params: Params
    prepared: Prepared
    layers: list
    support_color: np.ndarray    # BGR
    support_label: int | None    # teinte laissée au support (pas de pochoir)
    sheet_mm: tuple              # (largeur, hauteur) de la feuille du pochoir
    support_mm: tuple
    image_mm: tuple
    support_px: tuple            # (largeur, hauteur)
    img_off_px: tuple            # (x, y) de l'image dans la feuille
    sup_off_px: tuple = (0, 0)   # (x, y) du coin haut-gauche du support dans la feuille (peut être < 0)
    sheet_rect_mm: tuple = (0.0, 0.0, 0.0, 0.0)  # feuille dans le repère du support (x0, y0, x1, y1)

    @property
    def sup_off_mm(self) -> tuple:
        return (-self.sheet_rect_mm[0], -self.sheet_rect_mm[1])


def _lab(bgr: np.ndarray) -> np.ndarray:
    arr = np.asarray(bgr, np.float32).reshape(1, -1, 3) / 255.0
    return cv2.cvtColor(arr, cv2.COLOR_BGR2LAB).reshape(-1, 3)


def build(prep: Prepared, p: Params, outline_region: np.ndarray | None = None) -> Result:
    """`outline_region` : masque booléen (zone image) limitant la recherche des détails clés
    du pochoir de contours ; None = toute l'image."""
    labels = prep.labels
    H, W = labels.shape
    ppm = p.px_per_mm
    SW = int(round(p.support_w_mm * ppm))
    SH = int(round(p.support_h_mm * ppm))
    # Feuille dans le repère du support (la partie visible de l'image se déduit de la préparation)
    vis = (prep.off_px[0] / ppm, prep.off_px[1] / ppm, (prep.off_px[0] + W) / ppm, (prep.off_px[1] + H) / ppm)
    sx0, sy0, sx1, sy1 = sheet_rect(p, vis)
    ox, oy = int(round(-sx0 * ppm)), int(round(-sy0 * ppm))       # support dans la feuille
    sheet_shape = (max(int(round((sy1 - sy0) * ppm)), oy + prep.off_px[1] + H + 1),
                   max(int(round((sx1 - sx0) * ppm)), ox + prep.off_px[0] + W + 1))
    X0, Y0 = ox + prep.off_px[0], oy + prep.off_px[1]
    support = hex_to_bgr(p.support_color)

    n_colors = len(prep.palette)
    sup = None
    if p.skip_support and n_colors > 1:
        d = np.linalg.norm(_lab(prep.palette) - _lab(support), axis=1)
        sup = int(np.argmin(d))
    color_ids = [i for i in range(n_colors) if i != sup]
    extra_area = (1 - p.detail / 100.0) * 15.0

    def place(mask: np.ndarray) -> np.ndarray:
        full = np.zeros(sheet_shape, np.uint8)
        full[Y0:Y0 + H, X0:X0 + W] = mask
        return full

    targets, cleaned_all = [], []
    for li, ci in enumerate(color_ids):
        if p.layering == "cumulative":
            t = np.isin(labels, color_ids[li:])
        else:
            t = labels == ci
        t = np.where(t, 255, 0).astype(np.uint8)
        targets.append(t)
        cleaned_all.append(clean_mask(t, p, extra_area))

    layers = []
    for li, ci in enumerate(color_ids):
        target, cleaned = targets[li], cleaned_all[li]
        lost = cv2.bitwise_xor(cleaned, target)
        opening = place(cleaned)
        hidden = None
        if li + 1 < len(color_ids):
            later = np.zeros_like(cleaned)
            for c2 in cleaned_all[li + 1:]:
                later |= c2
            hidden = place(later) > 0
        bridges, n_isl, n_short = add_bridges(opening, p, hidden) if p.bridges else ([], 0, 0)
        paths = vectorize(opening, p)
        layers.append(Layer(index=li + 1, color=prep.palette[ci], target=target,
                            opening=opening, lost=lost, bridges=bridges, paths=paths,
                            islands=n_isl, short_islands=n_short))
    res = Result(params=p, prepared=prep, layers=layers, support_color=support, support_label=sup,
                 sheet_mm=(sheet_shape[1] / ppm, sheet_shape[0] / ppm),
                 support_mm=(SW / ppm, SH / ppm), image_mm=(W / ppm, H / ppm),
                 support_px=(SW, SH), img_off_px=(X0, Y0), sup_off_px=(ox, oy),
                 sheet_rect_mm=(sx0, sy0, sx0 + sheet_shape[1] / ppm, sy0 + sheet_shape[0] / ppm))

    # Pochoir de contours : peint en dernier, au-dessus de toutes les couches
    if p.outline:
        sim = image_sim(res)
        target = detect_key_details(prep, sim, p, outline_region)
        if target.any():
            color = outline_color(prep, support, p)
            cleaned = clean_mask(target, p)
            lost = cv2.bitwise_xor(cleaned, target)
            opening = place(cleaned)
            bridges, n_isl, n_short = add_bridges(opening, p, None) if p.bridges else ([], 0, 0)
            layers.append(Layer(index=len(layers) + 1, color=color, target=target, opening=opening,
                                lost=lost, bridges=bridges, paths=vectorize(opening, p),
                                islands=n_isl, short_islands=n_short, kind="outline"))
    return res


def outline_color(prep: Prepared, support: np.ndarray, p: Params) -> np.ndarray:
    """Couleur du trait : choisie par l'utilisateur, ou teinte de la palette la plus contrastée avec le support."""
    if not p.outline_auto_color:
        return hex_to_bgr(p.outline_color).astype(np.uint8)
    L_sup = _lab(support)[0, 0]
    L_pal = _lab(prep.palette)[:, 0]
    return prep.palette[int(np.argmax(np.abs(L_pal - L_sup)))]


def detect_key_details(prep: Prepared, sim: np.ndarray, p: Params,
                       region: np.ndarray | None = None) -> np.ndarray:
    """Détails clés de l'image que le rendu en aplats (simplification + flou de l'aérographe) fait disparaître.

    1. Contours nets de l'original (Canny, seuils adaptés à l'image et à la sensibilité).
    2. On ne garde que ceux où le contraste local du rendu simulé est nettement plus faible
       que celui de l'original (détail perdu ou estompé).
    3. On supprime les traits trop courts, puis on les épaissit à la largeur du trait.
    Renvoie un masque (zone image) des ouvertures du pochoir de contours.
    """
    ppm = p.px_per_mm
    s = p.outline_sensitivity / 100.0
    ref = prep.resized

    def lab(img):
        return cv2.cvtColor(img.astype(np.float32) / 255.0, cv2.COLOR_BGR2LAB)

    def grad(labimg):
        sig = max(0.7, 0.12 * ppm)
        g2 = np.zeros(labimg.shape[:2], np.float32)
        for c in range(3):
            ch = cv2.GaussianBlur(labimg[..., c], (0, 0), sig)
            gx = cv2.Sobel(ch, cv2.CV_32F, 1, 0, ksize=3)
            gy = cv2.Sobel(ch, cv2.CV_32F, 0, 1, ksize=3)
            g2 += gx * gx + gy * gy
        return np.sqrt(g2)

    g_ref = grad(lab(ref))
    g_sim = grad(lab(sim))

    # 1. Contours candidats : Canny sur la luminance ET sur les canaux de couleur (a, b),
    #    pour attraper aussi les détails de même luminosité que leur entourage.
    lab8 = cv2.cvtColor(cv2.bilateralFilter(ref, 7, 40, 5), cv2.COLOR_BGR2LAB)
    edges = np.zeros(ref.shape[:2], bool)
    for c, (lo, hi) in enumerate(((12, 32), (8, 20), (8, 20))):
        edges |= cv2.Canny(lab8[..., c], lo, hi, L2gradient=True) > 0
    b = max(2, int(round(0.5 * ppm)))   # pas de trait sur le bord de l'image elle-même
    edges[:b, :] = False; edges[-b:, :] = False; edges[:, :b] = False; edges[:, -b:] = False
    if region is not None:               # masque peint par l'utilisateur : on ne cherche que dedans
        edges &= region.astype(bool)

    # 2. Perte de netteté : part du contraste local de l'original absente du rendu simulé
    loss = np.clip((g_ref - g_sim) / (g_ref + 1e-3), 0, 1)
    loss = cv2.dilate(loss, disk(max(1.0, 0.4 * ppm)))      # tolérance de position du bord

    # 3. Sélection point par point : importance = contraste de l'original x part perdue.
    #    La sensibilité fixe la part des points de contour retenus (des plus importants aux moins importants).
    cand = edges & (loss >= 0.5 - 0.3 * s)
    if not cand.any():
        return np.zeros(ref.shape[:2], np.uint8)
    score = g_ref * loss
    thr = float(np.percentile(score[cand], 100 * (0.85 - 0.8 * s)))
    sel = cand & (score >= thr)
    # recoller les petites coupures le long d'un même trait, puis retirer les morceaux trop courts
    e8 = cv2.morphologyEx(sel.astype(np.uint8) * 255, cv2.MORPH_CLOSE, disk(max(1.0, 0.3 * ppm)))
    n, lab_e, stats, _ = cv2.connectedComponentsWithStats(e8, connectivity=8)
    min_px = max(2, int(p.outline_min_length_mm * ppm))
    # longueur approximative d'un trait = sa plus grande dimension
    length = np.maximum(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT])
    keep = length >= min_px
    keep[0] = False
    e8 = keep[lab_e].astype(np.uint8) * 255
    # largeur effective : jamais moins que l'ouverture mini du matériau (sinon non découpable)
    width = max(p.outline_width_mm, p.min_opening_mm * 1.05)
    stroke = cv2.dilate(e8, disk(width * ppm / 2))
    return stroke

# --------------------------------------------------------------------------
# Repères de calage (géométrie exacte en mm, repère feuille)
# --------------------------------------------------------------------------

CORNER_NAMES = ("haut-gauche", "haut-droite", "bas-gauche", "bas-droite")


def _reg_layout(res: Result) -> tuple[str, list[tuple], float, list[str]]:
    """Forme effective, centres des repères (repère feuille, mm) et largeur de la bande libre.

    Renvoie (forme, [(nom, cx, cy, sx, sy)], bande, avertissements) ; (sx, sy) = sens vers l'intérieur.
    """
    p = res.params
    a = p.reg_size_mm
    t = max(1.0, min(a / 5, 2.5))
    W, H = res.sheet_mm
    warns = []
    shape = p.reg_shape
    if p.sheet_mode == "around":
        m = p.margin_mm
        ox, oy = res.sup_off_mm
        sw, sh = res.support_mm
        x0, y0, x1, y1 = ox, oy, ox + sw, oy + sh
        corners = [(x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)]
        if shape == "equerre" and p.reg_corners and m < t + 1:
            warns.append(f"Marge de la feuille trop petite pour des équerres (il faut au moins {t + 1:.1f} mm) : "
                         "repères en croix à la place.")
            shape = "croix"
        pts = []
        for name, (cx, cy, sx, sy) in zip(CORNER_NAMES, corners[:p.reg_corners]):
            if shape == "equerre":
                pts.append((name, cx, cy, sx, sy))
            elif m >= a + 2:
                pts.append((name, cx - sx * m / 2, cy - sy * m / 2, sx, sy))          # dans la marge
            else:
                pts.append((name, cx + sx * (a / 2 + 1), cy + sy * (a / 2 + 1), sx, sy))  # dans l'angle du support
                if p.inner_margin_mm < a + 2 and not warns:
                    warns.append("Les repères sont placés dans les angles du support et risquent de "
                                 "chevaucher l'image : augmentez la marge de la feuille ou la marge intérieure.")
        return shape, pts, m, warns
    # Feuille posée DANS le support : pas d'angle du support à viser -> croix (ou trous) dans la bordure,
    # reportées au crayon sur le support grâce aux cotes.
    if shape == "equerre":
        shape = "croix"
    bx = (res.img_off_px[0]) / p.px_per_mm                       # bordure réelle à gauche…
    by = (res.img_off_px[1]) / p.px_per_mm
    bx2 = W - bx - res.image_mm[0]
    by2 = H - by - res.image_mm[1]
    band = max(0.0, min(bx, by, bx2, by2))
    corners = [(0, 0, 1, 1), (W, 0, -1, 1), (0, H, 1, -1), (W, H, -1, -1)]
    off = band / 2 if band >= a + 2 else a / 2 + 1
    if band < a + 2:
        warns.append(f"Bordure de la feuille trop étroite pour les repères ({band:.0f} mm, il en faut "
                     f"{a + 2:.0f}) : ils risquent de chevaucher le motif. Augmentez la bordure.")
    pts = [(name, cx + sx * off, cy + sy * off, sx, sy)
           for name, (cx, cy, sx, sy) in zip(CORNER_NAMES, corners[:p.reg_corners])]
    return shape, pts, band, warns


def registration_shapes(res: Result, layer_index: int | None = None) -> tuple[list[dict], list[str]]:
    """Formes à découper pour le calage.

    - equerre : fente en L posée à l'extérieur de chaque angle du support. Le pochoir est
      bien placé quand l'angle du support affleure exactement le coin intérieur du L.
    - croix   : fenêtre en croix -> on reporte la croix au crayon sur le support (aux cotes données
      quand la feuille est posée dans le support), puis on aligne chaque couche dessus.
    - rond    : trou pour pions de calage (diamètre = taille).
    3 coins : l'angle bas-droit est omis, ce qui sert de détrompeur.
    """
    p = res.params
    a = p.reg_size_mm
    t = max(1.0, min(a / 5, 2.5))
    shape, pts, band, warns = _reg_layout(res)
    shapes = []
    for _name, px, py, sx, sy in pts:
        if shape == "equerre":
            rel = [(-t, -t), (a, -t), (a, 0), (0, 0), (0, a), (-t, a)]
            shapes.append({"type": "poly", "pts": [(px + sx * u, py + sy * v) for u, v in rel]})
        elif shape == "rond":
            shapes.append({"type": "circle", "cx": px, "cy": py, "r": a / 2})
        else:
            half, w = a / 2, t / 2
            rel = [(-w, -half), (w, -half), (w, -w), (half, -w), (half, w), (w, w),
                   (w, half), (-w, half), (-w, w), (-half, w), (-half, -w), (-w, -w)]
            shapes.append({"type": "poly", "pts": [(px + u, py + v) for u, v in rel]})
    if p.layer_notches and layer_index and band >= 5:
        s = min(2.0, band / 6)
        gap = s * 0.8
        total = layer_index * s + (layer_index - 1) * gap
        xs = res.sheet_mm[0] / 2 - total / 2
        cy = band / 2
        for k in range(layer_index):
            x = xs + k * (s + gap)
            shapes.append({"type": "poly", "pts": [(x, cy - s / 2), (x + s, cy - s / 2),
                                                   (x + s, cy + s / 2), (x, cy + s / 2)]})
    return shapes, warns


def positioning(res: Result) -> dict:
    """Cotes à la règle (feuille posée dans le support), repère = coin haut-gauche du support (mm).

    On trace au crayon une croix sur le support à chaque cote, puis on pose chaque couche en
    alignant ses fenêtres en croix sur ces traits.
    """
    p = res.params
    sw, sh = res.support_mm
    sx0, sy0, sx1, sy1 = res.sheet_rect_mm
    shape, pts, _band, _w = _reg_layout(res)
    marks = []
    for name, px, py, _sx, _sy in pts:
        x, y = sx0 + px, sy0 + py
        marks.append({"coin": name, "x": round(x, 1), "y": round(y, 1),
                      "depuis_droite": round(sw - x, 1), "depuis_bas": round(sh - y, 1),
                      "sur_support": bool(0 <= x <= sw and 0 <= y <= sh)})
    return {
        "mode": p.sheet_mode,
        "repere": "coin haut-gauche du support",
        "forme": shape,
        "feuille": {"gauche": round(sx0, 1), "haut": round(sy0, 1),
                    "droite": round(sw - sx1, 1), "bas": round(sh - sy1, 1),
                    "largeur": round(sx1 - sx0, 1), "hauteur": round(sy1 - sy0, 1)},
        "reperes": marks,
    }


# --------------------------------------------------------------------------
# 6. Aperçus
# --------------------------------------------------------------------------

def simulate_sheet(res: Result) -> np.ndarray:
    """Simulation du rendu à l'aérographe sur la feuille (seul endroit où la peinture passe)."""
    p = res.params
    first = res.layers[0].opening if res.layers else None
    shape = first.shape if first is not None else (int(round(res.sheet_mm[1] * p.px_per_mm)),
                                                   int(round(res.sheet_mm[0] * p.px_per_mm)))
    canvas = np.empty(shape + (3,), np.float32)
    canvas[:] = res.support_color
    sig = max(0.3, p.spray_mm * p.px_per_mm)
    for L in res.layers:
        mask = cv2.GaussianBlur(L.opening.astype(np.float32) / 255.0, (0, 0), sig)
        a = (0.97 * mask)[..., None]
        canvas = canvas * (1 - a) + L.color.astype(np.float32) * a
    return np.clip(canvas, 0, 255).astype(np.uint8)


def support_overlap(res: Result) -> tuple[tuple, tuple]:
    """Zone commune feuille / support : (x0, y0, x1, y1) dans le support et décalage vers la feuille."""
    SW, SH = res.support_px
    ox, oy = res.sup_off_px
    if res.layers:
        Hs, Ws = res.layers[0].opening.shape
    else:
        Ws, Hs = int(round(res.sheet_mm[0] * res.params.px_per_mm)), int(round(res.sheet_mm[1] * res.params.px_per_mm))
    x0, y0 = max(0, -ox), max(0, -oy)
    x1, y1 = min(SW, Ws - ox), min(SH, Hs - oy)
    return (x0, y0, max(x0, x1), max(y0, y1)), (ox, oy)


def sheet_to_support(res: Result, arr: np.ndarray, fill=0) -> np.ndarray:
    """Recopie un tableau « feuille » à la taille du support (le reste est rempli par `fill`)."""
    SW, SH = res.support_px
    out = np.empty((SH, SW) + arr.shape[2:], arr.dtype)
    out[:] = fill
    (x0, y0, x1, y1), (ox, oy) = support_overlap(res)
    if x1 > x0 and y1 > y0:
        out[y0:y1, x0:x1] = arr[y0 + oy:y1 + oy, x0 + ox:x1 + ox]
    return out


def simulate(res: Result) -> np.ndarray:
    """Simulation du rendu à l'aérographe sur tout le support."""
    return sheet_to_support(res, simulate_sheet(res), res.support_color.astype(np.uint8))


def image_sim(res: Result, sheet_sim: np.ndarray | None = None) -> np.ndarray:
    """Rendu simulé de la seule zone de l'image."""
    sim = simulate_sheet(res) if sheet_sim is None else sheet_sim
    H, W = res.prepared.labels.shape
    X0, Y0 = res.img_off_px
    return sim[Y0:Y0 + H, X0:X0 + W]


def image_crop(res: Result, sim: np.ndarray) -> np.ndarray:
    """Zone de l'image dans un rendu à la taille du support."""
    H, W = res.prepared.labels.shape
    ox, oy = res.prepared.off_px
    return sim[oy:oy + H, ox:ox + W]


def quantized_view(res: Result) -> np.ndarray:
    pal = res.prepared.palette.copy()
    if res.support_label is not None:
        pal[res.support_label] = res.support_color
    return pal[res.prepared.labels]


def layer_view(res: Result, L: Layer, sheet_bgr=(200, 211, 220)) -> np.ndarray:
    """Vue du pochoir : matière, ouvertures, ponts (rouge), détails perdus (orange), calage."""
    p = res.params
    ppm = p.px_per_mm
    H, W = res.prepared.labels.shape
    X0, Y0 = res.img_off_px
    SW, SH = res.support_px
    ox, oy = res.sup_off_px
    op = L.opening > 0
    img = np.empty(op.shape + (3,), np.uint8)
    img[:] = sheet_bgr
    # emprise du support (repère visuel, non découpé)
    cv2.rectangle(img, (ox, oy), (ox + SW - 1, oy + SH - 1), (150, 150, 150), 1)
    light = (L.color.astype(np.float32) * 0.55 + 255 * 0.45).astype(np.uint8)
    img[op] = light
    edge = cv2.morphologyEx(L.opening, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    img[edge] = (40, 40, 40)
    lost = np.zeros(op.shape, bool)
    lost[Y0:Y0 + H, X0:X0 + W] = L.lost > 0
    sel = lost & ~edge
    img[sel] = (img[sel] * 0.4 + np.array((0, 140, 255)) * 0.6).astype(np.uint8)
    bw = max(1, int(round(p.bridge_width_mm * ppm)))
    for (x1, y1, x2, y2) in L.bridges:
        cv2.line(img, (x1, y1), (x2, y2), (40, 40, 230), thickness=bw)
    shapes, _ = registration_shapes(res, L.index)
    for s in shapes:
        if s["type"] == "poly":
            pts = (np.array(s["pts"]) * ppm).round().astype(np.int32)
            cv2.fillPoly(img, [pts], (255, 255, 255))
            cv2.polylines(img, [pts], True, (40, 40, 40), 1)
        else:
            c = (int(round(s["cx"] * ppm)), int(round(s["cy"] * ppm)))
            r = int(round(s["r"] * ppm))
            cv2.circle(img, c, r, (255, 255, 255), -1)
            cv2.circle(img, c, r, (40, 40, 40), 1)
    if p.sheet_outline:
        cv2.rectangle(img, (0, 0), (img.shape[1] - 1, img.shape[0] - 1), (40, 40, 40), 1)
    return img


def delta_e(res: Result, sheet_sim: np.ndarray | None = None) -> float:
    """Écart moyen (ΔE Lab) entre l'image d'origine et le rendu simulé, sur la zone de l'image."""
    a = cv2.cvtColor(res.prepared.resized.astype(np.float32) / 255, cv2.COLOR_BGR2LAB)
    b = cv2.cvtColor(image_sim(res, sheet_sim).astype(np.float32) / 255, cv2.COLOR_BGR2LAB)
    if res.prepared.gray:
        return float(np.abs(a[..., 0] - b[..., 0]).mean())
    return float(np.sqrt(((a - b) ** 2).sum(axis=2)).mean())


def layer_stats(L: Layer) -> dict:
    length = 0.0
    nodes = 0
    for pts in L.paths:
        d = np.diff(np.vstack([pts, pts[:1]]), axis=0)
        length += float(np.hypot(d[:, 0], d[:, 1]).sum())
        nodes += len(pts)
    return {
        "paths": len(L.paths),
        "nodes": nodes,
        "bridges": len(L.bridges),
        "islands": L.islands,
        "kind": L.kind,
        "short_islands": L.short_islands,
        "cut_length_m": round(length / 1000, 2),
        "lost_pct": round(100 * float((L.lost > 0).mean()), 1),
    }
