"""Processing pipeline: image -> cuttable stencil layers.

All physical quantities are in millimetres; the computation runs on a raster
grid of `px_per_mm` pixels per millimetre, then the outlines are vectorised
in mm.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, fields, replace

import cv2
import numpy as np


OUTLINE_METHODS = ("canny", "xdog", "ridge")
OUTLINE_TARGETS = ("stencil", "darkest", "nearest")


@dataclass
class Params:
    # Support (painted surface)
    support_w_mm: float = 210.0
    support_h_mm: float = 297.0
    support_color: str = "#ffffff"
    inner_margin_mm: float = 10.0  # reference margin for "fit to support"
    # Crop of the source image (fractions 0..1)
    crop_x: float = 0.0
    crop_y: float = 0.0
    crop_w: float = 1.0
    crop_h: float = 1.0
    # Layout on the support
    image_scale: float = 100.0     # % of the "fit to support" size
    image_height_factor: float = 1.0  # vertical stretch (1 = original proportions)
    image_pos_x: float = 50.0      # image centre, as % of the support width
    image_pos_y: float = 50.0      # image centre, as % of the support height
    px_per_mm: float = 6.0
    # Image preprocessing (before simplification)
    pre_auto_levels: bool = False  # automatic levels stretch (luminance)
    pre_clahe: float = 0.0         # local contrast (CLAHE), 0..100
    pre_gamma: float = 1.0         # midtones: > 1 lightens, < 1 darkens
    pre_saturation: float = 100.0  # colour saturation, % (100 = unchanged)
    pre_sharpen: float = 0.0       # sharpness (unsharp mask), 0..100
    pre_remove_bg: bool = False    # removed background ("subject" mask + GrabCut): left as bare support
    manual_thresholds: bool = False  # luminance thresholds chosen by hand between tones
    thresholds: str = ""           # L* thresholds (0..100) separated by commas
    # Simplification
    n_layers: int = 3              # number of stencils
    color_mode: str = "auto"       # auto | color | gray
    detail: float = 50.0           # 0 (very simplified) .. 100 (very detailed)
    layering: str = "cumulative"   # cumulative | exclusive
    skip_support: bool = True      # the tone closest to the support gets no stencil
    protect_lines: bool = False    # thin strokes (eyes, eyebrows…) escape the majority filter
    # Outline stencil (key details faded by the airbrush blur)
    outline: bool = False
    outline_method: str = "canny"       # canny (sharp edges) | xdog (drawn line) | ridge (thin lines, centre line)
    # where the lines go: stencil = separate outline stencil painted last;
    # darkest = into the darkest layer; nearest = into the layer of the nearest (darker) tone
    outline_target: str = "stencil"
    outline_sensitivity: float = 50.0   # 0 = only the strongest details .. 100 = many details (progressive)
    outline_width_mm: float = 0.8       # line width (at least the material's minimum opening)
    outline_min_length_mm: float = 4.0  # minimum line length
    outline_auto_color: bool = True     # auto colour = tone with the most contrast against the support
    outline_color: str = "#1e1e1e"
    # Paint colours chosen for the layers: "1=#rrggbb;3=#rrggbb" (layer number -> colour).
    # Layers not listed keep their computed tone.
    layer_colors: str = ""
    # Material constraints
    min_opening_mm: float = 0.8    # minimum width of an opening
    min_strip_mm: float = 1.0      # minimum width of a material strip
    bridge_width_mm: float = 1.5
    min_area_mm2: float = 2.5
    double_bridge_area_mm2: float = 400.0
    min_bridges: int = 1           # minimum number of bridges per island (1 to 4)
    bridges: bool = True
    # Merging zones instead of bridges (0 = off): see merge_zones
    merge_amount: float = 0.0      # 0..100, progressive scale of the largest visible change accepted
    merge_channel_mm: float = 2.5  # A: channels of opening narrower than this may be closed
    merge_channels: bool = True    # A: close narrow channels
    merge_islands: bool = True     # B: remove small islands
    # Vectorisation
    tolerance_mm: float = 0.12
    smooth_curves: bool = True
    # Stencil sheet:
    #   around = support + margin all around (registered on the support corners)
    #   fit    = inside the support, fitted to the design + border (registered on crosses drawn on the support)
    #   fixed  = inside the support, fixed size centred on the design
    sheet_mode: str = "around"
    margin_mm: float = 15.0
    sheet_border_mm: float = 20.0
    sheet_w_mm: float = 304.8
    sheet_h_mm: float = 304.8
    reg_dims: bool = True          # ruler dimensions of the crosses (sheet inside the support)
    sheet_outline: bool = True
    machine_max_mm: float = 305.0  # usable cutting width of the machine
    mat_w_mm: float = 304.8        # cutting mat (0 = no mat: only the width matters)
    mat_h_mm: float = 304.8
    mat_orient: str = "portrait"   # portrait = feed direction into the machine; landscape = mat turned a quarter turn
    # Registration
    reg_corners: int = 4           # 0, 3 (keyed) or 4
    reg_shape: str = "equerre"     # equerre | croix | rond
    reg_size_mm: float = 10.0
    layer_notches: bool = True     # notches giving the layer number
    # Preview
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
        p.outline_method = p.outline_method if p.outline_method in OUTLINE_METHODS else "canny"
        p.outline_target = p.outline_target if p.outline_target in OUTLINE_TARGETS else "stencil"
        p.pre_clahe = float(np.clip(p.pre_clahe, 0, 100))
        p.pre_gamma = float(np.clip(p.pre_gamma, 0.3, 3.0))
        p.pre_saturation = float(np.clip(p.pre_saturation, 0, 300))
        p.pre_sharpen = float(np.clip(p.pre_sharpen, 0, 100))
        p.outline_width_mm = float(np.clip(p.outline_width_mm, 0.2, 10))
        p.merge_amount = float(np.clip(p.merge_amount, 0, 100))
        p.merge_channel_mm = float(np.clip(p.merge_channel_mm, 0.3, 30))
        p.outline_min_length_mm = float(np.clip(p.outline_min_length_mm, 0, 200))
        return p


@dataclass
class Layout:
    src_rect: tuple    # (x0, y0, x1, y1) source image pixels actually used
    img_mm: tuple      # (width, height) of the whole image (after crop) on the support
    pos_mm: tuple      # (x, y) top-left corner of the whole image on the support
    vis_mm: tuple      # (x0, y0, x1, y1) visible part (inside the support)
    sheet_mm: tuple = (0.0, 0.0, 0.0, 0.0)  # (x0, y0, x1, y1) stencil sheet, support coordinates


def sheet_rect(p: Params, vis_mm: tuple) -> tuple[float, float, float, float]:
    """Stencil sheet in support coordinates (mm), according to the chosen mode."""
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
    """Places the cropped image on the support.

    Reference size (100 %) = image fitted in the support minus the inner margin.
    Parts overflowing the support are cropped.
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
    # Stencil sheet; at fixed size, the design is limited to the inside of the sheet (minus the border)
    sh_rect = sheet_rect(p, (vx0, vy0, vx1, vy1))
    if p.sheet_mode == "fixed":
        b = min(p.sheet_border_mm, (sh_rect[2] - sh_rect[0]) / 2 - 2, (sh_rect[3] - sh_rect[1]) / 2 - 2)
        ix0, iy0, ix1, iy1 = sh_rect[0] + b, sh_rect[1] + b, sh_rect[2] - b, sh_rect[3] - b
        nvx0, nvy0, nvx1, nvy1 = max(vx0, ix0), max(vy0, iy0), min(vx1, ix1), min(vy1, iy1)
        if max(nvx0 - vx0, nvy0 - vy0, vx1 - nvx1, vy1 - nvy1) > 0.05:
            warnings.append(f"Le motif est plus grand que la feuille ({p.sheet_w_mm:.0f} × {p.sheet_h_mm:.0f} mm, "
                            f"bordure {b:.0f} mm comprise) : il est rogné aux bords de la feuille.")
        vx0, vy0, vx1, vy1 = nvx0, nvy0, max(nvx1, nvx0 + 2), max(nvy1, nvy0 + 2)
    # part of the source matching the visible area
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
        # physical dimensions (width = machine direction), then oriented as on the support
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
# Utilities
# --------------------------------------------------------------------------

def decode_image(data: bytes) -> np.ndarray:
    """Decodes an image (transparency handled -> white background)."""
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
    # reasonable limit for memory
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
    """Removes (white) components with an area < min_px."""
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
# 1-2. Preprocessing + quantisation
# --------------------------------------------------------------------------

@dataclass
class Prepared:
    resized: np.ndarray      # resized and preprocessed image (simplification reference)
    labels: np.ndarray       # label map, sorted from lightest (0) to darkest
    palette: np.ndarray      # BGR colours sorted light -> dark
    gray: bool
    off_px: tuple = (0, 0)   # position of the visible part on the support (px)
    raw: np.ndarray | None = None   # same area, original image without preprocessing
    hist: list = None        # L* luminance histogram (100 bins, 0..1) of the smoothed image
    auto_thresholds: list = None    # L* thresholds the automatic computation would have chosen
    thresholds_used: list = None    # thresholds actually applied (manual) or None
    fg: np.ndarray | None = None    # subject (True) / removed background (False), computed image size


def preprocess_active(p: Params) -> bool:
    return bool(p.pre_auto_levels or p.pre_clahe > 0 or abs(p.pre_gamma - 1) > 1e-3
                or abs(p.pre_saturation - 100) > 1e-3 or p.pre_sharpen > 0)


def preprocess_image(img: np.ndarray, p: Params, px_per_mm: float | None = None) -> np.ndarray:
    """Auto levels, local contrast (CLAHE), gamma and sharpening on the luminance (Lab);
    saturation on the a, b colour channels. `px_per_mm`: image scale (sharpening radius)."""
    if not preprocess_active(p):
        return img
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    L = lab[..., 0]
    if p.pre_auto_levels:
        lo, hi = np.percentile(L, (0.5, 99.5))
        if hi - lo > 5:
            L = np.clip((L.astype(np.float32) - lo) * 255.0 / (hi - lo), 0, 255).astype(np.uint8)
    if p.pre_clahe > 0:
        clahe = cv2.createCLAHE(clipLimit=1.0 + p.pre_clahe / 100.0 * 4.0, tileGridSize=(8, 8))
        L = clahe.apply(L)
    if abs(p.pre_gamma - 1) > 1e-3:
        lut = np.clip(((np.arange(256) / 255.0) ** (1.0 / p.pre_gamma)) * 255 + 0.5, 0, 255).astype(np.uint8)
        L = lut[L]
    if p.pre_sharpen > 0:
        # unsharp mask: radius ~0.3 mm at stencil scale (1.5 px on the source image)
        sig = max(0.8, 0.3 * px_per_mm) if px_per_mm else 1.5
        Lf = L.astype(np.float32)
        L = np.clip(Lf + (Lf - cv2.GaussianBlur(Lf, (0, 0), sig)) * (p.pre_sharpen / 100.0 * 1.5),
                    0, 255).astype(np.uint8)
    lab[..., 0] = L
    if abs(p.pre_saturation - 100) > 1e-3:
        ab = lab[..., 1:].astype(np.float32) - 128.0
        lab[..., 1:] = np.clip(ab * (p.pre_saturation / 100.0) + 128.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def grabcut_subject(img: np.ndarray, painted: np.ndarray, max_side: int = 700) -> np.ndarray:
    """Cuts out the subject: `painted` (0/255, image size) = area roughly painted around the subject.

    Outside the painted area = sure background; inside = probable subject, refined by GrabCut on a
    downscaled copy, then brought back to the image size. Returns a boolean mask (True = subject).
    """
    h, w = img.shape[:2]
    s = min(1.0, max_side / max(h, w))
    sw, sh = max(1, round(w * s)), max(1, round(h * s))
    small = cv2.resize(img, (sw, sh), interpolation=cv2.INTER_AREA)
    pm = cv2.resize(painted, (sw, sh), interpolation=cv2.INTER_NEAREST) > 0
    if not pm.any():
        return np.ones((h, w), bool)
    if pm.all():                      # no background designated: nothing to remove
        return np.ones((h, w), bool)
    mask = np.where(pm, cv2.GC_PR_FGD, cv2.GC_BGD).astype(np.uint8)
    # the core of the painted area (more than ~5 % of the image size from its edge) is surely the
    # subject: GrabCut cannot remove it, it only adjusts the band near the stroke
    r = max(3, int(round(0.05 * min(sw, sh))))
    core = cv2.erode(pm.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0
    mask[core] = cv2.GC_FGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(small, mask, None, bgd, fgd, 6, cv2.GC_INIT_WITH_MASK)
        fg = (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)
    except cv2.error:
        fg = pm
    # cleanup: small crumbs removed, small holes filled
    k = np.ones((3, 3), np.uint8)
    fg8 = cv2.morphologyEx(fg.astype(np.uint8) * 255, cv2.MORPH_OPEN, k)
    fg8 = cv2.morphologyEx(fg8, cv2.MORPH_CLOSE, k)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg8, connectivity=8)
    if n > 2:                          # keep the non-negligible pieces (>= 1 % of the largest)
        big = stats[1:, cv2.CC_STAT_AREA].max()
        keep = np.zeros(n, bool)
        keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= 0.01 * big
        fg8 = np.where(keep[lab], 255, 0).astype(np.uint8)
    full = cv2.resize(fg8, (w, h), interpolation=cv2.INTER_LINEAR)
    return full > 127


def parse_layer_colors(txt: str) -> dict[int, np.ndarray]:
    out = {}
    for part in str(txt or "").replace(",", ";").split(";"):
        k, _, v = part.partition("=")
        v = v.strip()
        try:
            if len(v) == 7 and v.startswith("#"):
                out[int(k)] = hex_to_bgr(v).astype(np.uint8)
        except ValueError:
            pass
    return out


def parse_thresholds(txt: str) -> list[float]:
    out = []
    for t in str(txt or "").replace(";", ",").split(","):
        try:
            out.append(float(np.clip(float(t), 0.5, 99.5)))
        except ValueError:
            pass
    return sorted(out)


def prepare(img: np.ndarray, p: Params, lay: Layout, fg_src: np.ndarray | None = None) -> Prepared:
    """`fg_src`: subject mask at the size of the source image (removed background), or None."""
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
    raw = cv2.resize(src, (W, H), interpolation=interp)
    resized = preprocess_image(raw, p, ppm)
    fg = None
    if p.pre_remove_bg and fg_src is not None:
        fg = cv2.resize(fg_src[sy0:sy1, sx0:sx1].astype(np.uint8) * 255, (W, H),
                        interpolation=cv2.INTER_LINEAR) > 127
        if not fg.any() or fg.all():
            fg = None

    gray = is_grayscale(src) if p.color_mode == "auto" else p.color_mode == "gray"
    d = p.detail / 100.0

    # Edge-preserving smoothing, stronger when detail is low
    sm = resized.copy()
    iters = 1 + int(round((1 - d) * 3))
    for _ in range(iters):
        sm = cv2.bilateralFilter(sm, 7, 15 + (1 - d) * 55, 3 + (1 - d) * 6)

    k = p.n_layers + (1 if p.skip_support else 0)
    lab = cv2.cvtColor(sm, cv2.COLOR_BGR2LAB).astype(np.float32)
    L100 = lab[..., 0] * (100.0 / 255.0)
    feat = lab[..., :1] if gray else lab
    X = feat.reshape(-1, feat.shape[-1])

    # tones learnt on the subject only when the background is removed
    pool = np.flatnonzero(fg.ravel()) if fg is not None else np.arange(len(X))
    rng = np.random.default_rng(0)
    idx = pool[rng.choice(len(pool), size=min(len(pool), 60000), replace=False)]
    cv2.setRNGSeed(0)
    k_eff = int(min(k, len(np.unique(X[idx].round(), axis=0))))
    k_eff = max(1, k_eff)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 0.2)
    _, _, centers = cv2.kmeans(X[idx], k_eff, None, crit, 3, cv2.KMEANS_PP_CENTERS)

    # L* luminance (0..100) of the smoothed image: histogram and equivalent automatic thresholds
    Lh = L100[fg] if fg is not None else L100.ravel()
    hist = np.bincount(np.clip(Lh, 0, 99.999).astype(np.int32), minlength=100).astype(np.float64)
    hist = (hist / max(1.0, hist.max())).round(4).tolist()
    cl = np.sort(centers[:, 0] * (100.0 / 255.0))
    auto_thr = [round(float((a + b) / 2), 1) for a, b in zip(cl[:-1], cl[1:])]

    thr = parse_thresholds(p.thresholds) if p.manual_thresholds else []
    if thr and len(thr) == k - 1:
        # Manual thresholds: each tone = a luminance range (controlled posterisation)
        labels = np.digitize(L100, thr).astype(np.int32)
        n_lab = k
    else:
        thr = []
        # Assign every pixel to the nearest centre
        best = np.full(len(X), np.inf, np.float32)
        labels = np.zeros(len(X), np.int32)
        for i, c in enumerate(centers):
            dist = ((X - c) ** 2).sum(axis=1)
            upd = dist < best
            best[upd] = dist[upd]
            labels[upd] = i
        labels = labels.reshape(H, W)
        n_lab = len(centers)

    # Majority filter (shape simplification)
    r = (0.15 + (1 - d) * 1.6) * p.px_per_mm
    before = labels
    labels = majority_filter(labels, n_lab, r)
    if p.protect_lines:
        # thin strokes (dark or light) keep their own tone instead of being swallowed by the area around
        prot = thin_features(L100, p.px_per_mm)
        if fg is not None:
            prot &= fg
        labels = np.where(prot, before, labels)

    # Actual mean colours (on the smoothed image), sorted light -> dark
    lab_full = lab.reshape(H, W, 3)
    inside = fg if fg is not None else np.ones((H, W), bool)
    used = [i for i in range(n_lab) if np.any((labels == i) & inside)]
    if not used:
        used, inside = [i for i in range(n_lab) if np.any(labels == i)], np.ones((H, W), bool)
    means = np.array([lab_full[(labels == i) & inside].mean(axis=0) for i in used], np.float32)
    if gray:
        means[:, 1:] = 128
    order = np.argsort(-means[:, 0])
    remap = np.zeros(n_lab, np.int32)
    for i in range(n_lab):            # labels absent from the subject: attached to the nearest one
        if i not in used:
            remap[i] = int(np.argmin(np.abs(means[order][:, 0] - (centers[i, 0] if i < len(centers) else 128))))
    for new, old_pos in enumerate(order):
        remap[used[old_pos]] = new
    labels = remap[labels]
    palette = lab_to_bgr(means[order])
    return Prepared(resized=resized, labels=labels, palette=palette, gray=gray, off_px=(ox, oy),
                    raw=raw, hist=hist, auto_thresholds=auto_thr, thresholds_used=thr or None, fg=fg)


def recommend_layers(img: np.ndarray, gray: bool, skip_lightest: bool, max_colors: int = 9) -> dict:
    """Recommends a number of stencils for an image.

    The (downscaled) image is quantised with k = 1..max_colors tones and the mean difference
    (ΔE) to the image is measured. We stop at the smallest k that:
      - reaches a difference judged "good" (ΔE <= target), or
      - is hardly improved by one more tone (elbow of the curve), or
      - whose next tone would only cover a negligible area.
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

    curve = []  # (k, ΔE, share of the smallest tone)
    for k in range(1, min(max_colors, uniq) + 1):
        cv2.setRNGSeed(0)
        _, lab_k, centers = cv2.kmeans(X, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
        lab_k = lab_k.ravel()
        err = float(np.sqrt(((X - centers[lab_k]) ** 2).sum(axis=1)).mean())
        share = float(np.bincount(lab_k, minlength=k).min() / len(lab_k))
        curve.append((k, err, share))

    # Truly distinct tones: centres of k max merged when close (ΔE < 12)
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
# 3-4. Layers + cutting constraints
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


def merge_area_mm2(amount: float) -> float:
    """Largest visible area (mm²) a merge may change, from the "merge instead of bridges" setting
    (0..100, progressive scale): 0 = never merge, ~0.3 mm² at 1, ~5 mm² at 50, 90 mm² at 100."""
    if amount <= 0:
        return 0.0
    return 0.3 * 300.0 ** (min(amount, 100.0) / 100.0)


def merge_zones(opening: np.ndarray, p: Params, hidden: np.ndarray | None = None,
                weight: float = 1.0, protect: np.ndarray | None = None) -> tuple[np.ndarray, int]:
    """Holds material islands by merging zones instead of bridges, when the change is small enough.

    A. closes a narrow channel of opening (narrower than `merge_channel_mm`) separating an island
       from the rest of the material: the island is welded along the whole narrow part;
    B. removes a small island: the openings around it merge and it gets painted.
    Cost of a merge = changed area not repainted by a later layer (`hidden`) x `weight` (visibility
    of this layer's paint over what is under it, 0..1); merges are applied from the cheapest, while
    the cost stays under `merge_area_mm2(p.merge_amount)` and the merge links separate groups.
    `protect`: areas no merge may change (key-detail lines cut into the layer).
    Modifies `opening` in place; returns (mask of the changed areas, number of merges).
    """
    merged = np.zeros(opening.shape, bool)
    amax = merge_area_mm2(p.merge_amount) * p.px_per_mm ** 2
    if amax <= 0 or not (p.merge_channels or p.merge_islands):
        return merged, 0
    material = opening == 0
    n, lab = cv2.connectedComponents(material.astype(np.uint8), connectivity=4)
    main = int(lab[0, 0])
    if n <= 2:                          # no island
        return merged, 0
    visible = np.ones(opening.shape, np.float64) if hidden is None else (~hidden).astype(np.float64)
    w = max(float(weight), 0.05)
    actions = []                        # (cost, kind, index, material labels linked)
    if p.merge_islands:
        vis_lab = np.bincount(lab.ravel(), visible.ravel(), minlength=n) * w
        ring = set()
        if protect is not None:          # islands bordering a protected line are kept
            near = (cv2.dilate(protect.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & material
            ring = set(np.unique(lab[near]).tolist())
        for i in range(1, n):
            if i in ring:
                continue
            if i != main and vis_lab[i] <= amax:
                actions.append((float(vis_lab[i]), 1, i, (i,)))
    fill = flab = fstats = None
    if p.merge_channels:
        r = p.merge_channel_mm * p.px_per_mm / 2
        if r >= 0.5:
            closed = cv2.morphologyEx(material.astype(np.uint8), cv2.MORPH_CLOSE, disk(r)) > 0
            fill = closed & ~material
            if protect is not None:
                fill &= ~protect
            nf, flab, fstats, _ = cv2.connectedComponentsWithStats(fill.astype(np.uint8), connectivity=8)
            if nf > 1:
                vis_f = np.bincount(flab.ravel(), visible.ravel(), minlength=nf) * w
                # material labels touching each filled part (4-neighbours)
                pad = np.pad(lab, 1)
                codes = []
                for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    nb = pad[1 + dy:1 + dy + lab.shape[0], 1 + dx:1 + dx + lab.shape[1]]
                    m = (flab > 0) & (nb > 0)
                    codes.append(flab[m].astype(np.int64) * n + nb[m])
                codes = np.unique(np.concatenate(codes))
                touch: dict[int, list] = {}
                for c in codes.tolist():
                    touch.setdefault(c // n, []).append(c % n)
                for j, labs in touch.items():
                    if len(labs) >= 2 and vis_f[j] <= amax:
                        actions.append((float(vis_f[j]), 0, j, tuple(labs)))
    if not actions:
        return merged, 0

    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    size = [1] * n
    removed = set()                     # islands removed (B): they no longer link anything
    count = 0
    filled_any = False
    for cost, kind, idx, labs in sorted(actions):
        if kind == 1:                   # B: remove an island still alone (not linked yet)
            i = labs[0]
            if i in removed or find(i) != i or size[i] != 1 or find(i) == find(main):
                continue
            x, y, bw, bh = cv2.boundingRect((lab == i).astype(np.uint8))
            sub = lab[y:y + bh, x:x + bw] == i
            opening[y:y + bh, x:x + bw][sub] = 255
            merged[y:y + bh, x:x + bw] |= sub
            removed.add(i)
            count += 1
        else:                           # A: close a channel if it links separate groups
            roots = {find(a) for a in labs if a not in removed}
            if len(roots) < 2:
                continue
            x, y, bw, bh = fstats[idx, :4]
            sub = flab[y:y + bh, x:x + bw] == idx
            opening[y:y + bh, x:x + bw][sub] = 0
            merged[y:y + bh, x:x + bw] |= sub
            rl = list(roots)
            for a in rl[1:]:
                ra, rb = find(rl[0]), find(a)
                if ra != rb:
                    parent[rb] = ra
                    size[ra] += size[rb]
            filled_any = True
            count += 1
    if filled_any:
        # slivers of opening left too thin at the ends of the closed channels: material too
        ro = p.min_opening_mm * p.px_per_mm / 2
        if ro >= 0.5:
            near = cv2.dilate(merged.astype(np.uint8), disk(ro * 2 + 1)) > 0
            kept = cv2.morphologyEx(opening, cv2.MORPH_OPEN, disk(ro)) > 0
            sliver = near & (opening > 0) & ~kept
            if protect is not None:
                sliver &= ~protect
            opening[sliver] = 0
            merged |= sliver
    return merged, count


def add_bridges(opening: np.ndarray, p: Params, hidden: np.ndarray | None = None) -> list[tuple]:
    """Connects every material island to the frame. Modifies `opening` in place.

    `hidden`: mask of the areas repainted by a later layer;
    a bridge running there will be invisible in the final result -> preferred.
    Returns the list of bridges [(x1, y1, x2, y2)] in pixels.
    """
    ppm = p.px_per_mm
    bw = max(1, int(round(p.bridge_width_mm * ppm)))
    bridges = []
    double_px = p.double_bridge_area_mm2 * ppm * ppm
    n_islands = None
    short_islands = 0  # islands that could not get the requested number of bridges

    for _ in range(2000):
        # One pass = components and distance map computed ONCE, then all pending islands
        # processed from nearest to farthest from the frame (much faster than recomputing
        # everything after each island). A bridge may stop on another island (chain): both
        # then form a group, linked to the frame in the next pass.
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
        # distance to the frame + nearest frame point of every pixel (a single pass)
        dist, near_lbl = cv2.distanceTransformWithLabels(src, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        zy, zx = np.nonzero(src == 0)
        near = NearestMain(is_main, near_lbl, zx, zy)
        order = []
        for i in pending:
            x, y, w, h, _a = stats[i]
            sub = np.where(lab[y:y + h, x:x + w] == i, dist[y:y + h, x:x + w], np.inf)
            j = int(np.argmin(sub))
            order.append((float(sub.flat[j]), i, x + j % w, y + j // w))
        order.sort()
        # only islands close to the frame are processed in this pass: farther ones wait
        # for their neighbours to be connected (shorter, chained bridges)
        reach = order[0][0] * 1.5 + 4 * ppm
        touched = set()              # islands already connected to another one during this pass
        drawn = False
        for dv, i, px, py in order:
            if dv > reach:
                break
            if i in touched:
                continue
            want = max(p.min_bridges, 2 if stats[i, cv2.CC_STAT_AREA] > double_px else 1)
            cands = _candidates(lab, i, stats[i], cents[i], dist, near, hidden, dv, ppm,
                                wide=want > 1, bw=bw)
            if not cands or min(c[0] for c in cands) >= 1e6:
                # no clean bridge near the island: search its whole outline, with no length limit
                far = _candidates(lab, i, stats[i], cents[i], dist, near, hidden, dv, ppm,
                                  wide=want > 1, bw=bw, unlimited=True)
                if far and min(c[0] for c in far) < 1e6:
                    cands = far
            if not cands:
                q = near(px, py, dv)
                if q:
                    c = _clip_bridge(lab, i, px, py, q, bw)
                    q = c[0] if c else q
                cands = [(dv, (px, py), q, 0.0)] if q else []
            chosen = _spread(cands, want)
            if len(chosen) < want:
                short_islands += 1
            for _s, (ax, ay), q, _a in chosen:
                if q is not None and (ax, ay) != q:
                    cv2.line(opening, (ax, ay), q, 0, thickness=bw, lineType=cv2.LINE_8)
                    bridges.append((ax, ay, q[0], q[1]))
                    drawn = True
                    other = int(lab[q[1], q[0]])
                    if other not in (0, main, i):   # landing on another island: group to connect next
                        touched.add(other)
        if not drawn:   # safety: nothing changed, avoid an endless loop
            break
    return bridges, n_islands or 0, short_islands


def _spread(cands: list, want: int) -> list:
    """Picks `want` bridges well spread around the island (angular gap), with the best score.

    "Clear" bridges come first (even if less well spread); those running along an edge
    (score >= 1e6) only complete the selection as a last resort.
    """
    clean = [c for c in cands if c[0] < 1e6]
    chosen = _spread_in(clean, want, [])
    # Not enough room around: a clear bridge close to another is better than one running along
    # an edge -> take the clear one with the widest angle from those already chosen.
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
            sep *= 0.75  # not enough room: accept closer bridges
    return chosen


class NearestMain:
    """Nearest frame point (main component) of a pixel, read from the labels of
    `distanceTransformWithLabels` (O(1)); falls back to a local search if the label is inconsistent."""

    def __init__(self, is_main, lbl, zx, zy):
        self.is_main, self.lbl, self.zx, self.zy = is_main, lbl, zx, zy

    def __call__(self, x, y, d):
        k = int(self.lbl[y, x]) - 1
        if 0 <= k < len(self.zx):
            qx, qy = int(self.zx[k]), int(self.zy[k])
            if self.is_main[qy, qx]:
                return qx, qy
        return _nearest(self.is_main, x, y, d)


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
    """Shortens the bridge [anchor -> q] so that it only crosses empty space.

    After leaving island `i`, the bridge stops on the first material it meets (frame or
    another island: islands are then chained). If it starts by crossing island `i` or
    crosses it again further on (anchor on a "back" face), the candidate is rejected (None).
    Otherwise returns (landing point, clear); clear = False if the bridge runs along or grazes material.
    """
    n = max(2, int(math.ceil(math.hypot(q[0] - ax, q[1] - ay))) + 1)
    lx = np.linspace(ax, q[0], n).round().astype(int)
    ly = np.linspace(ay, q[1], n).round().astype(int)
    v = lab[ly, lx]
    gap = np.flatnonzero(v == 0)
    if len(gap) == 0:          # material immediately adjacent
        return q, True
    s = gap[0]
    if s > 3:                  # the bridge would start by crossing the island (anchor on the far side)
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
    """Does the bridge keep away from material outside its two attachments?

    The bridge is widened by a clearance on each side; outside the attachment discs around
    the anchor (radius 1.5 x widened half width: the bridge must leave the island at more than
    ~40° from its edge) and the landing point (radius 2 x, ~30°), this band must touch no
    material. This discards bridges that run along or graze an edge, even when they stay
    entirely in empty space and look "stuck" to the island.
    """
    half = bw / 2 + max(2.0, bw / 2)          # half width + clearance
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


def _candidates(lab, i, st, cent, dist, near, hidden, dmin, ppm, max_pts=96, wide=False, bw=1,
                unlimited=False):
    """Candidate bridges from the island edge: (score, anchor, frame point, angle).

    Score = length weighted by the visible share of the bridge (not repainted afterwards).
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
    # Several bridges requested: accept longer bridges so they can be spread
    limit = np.inf if unlimited else max(3 * dmin, dmin + 12 * ppm) * (4 if wide else 1)
    ok = dd <= limit
    xs, ys, dd = xs[ok], ys[ok], dd[ok]
    if len(xs) > max_pts:
        step = len(xs) / max_pts
        sel = (np.arange(max_pts) * step).astype(int)
        # always keep the nearest point
        sel = np.unique(np.append(sel, int(np.argmin(dd))))
        xs, ys, dd = xs[sel], ys[sel], dd[sel]
    out = []
    for ax, ay, d in zip(xs.tolist(), ys.tolist(), dd.tolist()):
        q = near(ax, ay, d)
        if q is None:
            continue
        c = _clip_bridge(lab, i, ax, ay, q, bw)
        if c is None:   # the bridge would cross back over the island itself
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
        if not clean:   # runs along an edge: last resort only
            score += 1e6
        out.append((score, (ax, ay), q, math.atan2(ay - cent[1], ax - cent[0])))
    return out


# --------------------------------------------------------------------------
# 5. Vectorisation
# --------------------------------------------------------------------------

def vectorize(opening: np.ndarray, p: Params) -> list[np.ndarray]:
    """Closed outlines in mm (list of Nx2 arrays)."""
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
    index: int               # 1..n (spraying order)
    color: np.ndarray        # BGR
    target: np.ndarray       # target mask (image area)
    opening: np.ndarray      # final opening mask (whole sheet)
    lost: np.ndarray         # details lost to the constraints (image area)
    bridges: list
    paths: list              # outlines in mm (sheet coordinates)
    islands: int = 0         # number of islands connected by bridges
    short_islands: int = 0   # islands that could not get the requested minimum of bridges
    kind: str = "color"      # "color" (flat colour) or "outline" (key-detail outlines)
    merged: np.ndarray | None = None   # areas changed by merges instead of bridges (whole sheet)
    n_merged: int = 0        # number of merges (closed channels + removed islands)


@dataclass
class Result:
    params: Params
    prepared: Prepared
    layers: list
    support_color: np.ndarray    # BGR
    support_label: int | None    # tone left to the support (no stencil)
    sheet_mm: tuple              # (width, height) of the stencil sheet
    support_mm: tuple
    image_mm: tuple
    support_px: tuple            # (width, height)
    img_off_px: tuple            # (x, y) of the image in the sheet
    sup_off_px: tuple = (0, 0)   # (x, y) of the support's top-left corner in the sheet (may be < 0)
    sheet_rect_mm: tuple = (0.0, 0.0, 0.0, 0.0)  # sheet in support coordinates (x0, y0, x1, y1)
    detect_sim: np.ndarray | None = None  # simulated render the key-detail search compared against
    lines_added: int = 0         # key-detail lines merged into the colour layers
    detect_painted: np.ndarray | None = None  # layer painting each pixel before the lines were merged

    @property
    def sup_off_mm(self) -> tuple:
        return (-self.sheet_rect_mm[0], -self.sheet_rect_mm[1])


def _lab(bgr: np.ndarray) -> np.ndarray:
    arr = np.asarray(bgr, np.float32).reshape(1, -1, 3) / 255.0
    return cv2.cvtColor(arr, cv2.COLOR_BGR2LAB).reshape(-1, 3)


def layer_job(job):
    """Merges + bridges + vectorisation of one layer (module-level function: can run in another process).
    `protect`: areas no merge may change (lines added to the layer); `weight`: see merge_zones."""
    opening, hidden, p, weight, protect = job
    merged, n_merged = merge_zones(opening, p, hidden, weight, protect)
    bridges, n_isl, n_short = add_bridges(opening, p, hidden) if p.bridges else ([], 0, 0)
    return opening, bridges, n_isl, n_short, vectorize(opening, p), merged, n_merged


# Parallelism between layers: "thread" (default), "process" (separate processes), or "none" (serial)
PARALLEL = os.environ.get("STENCILIT_PARALLEL", "thread")
_POOL = None


def _pool():
    global _POOL
    if _POOL is None:
        from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
        n = max(1, min(8, (os.cpu_count() or 2) - 1))
        _POOL = ProcessPoolExecutor(n) if PARALLEL == "process" else ThreadPoolExecutor(n)
    return _POOL


def run_layer_jobs(jobs: list) -> list:
    if PARALLEL == "none" or len(jobs) < 2:
        return [layer_job(j) for j in jobs]
    try:
        return list(_pool().map(layer_job, jobs))
    except Exception:                  # pool unavailable (e.g. child process killed): serial
        return [layer_job(j) for j in jobs]


def build(prep: Prepared, p: Params, outline_region: np.ndarray | None = None) -> Result:
    """`outline_region`: boolean mask (image area) limiting the key-detail search of the
    outline stencil; None = whole image."""
    labels = prep.labels
    H, W = labels.shape
    ppm = p.px_per_mm
    SW = int(round(p.support_w_mm * ppm))
    SH = int(round(p.support_h_mm * ppm))
    # Sheet in support coordinates (the visible part of the image is derived from the preparation)
    vis = (prep.off_px[0] / ppm, prep.off_px[1] / ppm, (prep.off_px[0] + W) / ppm, (prep.off_px[1] + H) / ppm)
    sx0, sy0, sx1, sy1 = sheet_rect(p, vis)
    ox, oy = int(round(-sx0 * ppm)), int(round(-sy0 * ppm))       # support in the sheet
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
        if prep.fg is not None:            # removed background: left as bare support
            t &= prep.fg
        t = np.where(t, 255, 0).astype(np.uint8)
        targets.append(t)
        cleaned_all.append(clean_mask(t, p, extra_area))

    paints = parse_layer_colors(p.layer_colors)
    colors = [paints.get(li + 1, prep.palette[ci]) for li, ci in enumerate(color_ids)]

    def make_result(layers, **kw):
        return Result(params=p, prepared=prep, layers=layers, support_color=support, support_label=sup,
                      sheet_mm=(sheet_shape[1] / ppm, sheet_shape[0] / ppm),
                      support_mm=(SW / ppm, SH / ppm), image_mm=(W / ppm, H / ppm),
                      support_px=(SW, SH), img_off_px=(X0, Y0), sup_off_px=(ox, oy),
                      sheet_rect_mm=(sx0, sy0, sx0 + sheet_shape[1] / ppm, sy0 + sheet_shape[0] / ppm), **kw)

    region = outline_region
    if prep.fg is not None and p.outline:
        region = prep.fg if region is None else (region.astype(bool) & prep.fg)

    # Key-detail lines merged into the colour layers (instead of a separate outline stencil):
    # searched against the render of the layers before bridges, then added to the chosen layer.
    detect_sim, detect_painted, lines_added, strokes = None, None, 0, {}
    if p.outline and p.outline_target != "stencil" and color_ids:
        draft = make_result([Layer(index=li + 1, color=colors[li], target=targets[li], opening=place(c),
                                   lost=c, bridges=[], paths=[]) for li, c in enumerate(cleaned_all)])
        detect_sim = image_sim(draft)
        painted = np.full((H, W), -1, np.int32)      # last layer painting each pixel (-1 = support)
        for li, c in enumerate(cleaned_all):
            painted[c > 0] = li
        strokes, lines_added = lines_into_layers(prep, detect_sim, p, region, color_ids, painted)
        detect_painted = painted
        for li, stroke in strokes.items():
            targets[li] = targets[li] | stroke
            cleaned_all[li] = clean_mask(cleaned_all[li] | clean_mask(stroke, p), p)

    # Each layer (bridges + vectorisation) is independent of the others: computed in parallel
    jobs = []
    for li, ci in enumerate(color_ids):
        cleaned = cleaned_all[li]
        hidden = None
        if li + 1 < len(color_ids):
            later = np.zeros_like(cleaned)
            for c2 in cleaned_all[li + 1:]:
                later |= c2
            hidden = place(later) > 0
        # visibility of a merge: contrast between this paint and what shows without it
        under = colors[li - 1] if (p.layering == "cumulative" and li > 0) else support
        de = float(np.linalg.norm(_lab(colors[li]) - _lab(under)))
        protect = place(strokes[li]) > 0 if li in strokes else None
        jobs.append((place(cleaned), hidden, p, float(np.clip(de / 40.0, 0.15, 1.0)), protect))
    results = run_layer_jobs(jobs)
    layers = []
    for li, ci in enumerate(color_ids):
        opening, bridges, n_isl, n_short, paths, merged, n_merged = results[li]
        target, cleaned = targets[li], cleaned_all[li]
        layers.append(Layer(index=li + 1, color=colors[li], target=target,
                            opening=opening, lost=cv2.bitwise_xor(cleaned, target), bridges=bridges, paths=paths,
                            islands=n_isl, short_islands=n_short, merged=merged, n_merged=n_merged))
    res = make_result(layers, detect_sim=detect_sim, detect_painted=detect_painted, lines_added=lines_added)

    # Outline stencil: painted last, above all layers
    if p.outline and p.outline_target == "stencil":
        sim = res.detect_sim = image_sim(res)
        color = outline_color(prep, support, p)
        target = detect_key_details(prep, sim, p, region, outline_is_dark(color, support))
        if target.any():
            cleaned = clean_mask(target, p)
            lost = cv2.bitwise_xor(cleaned, target)
            opening = place(cleaned)
            bridges, n_isl, n_short = add_bridges(opening, p, None) if p.bridges else ([], 0, 0)
            layers.append(Layer(index=len(layers) + 1, color=color, target=target, opening=opening,
                                lost=lost, bridges=bridges, paths=vectorize(opening, p),
                                islands=n_isl, short_islands=n_short, kind="outline"))
    return res


def outline_color(prep: Prepared, support: np.ndarray, p: Params) -> np.ndarray:
    """Line colour: chosen by the user, or the palette tone with the most contrast against the support."""
    if not p.outline_auto_color:
        return hex_to_bgr(p.outline_color).astype(np.uint8)
    L_sup = _lab(support)[0, 0]
    L_pal = _lab(prep.palette)[:, 0]
    return prep.palette[int(np.argmax(np.abs(L_pal - L_sup)))]


def outline_is_dark(color: np.ndarray, support: np.ndarray) -> bool:
    """True when the outline paint is darker than the support: the lines to find are dark ones."""
    lc = _lab(np.asarray(color, np.uint8).reshape(1, 3))[0, 0]
    ls = _lab(np.asarray(support, np.uint8).reshape(1, 3))[0, 0]
    return float(lc) <= float(ls)


def _crest(resp: np.ndarray, floor: float) -> np.ndarray:
    """One-pixel-wide crest lines of a line strength map: points above `floor` that are a maximum
    across the line (non-maximum suppression along the direction of strongest curvature)."""
    g = cv2.GaussianBlur(resp, (0, 0), 1.0)
    dxx = cv2.Sobel(g, cv2.CV_32F, 2, 0, ksize=3)
    dyy = cv2.Sobel(g, cv2.CV_32F, 0, 2, ksize=3)
    dxy = cv2.Sobel(g, cv2.CV_32F, 1, 1, ksize=3)
    # direction across the crest = eigenvector of the most negative curvature
    ang = 0.5 * np.arctan2(2 * dxy, dxx - dyy) + np.pi / 2
    q = np.round(ang / (np.pi / 4)).astype(np.int32) % 4       # 0, 45, 90, 135 degrees
    keep = resp > floor
    pad = np.pad(g, 1, mode="edge")
    H, W = g.shape
    for k, (dx, dy) in enumerate(((1, 0), (1, 1), (0, 1), (-1, 1))):
        a = pad[1 + dy:1 + dy + H, 1 + dx:1 + dx + W]
        b = pad[1 - dy:1 - dy + H, 1 - dx:1 - dx + W]
        keep &= (q != k) | ((g >= a) & (g >= b))
    return keep


def _line_response(L: np.ndarray, ppm: float, method: str, dark: bool,
                   scales: tuple = (0.12, 0.25, 0.45)) -> np.ndarray:
    """Line strength map (L* units, >= 0) for the "xdog" and "ridge" methods.

    xdog : difference of Gaussians, positive on the dark (or light) side of an edge and inside thin
           dark (light) lines -> a single line drawn along each contour, like a pen drawing.
    ridge: multi-scale Hessian (largest curvature across the line, scale-normalised) -> the centre
           line of thin dark (light) strokes (lashes, wrinkles, hair), where Canny finds both edges.
    """
    sign = 1.0 if dark else -1.0
    if method == "xdog":
        sig = max(0.8, 0.15 * ppm)
        d = cv2.GaussianBlur(L, (0, 0), 1.6 * sig) - cv2.GaussianBlur(L, (0, 0), sig)
        return np.maximum(sign * d, 0)
    resp = np.zeros(L.shape, np.float32)
    for smm in scales:                           # default: line widths of ~0.3 to ~1.2 mm
        sig = max(0.8, smm * ppm)
        g = cv2.GaussianBlur(L, (0, 0), sig)
        dxx = cv2.Sobel(g, cv2.CV_32F, 2, 0, ksize=3)
        dyy = cv2.Sobel(g, cv2.CV_32F, 0, 2, ksize=3)
        dxy = cv2.Sobel(g, cv2.CV_32F, 1, 1, ksize=3)
        tr, root = dxx + dyy, np.sqrt((dxx - dyy) ** 2 + 4 * dxy * dxy)
        lam = (tr + root) / 2 if dark else -(tr - root) / 2   # curvature across the line
        # a step edge also curves on one side: weaken where the slope is strong (off-centre)
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3) / 8
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3) / 8
        r = np.maximum(lam, 0) * sig * sig
        slope = np.sqrt(gx * gx + gy * gy) * sig
        resp = np.maximum(resp, r * np.exp(-(slope / (r + 1e-3)) ** 2 / 2))
    return resp


# noise floor of each method (L* units): weaker responses are never candidates
_LINE_FLOOR = {"xdog": 1.5, "ridge": 2.0}


def thin_features(L100: np.ndarray, ppm: float, floor: float = 6.0) -> np.ndarray:
    """Thin dark or light strokes (~0.5 to ~2.5 mm wide: eyes, eyebrows, nostrils, strands) that
    the majority filter would swallow: band of strong Hessian ridge response, small specks removed."""
    scales = (0.25, 0.5, 0.9)
    r = np.maximum(_line_response(L100, ppm, "ridge", True, scales),
                   _line_response(L100, ppm, "ridge", False, scales))
    m = (r > floor).astype(np.uint8) * 255
    return remove_small(m, max(4, int(1.0 * ppm * ppm))) > 0


def lines_into_layers(prep: Prepared, sim: np.ndarray, p: Params, region: np.ndarray | None,
                      color_ids: list, painted: np.ndarray, stages: bool = False):
    """Key-detail lines to add to the colour layers: {layer position: stroke mask (image area)}.

    `painted`: position of the last layer painting each pixel once cut (-1 = bare support).
    Each line goes to a layer painted after the one(s) under it (darker tone, otherwise the paint
    would not show): the darkest layer, or (`nearest`) the one whose tone is closest to the line's
    colour in the original. Lines over an area already painted by the last layer are left out
    (they are already cut). With `stages`, returns the detection stages instead, the stroke
    limited to the lines added and `present` = lines already in the layers."""
    st = detect_key_details(prep, sim, p, region, dark=True, stages=True)
    n, comp = cv2.connectedComponents(st["kept"].astype(np.uint8), connectivity=8)
    if n <= 1:
        return dict(st, present=np.zeros_like(st["kept"])) if stages else ({}, 0)
    ys, xs = np.nonzero(comp)
    c = comp[ys, xs]
    # layer painting the area in the cut stencils = most frequent one along the line
    nl = len(color_ids) + 1
    counts = np.bincount(c * nl + painted[ys, xs] + 1, minlength=n * nl).reshape(n, nl)
    local = counts.argmax(axis=1) - 1
    # mean colour of the line in the original
    lab = _lab(prep.resized[ys, xs]).astype(np.float64)
    tot = np.bincount(c, minlength=n).astype(np.float64)
    mean = np.stack([np.bincount(c, lab[:, k], minlength=n) for k in range(3)], 1) / np.maximum(tot, 1)[:, None]
    pal = _lab(prep.palette)
    assign = np.full(n, -1, np.int32)
    for i in range(1, n):
        cands = list(range(local[i] + 1, len(color_ids)))         # layers are sorted light -> dark
        if not cands:
            continue
        if p.outline_target == "nearest":
            assign[i] = min(cands, key=lambda li: float(np.sum((pal[color_ids[li]] - mean[i]) ** 2)))
        else:
            assign[i] = cands[-1]
    width = max(p.outline_width_mm, p.min_opening_mm * 1.05)
    k = disk(width * p.px_per_mm / 2)
    out = {}
    for li in sorted(set(assign[assign >= 0].tolist())):
        m = (assign[comp] == li) & (comp > 0)
        out[li] = cv2.dilate(m.astype(np.uint8) * 255, k)
    if stages:
        stroke = np.zeros(comp.shape, bool)
        for m in out.values():
            stroke |= m > 0
        return dict(st, stroke=stroke, present=(assign[comp] < 0) & (comp > 0))
    return out, int((assign >= 0).sum())


def outline_keep_share(sensitivity: float) -> float:
    """Share of the candidate edge points kept by the outline sensitivity (0..100), progressive
    scale: 1 % at 0, 95 % at 100, each step multiplies it by ~1.05."""
    return 0.01 * 95.0 ** (float(np.clip(sensitivity, 0, 100)) / 100.0)


def detect_key_details(prep: Prepared, sim: np.ndarray, p: Params,
                       region: np.ndarray | None = None, dark: bool = True,
                       stages: bool = False):
    """Key details of the image that the flat render (simplification + airbrush blur) makes disappear.

    1. Candidate lines of the original, by the chosen method (`p.outline_method`):
       canny = sharp edges (thresholds on L*, a*, b*); xdog = drawn line (difference of Gaussians);
       ridge = centre line of thin strokes (Hessian). `dark`: polarity of the lines for xdog / ridge.
    2. Only those where the local contrast of the simulated render is clearly lower than the
       original's are kept (lost or faded detail).
    3. Lines that are too short are removed, then thickened to the line width.
    Returns a mask (image area) of the outline stencil openings; with `stages`, a dict of the
    intermediate masks (for the detection preview): detected, selected, kept, short, stroke.
    """
    ppm = p.px_per_mm
    ref = prep.resized
    method = p.outline_method

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

    lab_ref = lab(ref)
    g_ref = grad(lab_ref)
    g_sim = grad(lab(sim))

    # 1. Candidate lines
    if method == "canny":
        # Canny on the luminance AND on the colour channels (a, b), to also catch details as
        # bright as their surroundings.
        lab8 = cv2.cvtColor(cv2.bilateralFilter(ref, 7, 40, 5), cv2.COLOR_BGR2LAB)
        edges = np.zeros(ref.shape[:2], bool)
        for c, (lo, hi) in enumerate(((12, 32), (8, 20), (8, 20))):
            edges |= cv2.Canny(lab8[..., c], lo, hi, L2gradient=True) > 0
        strength = g_ref
    else:
        strength = _line_response(lab_ref[..., 0], ppm, method, dark)
        edges = _crest(strength, _LINE_FLOOR[method])
    b = max(2, int(round(0.5 * ppm)))   # no line on the edge of the image itself
    edges[:b, :] = False; edges[-b:, :] = False; edges[:, :b] = False; edges[:, -b:] = False
    if region is not None:               # mask painted by the user: search only inside
        edges &= region.astype(bool)

    def result(sel, kept, short, stroke):
        if not stages:
            return stroke
        return dict(detected=edges, selected=sel, kept=kept, short=short, stroke=stroke > 0)

    # 2. Loss of sharpness: share of the original's local contrast missing from the simulated render
    loss = np.clip((g_ref - g_sim) / (g_ref + 1e-3), 0, 1)
    loss = cv2.dilate(loss, disk(max(1.0, 0.4 * ppm)))      # edge position tolerance

    # 3. Point-by-point selection: importance = line strength x lost share.
    #    The sensitivity sets the share of edge points kept (from most to least important), on a
    #    progressive scale (1 % at 0, ~10 % at 50, 95 % at 100: fine control of the few-lines end).
    #    Minimum lost share: 0.5 up to 15 % kept, then down to 0.2 at 95 % (as before version 1.2).
    keep_share = outline_keep_share(p.outline_sensitivity)
    cand = edges & (loss >= 0.5 - 0.3 * float(np.clip((keep_share - 0.15) / 0.8, 0, 1)))
    if not cand.any():
        z = np.zeros(ref.shape[:2], bool)
        return result(z, z, z, np.zeros(ref.shape[:2], np.uint8))
    score = strength * loss
    thr = float(np.percentile(score[cand], 100 * (1 - keep_share)))
    sel = cand & (score >= thr)
    # rejoin small gaps along a same line, then remove pieces that are too short
    e8 = cv2.morphologyEx(sel.astype(np.uint8) * 255, cv2.MORPH_CLOSE, disk(max(1.0, 0.3 * ppm)))
    n, lab_e, stats, _ = cv2.connectedComponentsWithStats(e8, connectivity=8)
    min_px = max(2, int(p.outline_min_length_mm * ppm))
    # approximate length of a line = its largest dimension
    length = np.maximum(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT])
    keep = length >= min_px
    keep[0] = False
    short = (e8 > 0) & ~keep[lab_e]
    e8 = keep[lab_e].astype(np.uint8) * 255
    # effective width: never less than the material's minimum opening (otherwise not cuttable)
    width = max(p.outline_width_mm, p.min_opening_mm * 1.05)
    stroke = cv2.dilate(e8, disk(width * ppm / 2))
    return result(sel, e8 > 0, short, stroke)


def outline_detection(res: Result, p: Params, region: np.ndarray | None = None) -> dict:
    """Detection stages of the outline stencil for the preview, from a computed result and the
    current outline settings of `p` (colour layers and simulated render are the result's)."""
    p = replace(res.params, **{f.name: getattr(p, f.name) for f in fields(Params)
                               if f.name.startswith("outline")})
    prep = res.prepared
    if prep.fg is not None:
        region = prep.fg if region is None else (region.astype(bool) & prep.fg)
    sim = res.detect_sim
    if sim is None:      # outline off in the last computation: render of its colour layers
        sim = image_sim(replace(res, layers=[L for L in res.layers if L.kind != "outline"]))
    if p.outline_target == "stencil":
        dark = outline_is_dark(outline_color(prep, res.support_color, p), res.support_color)
        return dict(detect_key_details(prep, sim, p, region, dark, stages=True), present=None)
    colour = [L for L in res.layers if L.kind != "outline"]
    color_ids = [i for i in range(len(prep.palette)) if i != res.support_label][:len(colour)]
    painted = res.detect_painted
    if painted is None:  # lines not merged in the last computation: its colour layers as cut
        H, W = prep.labels.shape
        X0, Y0 = res.img_off_px
        painted = np.full((H, W), -1, np.int32)
        for li, L in enumerate(colour):
            painted[L.opening[Y0:Y0 + H, X0:X0 + W] > 0] = li
    return lines_into_layers(prep, sim, p, region, color_ids, painted, stages=True)

# --------------------------------------------------------------------------
# Registration marks (exact geometry in mm, sheet coordinates)
# --------------------------------------------------------------------------

CORNER_NAMES = ("haut-gauche", "haut-droite", "bas-gauche", "bas-droite")


def _reg_layout(res: Result) -> tuple[str, list[tuple], float, list[str]]:
    """Effective shape, mark centres (sheet coordinates, mm) and width of the free band.

    Returns (shape, [(name, cx, cy, sx, sy)], band, warnings); (sx, sy) = inward direction.
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
                pts.append((name, cx - sx * m / 2, cy - sy * m / 2, sx, sy))          # in the margin
            else:
                pts.append((name, cx + sx * (a / 2 + 1), cy + sy * (a / 2 + 1), sx, sy))  # in the support corner
                if p.inner_margin_mm < a + 2 and not warns:
                    warns.append("Les repères sont placés dans les angles du support et risquent de "
                                 "chevaucher l'image : augmentez la marge de la feuille ou la marge intérieure.")
        return shape, pts, m, warns
    # Sheet laid INSIDE the support: no support corner to aim at -> crosses (or holes) in the border,
    # transferred in pencil onto the support using the dimensions.
    if shape == "equerre":
        shape = "croix"
    bx = (res.img_off_px[0]) / p.px_per_mm                       # actual border on the left…
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
    """Shapes to cut for registration.

    - equerre (L-bracket): L-shaped slot outside each support corner. The stencil is
      in place when the support corner exactly meets the inner corner of the L.
    - croix (cross): cross window -> the cross is transferred in pencil onto the support (at the
      given dimensions when the sheet is laid inside the support), then each layer is aligned on it.
    - rond (round): hole for registration pegs (diameter = size).
    3 corners: the bottom-right corner is omitted, which acts as a key.
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
    """Ruler dimensions (sheet laid inside the support), origin = support's top-left corner (mm).

    A cross is pencilled on the support at each dimension, then each layer is laid by
    aligning its cross windows on these marks.
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
# 6. Previews
# --------------------------------------------------------------------------

def simulate_sheet(res: Result) -> np.ndarray:
    """Airbrush render simulation on the sheet (the only place paint goes through)."""
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
    """Common area of sheet and support: (x0, y0, x1, y1) in the support and offset to the sheet."""
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
    """Copies a "sheet" array to the support size (the rest is filled with `fill`)."""
    SW, SH = res.support_px
    out = np.empty((SH, SW) + arr.shape[2:], arr.dtype)
    out[:] = fill
    (x0, y0, x1, y1), (ox, oy) = support_overlap(res)
    if x1 > x0 and y1 > y0:
        out[y0:y1, x0:x1] = arr[y0 + oy:y1 + oy, x0 + ox:x1 + ox]
    return out


def simulate(res: Result) -> np.ndarray:
    """Airbrush render simulation over the whole support."""
    return sheet_to_support(res, simulate_sheet(res), res.support_color.astype(np.uint8))


def image_sim(res: Result, sheet_sim: np.ndarray | None = None) -> np.ndarray:
    """Simulated render of the image area only."""
    sim = simulate_sheet(res) if sheet_sim is None else sheet_sim
    H, W = res.prepared.labels.shape
    X0, Y0 = res.img_off_px
    return sim[Y0:Y0 + H, X0:X0 + W]


def image_crop(res: Result, sim: np.ndarray) -> np.ndarray:
    """Image area in a support-sized render."""
    H, W = res.prepared.labels.shape
    ox, oy = res.prepared.off_px
    return sim[oy:oy + H, ox:ox + W]


def quantized_view(res: Result) -> np.ndarray:
    pal = res.prepared.palette.copy()
    if res.support_label is not None:
        pal[res.support_label] = res.support_color
    return pal[res.prepared.labels]


def layer_view(res: Result, L: Layer, sheet_bgr=(200, 211, 220), bridges: bool = True,
               lost: bool = True) -> np.ndarray:
    """Stencil view: material, openings, bridges (red), lost details (orange), registration.

    `bridges` / `lost` = False: view without these highlights (see `layer_overlays` to get them separately).
    """
    p = res.params
    ppm = p.px_per_mm
    SW, SH = res.support_px
    ox, oy = res.sup_off_px
    op = L.opening > 0
    img = np.empty(op.shape + (3,), np.uint8)
    img[:] = sheet_bgr
    # support outline (visual guide, not cut)
    cv2.rectangle(img, (ox, oy), (ox + SW - 1, oy + SH - 1), (150, 150, 150), 1)
    light = (L.color.astype(np.float32) * 0.55 + 255 * 0.45).astype(np.uint8)
    img[op] = light
    edge = cv2.morphologyEx(L.opening, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    img[edge] = (40, 40, 40)
    if lost:
        sel = _lost_mask(res, L, edge)
        img[sel] = (img[sel] * (1 - LOST_ALPHA) + np.array(LOST_BGR) * LOST_ALPHA).astype(np.uint8)
    if bridges:
        _draw_bridges(img, res, L, BRIDGE_BGR)
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


BRIDGE_BGR = (40, 40, 230)
LOST_BGR = (0, 140, 255)
LOST_ALPHA = 0.6
MERGE_BGR = (200, 60, 150)      # violet: zones merged instead of a bridge
MERGE_ALPHA = 0.75


def _lost_mask(res: Result, L: Layer, edge: np.ndarray | None = None) -> np.ndarray:
    H, W = res.prepared.labels.shape
    X0, Y0 = res.img_off_px
    m = np.zeros(L.opening.shape, bool)
    m[Y0:Y0 + H, X0:X0 + W] = L.lost > 0
    if edge is None:
        edge = cv2.morphologyEx(L.opening, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    return m & ~edge


def _draw_bridges(img: np.ndarray, res: Result, L: Layer, color) -> None:
    bw = max(1, int(round(res.params.bridge_width_mm * res.params.px_per_mm)))
    for (x1, y1, x2, y2) in L.bridges:
        cv2.line(img, (x1, y1), (x2, y2), color, thickness=bw)


def layer_overlays(res: Result, L: Layer) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Transparent overlays (BGRA, sheet size) of the bridges, removed details and merged zones,
    to stack on `layer_view(..., bridges=False, lost=False)` so they can be shown or hidden."""
    # colour everywhere, only transparency varies: sharp edges once the image is downscaled
    shape = L.opening.shape
    br = np.empty(shape + (4,), np.uint8)
    br[..., :3] = BRIDGE_BGR
    a = np.zeros(shape, np.uint8)
    _draw_bridges(a, res, L, 255)
    br[..., 3] = a
    lo = np.empty(shape + (4,), np.uint8)
    lo[..., :3] = LOST_BGR
    lo[..., 3] = np.where(_lost_mask(res, L), int(round(255 * LOST_ALPHA)), 0).astype(np.uint8)
    mg = np.empty(shape + (4,), np.uint8)
    mg[..., :3] = MERGE_BGR
    mg[..., 3] = 0 if L.merged is None else np.where(L.merged, int(round(255 * MERGE_ALPHA)), 0).astype(np.uint8)
    return br, lo, mg


def delta_e(res: Result, sheet_sim: np.ndarray | None = None) -> float:
    """Mean difference (Lab ΔE) between the original image and the simulated render, over the image area."""
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
        "merged": L.n_merged,
        "islands": L.islands,
        "kind": L.kind,
        "short_islands": L.short_islands,
        "cut_length_m": round(length / 1000, 2),
        "lost_pct": round(100 * float((L.lost > 0).mean()), 1),
    }
