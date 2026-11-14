"""Effects applied to the computed layers (opening masks), before merges, bridges and vectorisation.

Each colour layer has its own ordered stack of effects. The stacks are stored in
`Params.layer_effects` as JSON:

    {"on": true,
     "layers": {"1": {"on": true, "fx": [{"type": "smooth", "on": true, "p": {"radius_mm": 0.8}}]},
                "2": {...}}}

Layers are processed in spraying order (1, 2, 3...): an effect sees the final shape of the layers
already processed and the raw shape (before effects) of the following ones. Some effects also
change other layers (drop shadow, halo). After the effects, every changed layer is cleaned again
with the material limits so that it stays cuttable.

Masks are uint8 (0 / 255) at `px_per_mm`, image area. Patterns are anchored to the support (the
same pattern lines up from one layer to the next).

Labels and tooltips are in French (UI source language, translated in `static/i18n.js`).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

# --------------------------------------------------------------------------
# Effect catalogue (served to the browser by /api/effects)
# --------------------------------------------------------------------------
# effect: label, category, tip, params
# param: key, label, kind (float | int | choice), min, max, step, default, unit, tip, [choices],
# [when: {other param: value or [values]} = shown only then]

CATEGORIES = ["Contour", "Remplissage", "Structure", "Pratique"]


def _f(key, label, lo, hi, step, default, unit, tip, **kw):
    return {"key": key, "label": label, "kind": "float", "min": lo, "max": hi, "step": step,
            "default": default, "unit": unit, "tip": tip, **kw}


def _i(key, label, lo, hi, default, tip, unit="", **kw):
    return {"key": key, "label": label, "kind": "int", "min": lo, "max": hi, "step": 1,
            "default": default, "unit": unit, "tip": tip, **kw}


def _c(key, label, choices, default, tip, **kw):
    return {"key": key, "label": label, "kind": "choice", "choices": choices, "default": default,
            "tip": tip, **kw}


EFFECTS: dict[str, dict] = {
    # ---------------------------------------------------------------- outline of the shapes
    "smooth": {
        "label": "Lissage", "category": "Contour",
        "tip": "Arrondit les angles et adoucit les contours de la couche (rendu plus organique, coupe plus "
               "facile dans les angles). La surface peinte reste à peu près la même.",
        "params": [
            _f("radius_mm", "Rayon", 0.1, 10, 0.1, 0.8, "mm",
               "Rayon des arrondis : plus grand = formes plus douces, petits détails effacés"),
        ],
    },
    "polygon": {
        "label": "Contour polygonal", "category": "Contour",
        "tip": "Simplifie fortement les contours en lignes droites : rendu facetté, « low-poly », façon "
               "papier découpé.",
        "params": [
            _f("tolerance_mm", "Simplification", 0.3, 20, 0.1, 2.5, "mm",
               "Écart maximal entre le contour d'origine et les segments : plus grand = moins de facettes, plus grandes"),
        ],
    },
    "angular": {
        "label": "Contour anguleux", "category": "Contour",
        "tip": "Remplace les contours par des segments aux angles imposés (90°, 45° ou 30°) : rendu "
               "géométrique, cristallisé ou Art déco.",
        "params": [
            _c("step", "Angles", [["90", "90° (escaliers)"], ["45", "45°"], ["30", "30°"]], "45",
               "Directions permises pour les segments : multiples de cet angle"),
            _f("tolerance_mm", "Simplification", 0.3, 20, 0.1, 2.0, "mm",
               "Simplification du contour avant de redresser les segments : plus grand = segments plus longs"),
        ],
    },
    "rough": {
        "label": "Bords rugueux", "category": "Contour",
        "tip": "Déforme les contours avec un bruit aléatoire (aspect graffiti, papier déchiré). La même graine "
               "sur plusieurs couches leur donne la même déformation : elles restent calées entre elles.",
        "params": [
            _f("amplitude_mm", "Amplitude", 0.1, 10, 0.1, 0.6, "mm", "Déplacement maximal approximatif des contours"),
            _f("scale_mm", "Échelle", 0.5, 50, 0.5, 4, "mm",
               "Taille des ondulations : petite = bord granuleux, grande = bord ondulant"),
            _i("seed", "Graine", 0, 9999, 1, "Change le tirage aléatoire du bruit"),
        ],
    },
    "wavy": {
        "label": "Bords ondulés", "category": "Contour",
        "tip": "Fait onduler régulièrement les contours : vagues, dents de scie ou festons (effet « timbre-poste »).",
        "params": [
            _c("shape", "Forme", [["wave", "vagues"], ["teeth", "dents de scie"], ["scallop", "festons"]], "wave",
               "Forme de l'ondulation le long du contour"),
            _f("amplitude_mm", "Amplitude", 0.1, 10, 0.1, 0.8, "mm", "Écart de part et d'autre du contour d'origine"),
            _f("period_mm", "Période", 0.5, 50, 0.5, 4, "mm", "Longueur d'une ondulation le long du contour"),
        ],
    },
    "offset": {
        "label": "Gonflement / amincissement", "category": "Contour",
        "tip": "Décale tout le contour de la couche vers l'extérieur (valeur positive : formes et traits plus "
               "épais) ou vers l'intérieur (valeur négative : plus fins, les petits détails disparaissent).",
        "params": [
            _f("distance_mm", "Décalage", -10, 10, 0.1, 0.5, "mm",
               "Positif = vers l'extérieur (gonfler), négatif = vers l'intérieur (amincir)"),
        ],
    },
    # ---------------------------------------------------------------- fill of the flat areas
    "halftone": {
        "label": "Trame de points", "category": "Remplissage",
        "tip": "Remplace l'aplat par des trous ronds sur une grille (effet pop art). La taille des points "
               "peut suivre la distance au bord ou les tons de l'image d'origine (dégradé tramé).",
        "params": [
            _f("pitch_mm", "Pas de la grille", 1, 30, 0.5, 4, "mm", "Distance entre les centres de deux points voisins"),
            _f("dmin_mm", "Ø mini", 0, 20, 0.1, 1, "mm", "Diamètre des plus petits points (0 = les points disparaissent)"),
            _f("dmax_mm", "Ø maxi", 0.3, 30, 0.1, 3, "mm",
               "Diamètre des plus gros points (égal au pas : les points se touchent)"),
            _f("angle", "Angle", 0, 90, 1, 45, "°", "Orientation de la grille"),
            _c("source", "Taille des points",
               [["flat", "constante (Ø maxi)"], ["edge", "selon la distance au bord"], ["tone", "selon les tons de l'image"]],
               "edge",
               "Constante : tous les points au Ø maxi. Distance au bord : petits près du bord, gros au centre. "
               "Tons : gros dans les zones sombres de l'image d'origine, petits dans les claires"),
            _f("fade_mm", "Fondu depuis le bord", 0.5, 50, 0.5, 6, "mm",
               "Distance au bord sur laquelle les points grossissent (taille selon la distance au bord)",
               when={"source": "edge"}),
        ],
    },
    "hatch": {
        "label": "Hachures", "category": "Remplissage",
        "tip": "Remplace l'aplat par des bandes parallèles (hachures), simples ou croisées. Les hachures "
               "croisées laissent des carrés de matière isolés, tenus par des ponts.",
        "params": [
            _f("pitch_mm", "Pas", 1, 30, 0.5, 3, "mm", "Distance entre deux hachures voisines"),
            _f("width_mm", "Largeur d'une hachure", 0.3, 20, 0.1, 1.2, "mm", "Largeur des bandes peintes"),
            _f("angle", "Angle", 0, 180, 1, 45, "°", "Orientation des hachures"),
            _c("cross", "Type", [["single", "simples"], ["cross", "croisées"]], "single",
               "Croisées : une seconde série de hachures à angle droit"),
        ],
    },
    "levels": {
        "label": "Lignes de niveau", "category": "Remplissage",
        "tip": "Remplace l'aplat par des bandes qui suivent le contour, de plus en plus à l'intérieur (style "
               "topographique ou op art). Les anneaux de matière sont tenus par des ponts.",
        "params": [
            _f("pitch_mm", "Pas", 1, 30, 0.5, 3, "mm", "Distance entre deux lignes voisines"),
            _f("width_mm", "Largeur d'une ligne", 0.3, 20, 0.1, 1.2, "mm", "Largeur des bandes peintes"),
        ],
    },
    "pattern": {
        "label": "Motif", "category": "Remplissage",
        "tip": "Remplit l'aplat avec un motif répété (losanges, hexagones, briques, étoiles), découpé par la "
               "forme de la couche. La matière entre les motifs reste d'un seul tenant.",
        "params": [
            _c("shape", "Motif", [["diamond", "losanges"], ["hexagon", "hexagones"], ["brick", "briques"],
                                  ["star", "étoiles"]], "hexagon", "Forme répétée"),
            _f("size_mm", "Taille", 1, 50, 0.5, 6, "mm", "Taille d'un motif (avec son joint)"),
            _f("gap_mm", "Joint", 0.3, 10, 0.1, 1.2, "mm", "Largeur de matière laissée entre deux motifs"),
        ],
    },
    # ---------------------------------------------------------------- structure, composition
    "outline": {
        "label": "Contour seul", "category": "Structure",
        "tip": "Ne garde qu'une bande le long du bord de chaque forme : un aplat devient un trait cerné. "
               "L'intérieur reste en matière, tenu par des ponts.",
        "params": [
            _f("width_mm", "Largeur du trait", 0.3, 30, 0.1, 2, "mm", "Largeur de la bande gardée le long du bord"),
        ],
    },
    "shadow": {
        "label": "Ombre portée", "category": "Structure",
        "tip": "Ajoute une copie décalée de la couche (son ombre) à une autre couche, en général plus foncée : "
               "effet de relief ou de sticker. L'ombre n'est ajoutée que là où la couche n'est pas.",
        "params": [
            _f("dx_mm", "Décalage horizontal", -50, 50, 0.5, 2, "mm", "Décalage vers la droite (négatif = vers la gauche)"),
            _f("dy_mm", "Décalage vertical", -50, 50, 0.5, 2, "mm", "Décalage vers le bas (négatif = vers le haut)"),
            _i("layer", "Couche de l'ombre", 0, 10, 0,
               "Numéro de la couche qui peint l'ombre (0 = la plus foncée)"),
        ],
    },
    "halo": {
        "label": "Halo / liseré", "category": "Structure",
        "tip": "Bande tout autour des formes de la couche, à une distance donnée : laissée en support nu (liseré "
               "blanc de sticker) ou peinte par une autre couche.",
        "params": [
            _f("gap_mm", "Distance", 0, 30, 0.1, 0, "mm", "Écart entre la forme et le halo"),
            _f("width_mm", "Largeur", 0.3, 30, 0.1, 2, "mm", "Largeur de la bande du halo"),
            _i("layer", "Couche du halo", 0, 10, 0,
               "0 = support nu (le halo est retiré de toutes les autres couches) ; sinon numéro de la couche qui peint le halo"),
        ],
    },
    "mosaic": {
        "label": "Mosaïque / vitrail", "category": "Structure",
        "tip": "Découpe les ouvertures en tessons irréguliers séparés par des joints de matière : effet "
               "vitrail, et un grand pochoir devient plus rigide.",
        "params": [
            _f("cell_mm", "Taille des tessons", 2, 80, 0.5, 10, "mm", "Taille moyenne d'un tesson"),
            _f("joint_mm", "Joint", 0.5, 10, 0.1, 1.2, "mm", "Largeur des joints de matière entre les tessons"),
            _i("seed", "Graine", 0, 9999, 1, "Change le tirage aléatoire des tessons"),
        ],
    },
    "bridges": {
        "label": "Ponts décoratifs", "category": "Structure",
        "tip": "Coupe les ouvertures par des bandes de matière qui forment un motif voulu (lignes, grille, "
               "rayons) : les ponts deviennent un élément du style, comme un lettrage au pochoir.",
        "params": [
            _c("style", "Disposition", [["lines", "lignes parallèles"], ["grid", "grille"], ["rays", "rayons"]],
               "lines", "Lignes : une série de bandes parallèles. Grille : deux séries croisées. Rayons : depuis le centre de la couche"),
            _f("pitch_mm", "Pas", 2, 100, 0.5, 10, "mm", "Distance entre deux ponts voisins",
               when={"style": ["lines", "grid"]}),
            _i("count", "Nombre de rayons", 3, 72, 12, "Nombre de rayons répartis sur le tour",
               when={"style": "rays"}),
            _f("width_mm", "Largeur", 0.5, 10, 0.1, 1.5, "mm", "Largeur des ponts"),
            _f("angle", "Angle", 0, 180, 1, 0, "°", "Orientation des lignes, de la grille ou du premier rayon"),
        ],
    },
    # ---------------------------------------------------------------- practical (cutting, registration)
    "overlap": {
        "label": "Recouvrement", "category": "Pratique",
        "tip": "Agrandit la couche sous les couches suivantes (plus foncées) : un léger décalage de calage ne "
               "laisse plus de liseré du support entre deux couches. Sans effet en empilement cumulatif.",
        "params": [
            _f("width_mm", "Débord", 0.1, 5, 0.1, 0.5, "mm", "Largeur du débord sous les couches suivantes"),
        ],
    },
    "merge": {
        "label": "Fusion des petites ouvertures", "category": "Pratique",
        "tip": "Réunit les ouvertures très proches les unes des autres et supprime les plus petites : moins "
               "de micro-découpes, coupe plus rapide.",
        "params": [
            _f("distance_mm", "Distance", 0.2, 10, 0.1, 1.0, "mm",
               "Les ouvertures séparées par moins que cette distance sont réunies"),
            _f("min_area_mm2", "Surface mini", 0, 100, 0.5, 0, "mm²",
               "Les ouvertures plus petites que cette surface sont supprimées (0 = toutes gardées)"),
        ],
    },
}


def catalogue() -> dict:
    return EFFECTS


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def _param_value(spec: dict, v):
    d = spec["default"]
    if spec["kind"] == "choice":
        keys = [c[0] for c in spec["choices"]]
        return v if v in keys else d
    try:
        v = float(v)
    except (TypeError, ValueError):
        return d
    if not math.isfinite(v):
        return d
    v = min(max(v, spec["min"]), spec["max"])
    return int(round(v)) if spec["kind"] == "int" else v


FREED = ("support", "nearest", "lighter")


def options(txt: str) -> dict:
    """Options of the effects in exclusive stacking:
    sync: what an effect adds to a layer is removed from the darker layers (painted later, they
          would hide it); freed: what an effect removes from a layer goes to the bare support, to the
          layer surrounding the area ("nearest"), or to the previous (lighter) layer."""
    out = {"sync": True, "freed": "support"}
    try:
        data = json.loads(txt) if txt else {}
    except (ValueError, TypeError):
        data = {}
    if isinstance(data, dict):
        if isinstance(data.get("sync"), bool):
            out["sync"] = data["sync"]
        if data.get("freed") in FREED:
            out["freed"] = data["freed"]
    return out


def parse(txt: str) -> dict[int, list[tuple[str, dict]]]:
    """Active effects per layer number: {layer: [(type, params), ...]} (empty = no effect)."""
    if not txt:
        return {}
    try:
        data = json.loads(txt)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict) or data.get("on") is False:
        return {}
    out = {}
    for k, layer in (data.get("layers") or {}).items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        if not isinstance(layer, dict) or layer.get("on") is False:
            continue
        stack = []
        for fx in layer.get("fx") or []:
            if not isinstance(fx, dict) or fx.get("on") is False or fx.get("type") not in EFFECTS:
                continue
            raw = fx.get("p") or {}
            stack.append((fx["type"], {s["key"]: _param_value(s, raw.get(s["key"], s["default"]))
                                       for s in EFFECTS[fx["type"]]["params"]}))
        if stack:
            out[idx] = stack
    return out


# --------------------------------------------------------------------------
# Context shared by the effects of one computation
# --------------------------------------------------------------------------

@dataclass
class Context:
    ppm: float
    off_px: tuple                     # image area on the support (px): patterns anchored to the support
    image_bgr: np.ndarray             # prepared image (tones source)
    masks: list                       # current masks of all colour layers (image area, uint8 0/255)
    index: int = 0                    # 0-based index of the layer being processed
    touched: set = field(default_factory=set)   # other layers changed by an effect (cleaned at the end)
    under: dict = field(default_factory=dict)   # layer -> what Overlap added (meant to stay under the next layers)
    bare: np.ndarray | None = None              # left as bare support on purpose (halo on the support)
    _light: np.ndarray | None = field(default=None, repr=False)

    def lightness(self) -> np.ndarray:
        """L* of the prepared image, 0..100 (float32)."""
        if self._light is None:
            lab = cv2.cvtColor(self.image_bgr.astype(np.float32) / 255.0, cv2.COLOR_BGR2LAB)
            self._light = lab[..., 0]
        return self._light

    def later(self) -> np.ndarray:
        """Union of the following layers (raw shapes)."""
        out = np.zeros_like(self.masks[self.index])
        for m in self.masks[self.index + 1:]:
            out |= m
        return out

    def grid_mm(self, shape) -> tuple[np.ndarray, np.ndarray]:
        """Support coordinates (mm) of the pixel centres."""
        H, W = shape
        ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
        return (xs + 0.5 + self.off_px[0]) / self.ppm, (ys + 0.5 + self.off_px[1]) / self.ppm

    def target(self, n: int, default_last: bool) -> int | None:
        """0-based index of the layer numbered n (1..), 0 = the darkest one (or None)."""
        if n <= 0:
            return len(self.masks) - 1 if default_last else None
        return min(n, len(self.masks)) - 1


def _disk(r: float) -> np.ndarray:
    k = max(1, int(round(r)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))


def _u8(b: np.ndarray) -> np.ndarray:
    return np.where(b, 255, 0).astype(np.uint8)


def _dist_inside(mask: np.ndarray) -> np.ndarray:
    """Distance (px) of each pixel of the shape to the nearest pixel outside it."""
    return cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 5)


def _dist_outside(mask: np.ndarray) -> np.ndarray:
    """Distance (px) of each pixel outside the shape to the shape."""
    return cv2.distanceTransform((mask == 0).astype(np.uint8), cv2.DIST_L2, 5)


# --------------------------------------------------------------------------
# Outline redrawing (polygonal, angular, wavy): every contour is transformed, then the shapes are
# filled again by nesting depth (outer shape, hole, island in the hole...)
# --------------------------------------------------------------------------

def _contours(mask: np.ndarray, approx=cv2.CHAIN_APPROX_NONE) -> list[tuple[np.ndarray, int]]:
    cnts, hier = cv2.findContours(mask, cv2.RETR_TREE, approx)
    if hier is None:
        return []
    hier = hier[0]
    out = []
    for i, c in enumerate(cnts):
        d, p = 0, hier[i][3]
        while p >= 0:
            d += 1
            p = hier[p][3]
        out.append((c[:, 0, :].astype(np.float32), d))
    return out


def _redraw(shape, polys) -> np.ndarray:
    out = np.zeros(shape, np.uint8)
    for pts, d in sorted(polys, key=lambda t: t[1]):
        if pts is None or len(pts) < 3:
            continue
        cv2.fillPoly(out, [np.round(pts * 16).astype(np.int32)], 255 if d % 2 == 0 else 0, cv2.LINE_8, 4)
    return out


def _snap(pts: np.ndarray, step_deg: float) -> np.ndarray:
    """Closed polygon whose segments all follow multiples of step_deg: each segment is replaced by
    two segments along the two allowed directions around it (vertices kept, closed exactly)."""
    st = math.radians(step_deg)
    out = []
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        out.append(a)
        v = b - a
        if float(np.hypot(*v)) < 1e-6:
            continue
        ang = math.atan2(float(v[1]), float(v[0]))
        a1 = math.floor(ang / st + 1e-9) * st
        u1 = np.array([math.cos(a1), math.sin(a1)], np.float32)
        u2 = np.array([math.cos(a1 + st), math.sin(a1 + st)], np.float32)
        det = u1[0] * u2[1] - u1[1] * u2[0]
        if abs(det) < 1e-9:
            continue
        s = (v[0] * u2[1] - v[1] * u2[0]) / det
        t = (u1[0] * v[1] - u1[1] * v[0]) / det
        if s > 1e-6 and t > 1e-6:
            out.append(a + s * u1 if s >= t else a + t * u2)
    return np.array(out, np.float32)


def _smooth_closed(pts: np.ndarray, sigma: float) -> np.ndarray:
    n = len(pts)
    r = int(min(3 * sigma, (n - 1) // 2))
    if r < 1:
        return pts
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    ext = np.concatenate([pts[-r:], pts, pts[:r]])
    return np.stack([np.convolve(ext[:, 0], k, "valid"), np.convolve(ext[:, 1], k, "valid")], 1).astype(np.float32)


# --------------------------------------------------------------------------
# Effects (mask, context, parameters) -> mask
# --------------------------------------------------------------------------

def fx_smooth(mask, ctx, a):
    sigma = max(0.5, a["radius_mm"] * ctx.ppm * 0.5)
    blur = cv2.GaussianBlur(mask, (0, 0), sigma)
    return _u8(blur >= 128)


def fx_polygon(mask, ctx, a):
    eps = max(0.5, a["tolerance_mm"] * ctx.ppm)
    polys = [(cv2.approxPolyDP(p.reshape(-1, 1, 2), eps, True)[:, 0, :], d) for p, d in _contours(mask)]
    return _redraw(mask.shape, polys)


def fx_angular(mask, ctx, a):
    eps = max(0.5, a["tolerance_mm"] * ctx.ppm)
    step = float(a["step"])
    polys = []
    for p, d in _contours(mask):
        q = cv2.approxPolyDP(p.reshape(-1, 1, 2), eps, True)[:, 0, :]
        polys.append((_snap(q, step) if len(q) >= 3 else q, d))
    return _redraw(mask.shape, polys)


def fx_rough(mask, ctx, a):
    if not mask.any():
        return mask
    H, W = mask.shape
    ppm = ctx.ppm
    rng = np.random.default_rng(int(a["seed"]))
    cell = max(2.0, a["scale_mm"] * ppm)
    amp = a["amplitude_mm"] * ppm * 0.5           # ~ 2 sigma = amplitude
    dx = _noise((H, W), cell, rng) + 0.35 * _noise((H, W), max(2.0, cell / 3), rng)
    dy = _noise((H, W), cell, rng) + 0.35 * _noise((H, W), max(2.0, cell / 3), rng)
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    out = cv2.remap(mask, xs + dx * amp, ys + dy * amp, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return _u8(out >= 128)


def _noise(shape, cell_px: float, rng: np.random.Generator) -> np.ndarray:
    H, W = shape
    gh, gw = max(2, int(H / cell_px) + 3), max(2, int(W / cell_px) + 3)
    g = rng.standard_normal((gh, gw)).astype(np.float32)
    n = cv2.resize(g, (int(gw * cell_px), int(gh * cell_px)), interpolation=cv2.INTER_CUBIC)[:H, :W]
    sd = float(n.std())
    return n / sd if sd > 1e-6 else n


def fx_wavy(mask, ctx, a):
    ppm = ctx.ppm
    amp, per = a["amplitude_mm"] * ppm, max(1.0, a["period_mm"] * ppm)
    polys = []
    for p, d in _contours(mask):
        if len(p) < 8:
            polys.append((p, d))
            continue
        q = _smooth_closed(p, 1.5)
        seg = np.hypot(*np.diff(np.vstack([q, q[:1]]), axis=0).T)
        s = np.concatenate([[0.0], np.cumsum(seg)[:-1]])
        if s[-1] + seg[-1] < per:                     # contour shorter than one period: left as is
            polys.append((p, d))
            continue
        t = np.roll(q, -1, 0) - np.roll(q, 1, 0)
        t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-6)[:, None]
        nrm = np.stack([-t[:, 1], t[:, 0]], 1)
        ph = s / per
        if a["shape"] == "teeth":
            w = 2 * np.abs(2 * (ph % 1) - 1) - 1      # triangle wave: zigzag
        elif a["shape"] == "scallop":
            w = 2 * np.abs(np.sin(np.pi * ph)) - 1    # rounded scallops
        else:
            w = np.sin(2 * np.pi * ph)
        polys.append((q + nrm * (amp * w)[:, None], d))
    return _redraw(mask.shape, polys)


def fx_offset(mask, ctx, a):
    d = a["distance_mm"] * ctx.ppm
    if abs(d) < 0.5:
        return mask
    if d > 0:
        return _u8((mask > 0) | (_dist_outside(mask) <= d))
    return _u8(_dist_inside(mask) > -d)


def fx_halftone(mask, ctx, a):
    if not mask.any():
        return mask
    H, W = mask.shape
    ppm = ctx.ppm
    pitch = a["pitch_mm"]
    dmin, dmax = sorted((a["dmin_mm"], a["dmax_mm"]))
    th = math.radians(a["angle"])
    c, s = math.cos(th), math.sin(th)
    X, Y = ctx.grid_mm(mask.shape)
    u = X * c + Y * s
    v = -X * s + Y * c
    cu = np.round(u / pitch) * pitch               # centre of the grid cell
    cv_ = np.round(v / pitch) * pitch
    d = np.hypot(u - cu, v - cv_)
    del u, v, X, Y
    # cell centre back in image pixels, to sample the size of the dot there (one size per dot)
    px = np.clip(((cu * c - cv_ * s) * ppm - ctx.off_px[0]).astype(np.int32), 0, W - 1)
    py = np.clip(((cu * s + cv_ * c) * ppm - ctx.off_px[1]).astype(np.int32), 0, H - 1)
    del cu, cv_
    src = a["source"]
    if src == "flat":
        t = np.ones((H, W), np.float32)
    elif src == "edge":
        dist = _dist_inside(mask) / ppm
        t = np.clip(dist / max(a["fade_mm"], 1e-3), 0, 1)[py, px]
    else:                                          # tone: dark in the image = big dot
        L = ctx.lightness()
        inside = L[mask > 0]
        lo, hi = np.percentile(inside, (5, 95)) if inside.size else (0.0, 100.0)
        dark = np.clip((hi - L) / max(hi - lo, 1e-3), 0, 1)
        dark = cv2.GaussianBlur(dark, (0, 0), max(0.5, pitch * ppm * 0.5))
        t = dark[py, px]
    r = (dmin + (dmax - dmin) * t) * 0.5
    return _u8((d <= r) & (r > 0) & (mask > 0))


def _stripes(X, Y, angle_deg, pitch, width):
    th = math.radians(angle_deg)
    u = X * math.cos(th) + Y * math.sin(th)
    return np.mod(u, pitch) < width


def fx_hatch(mask, ctx, a):
    if not mask.any():
        return mask
    X, Y = ctx.grid_mm(mask.shape)
    on = _stripes(X, Y, a["angle"], a["pitch_mm"], a["width_mm"])
    if a["cross"] == "cross":
        on |= _stripes(X, Y, a["angle"] + 90, a["pitch_mm"], a["width_mm"])
    return _u8(on & (mask > 0))


def fx_levels(mask, ctx, a):
    if not mask.any():
        return mask
    dist = _dist_inside(mask) / ctx.ppm
    return _u8((mask > 0) & (np.mod(dist, a["pitch_mm"]) < a["width_mm"]))


def fx_pattern(mask, ctx, a):
    if not mask.any():
        return mask
    X, Y = ctx.grid_mm(mask.shape)
    size, gap = a["size_mm"], a["gap_mm"]
    shape = a["shape"]
    if shape == "diamond":                        # square grid turned 45°
        Xr, Yr = (X + Y) / math.sqrt(2), (Y - X) / math.sqrt(2)
        lx = np.mod(Xr, size) - size / 2
        ly = np.mod(Yr, size) - size / 2
        half = size / 2 - gap / 2
        on = (np.abs(lx) <= half) & (np.abs(ly) <= half)
    elif shape == "hexagon":                      # pointy-top hexagons, size = width across flats
        ap = size / 2                              # apothem with the joint
        R = ap * 2 / math.sqrt(3)
        wc, hc = 2 * ap, 3 * R
        best = None
        for ox, oy in ((0.0, 0.0), (wc / 2, hc / 2)):
            dx = np.mod(X - ox, wc) - wc / 2
            dy = np.mod(Y - oy, hc) - hc / 2
            dd = dx * dx + dy * dy
            if best is None:
                best, bx, by = dd, dx, dy
            else:
                sel = dd < best
                best = np.where(sel, dd, best)
                bx, by = np.where(sel, dx, bx), np.where(sel, dy, by)
        a2 = ap - gap / 2
        qx, qy = np.abs(bx), np.abs(by)
        on = (qx <= a2) & (qx * 0.5 + qy * (math.sqrt(3) / 2) <= a2)
    elif shape == "brick":
        bw, bh = size, size / 2
        row = np.floor(Y / bh)
        lx = np.mod(X + np.mod(row, 2) * bw / 2, bw)
        ly = np.mod(Y, bh)
        g = gap / 2
        on = (lx >= g) & (lx <= bw - g) & (ly >= g) & (ly <= bh - g)
    else:                                          # five-point stars on a staggered grid
        row = np.floor(Y / size)
        lx = np.mod(X + np.mod(row, 2) * size / 2, size) - size / 2
        ly = np.mod(Y, size) - size / 2
        r = np.hypot(lx, ly)
        th = np.arctan2(lx, -ly)                   # 0 = up: a point upwards
        tip = np.abs(np.mod(th / (2 * np.pi / 5) + 0.5, 1) - 0.5) * 2   # 0 at the tips, 1 between
        Ro = size / 2 - gap / 2
        Ri = Ro * 0.42
        on = r <= Ro - (Ro - Ri) * tip
    return _u8(on & (mask > 0))


def fx_outline(mask, ctx, a):
    w = a["width_mm"] * ctx.ppm
    return _u8((mask > 0) & (_dist_inside(mask) <= w))


def _shift(mask, dx_px, dy_px):
    M = np.float32([[1, 0, dx_px], [0, 1, dy_px]])
    return cv2.warpAffine(mask, M, (mask.shape[1], mask.shape[0]), flags=cv2.INTER_NEAREST, borderValue=0)


def fx_shadow(mask, ctx, a):
    j = ctx.target(int(a["layer"]), default_last=True)
    if j is None or not mask.any():
        return mask
    sh = _shift(mask, a["dx_mm"] * ctx.ppm, a["dy_mm"] * ctx.ppm)
    sh = sh & ~mask & 255
    if j == ctx.index:
        return mask | sh
    ctx.masks[j] = ctx.masks[j] | sh
    ctx.touched.add(j)
    return mask


def fx_halo(mask, ctx, a):
    if not mask.any():
        return mask
    ppm = ctx.ppm
    do = _dist_outside(mask)
    ring = _u8((do > a["gap_mm"] * ppm) & (do <= (a["gap_mm"] + a["width_mm"]) * ppm))
    j = ctx.target(int(a["layer"]), default_last=False)
    if j is None:                                  # bare support: the ring is removed from the others
        for k in range(len(ctx.masks)):
            if k != ctx.index and (ctx.masks[k] & ring).any():
                ctx.masks[k] = ctx.masks[k] & ~ring & 255
                ctx.touched.add(k)
        ctx.bare = ring if ctx.bare is None else (ctx.bare | ring)
        return mask
    if j == ctx.index:
        return mask | ring
    ctx.masks[j] = ctx.masks[j] | ring
    ctx.touched.add(j)
    return mask


def fx_mosaic(mask, ctx, a):
    if not mask.any():
        return mask
    H, W = mask.shape
    ppm = ctx.ppm
    cell = max(2.0, a["cell_mm"] * ppm)
    rng = np.random.default_rng(int(a["seed"]))
    # jittered grid anchored to the support
    x0 = -(ctx.off_px[0] % cell) - cell
    y0 = -(ctx.off_px[1] % cell) - cell
    nx, ny = int(W / cell) + 3, int(H / cell) + 3
    gx, gy = np.meshgrid(np.arange(nx), np.arange(ny))
    jit = rng.random((ny, nx, 2)) * 0.8 + 0.1
    sx = (x0 + (gx + jit[..., 0]) * cell).ravel()
    sy = (y0 + (gy + jit[..., 1]) * cell).ravel()
    keep = (sx >= 0) & (sx < W) & (sy >= 0) & (sy < H)
    seeds = np.ones((H, W), np.uint8)
    seeds[sy[keep].astype(int), sx[keep].astype(int)] = 0
    if seeds.all():
        return mask
    _, labels = cv2.distanceTransformWithLabels(seeds, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    edge = np.zeros((H, W), bool)
    edge[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    edge[1:, :] |= labels[1:, :] != labels[:-1, :]
    joints = cv2.dilate(_u8(edge), _disk(max(0.5, a["joint_mm"] * ppm / 2)))
    return mask & ~joints & 255


def fx_bridges(mask, ctx, a):
    if not mask.any():
        return mask
    w = a["width_mm"]
    style = a["style"]
    if style == "rays":
        m = cv2.moments(mask, binaryImage=True)
        if m["m00"] <= 0:
            return mask
        cx, cy = m["m10"] / m["m00"], m["m01"] / m["m00"]
        H, W = mask.shape
        ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
        dx, dy = xs - cx, ys - cy
        r = np.hypot(dx, dy)
        step = 2 * math.pi / max(3, int(a["count"]))
        th = np.arctan2(dy, dx) - math.radians(a["angle"])
        delta = np.abs(np.mod(th / step + 0.5, 1) - 0.5) * step
        solid = r * np.sin(delta) < w * ctx.ppm / 2
    else:
        X, Y = ctx.grid_mm(mask.shape)
        p = a["pitch_mm"]
        solid = _stripes(X, Y, a["angle"], p, w)
        if style == "grid":
            solid |= _stripes(X, Y, a["angle"] + 90, p, w)
    return _u8((mask > 0) & ~solid)


def fx_overlap(mask, ctx, a):
    later = ctx.later()
    if not later.any() or not mask.any():
        return mask
    grown = cv2.dilate(mask, _disk(a["width_mm"] * ctx.ppm))
    add = grown & later & ~mask & 255
    ctx.under[ctx.index] = add if ctx.index not in ctx.under else (ctx.under[ctx.index] | add)
    return mask | add


def fx_merge(mask, ctx, a):
    r = a["distance_mm"] * ctx.ppm / 2
    m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _disk(r)) if r >= 0.5 else mask
    amin = a["min_area_mm2"] * ctx.ppm * ctx.ppm
    if amin >= 1:
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        small = np.zeros(n, bool)
        small[1:] = st[1:, cv2.CC_STAT_AREA] < amin
        m = m.copy()
        m[small[lab]] = 0
    return m


APPLY = {"smooth": fx_smooth, "polygon": fx_polygon, "angular": fx_angular, "rough": fx_rough,
         "wavy": fx_wavy, "offset": fx_offset, "halftone": fx_halftone, "hatch": fx_hatch,
         "levels": fx_levels, "pattern": fx_pattern, "outline": fx_outline, "shadow": fx_shadow,
         "halo": fx_halo, "mosaic": fx_mosaic, "bridges": fx_bridges, "overlap": fx_overlap,
         "merge": fx_merge}
assert set(APPLY) == set(EFFECTS)
assert all(e["category"] in CATEGORIES for e in EFFECTS.values())


# --------------------------------------------------------------------------
# Stack application
# --------------------------------------------------------------------------

def clean_after(mask: np.ndarray, p, limit: np.ndarray | None) -> np.ndarray:
    """Material limits after the effects: minimum opening, minimum strip, no tiny loose piece of
    material. Small openings are kept (a halftone is made of them)."""
    ppm = p.px_per_mm
    m = mask
    if limit is not None:
        m = m & limit
    r_open = p.min_opening_mm * ppm / 2
    if r_open >= 0.5:
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, _disk(r_open))
    r_close = p.min_strip_mm * ppm / 2
    if r_close >= 0.5:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, _disk(r_close))
    amin = int(p.min_area_mm2 * ppm * ppm)
    if amin > 1:                                   # loose pieces of material too small to hold
        inv = 255 - m
        n, lab, st, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
        H, W = m.shape
        small = np.zeros(n, bool)
        for i in range(1, n):
            x, y, w, h, area = st[i]
            small[i] = area < amin and x > 0 and y > 0 and x + w < W and y + h < H
        if small.any():
            m = m.copy()
            m[small[lab]] = 255
    return m


def pass_on(orig: list, out: list, ctx: Context, changed: set, opts: dict) -> set:
    """Exclusive stacking: passes the changes made by the effects on to the other layers.
    Returns the layers changed here."""
    n = len(out)
    gained, lost = {}, {}
    for i in changed:
        gained[i] = out[i] & ~orig[i] & 255
        if i in ctx.under:                            # Overlap: meant to stay under the next layers
            gained[i] &= ~ctx.under[i] & 255
        lost[i] = orig[i] & ~out[i] & 255
        if ctx.bare is not None:                      # halo left as bare support on purpose
            lost[i] &= ~ctx.bare & 255
    touched = set()
    if opts["sync"]:
        for i in sorted(gained):
            if not gained[i].any():
                continue
            for k in range(i + 1, n):                 # darker layers, painted later: they would hide it
                if (out[k] & gained[i]).any():
                    out[k] = out[k] & ~gained[i] & 255
                    touched.add(k)
    if opts["freed"] != "support":
        for i in sorted(lost):
            free = lost[i].copy()
            for k in range(n):                        # already painted by another layer: nothing to do
                free &= ~out[k] & 255
            if not free.any():
                continue
            if opts["freed"] == "lighter":
                if i > 0:
                    out[i - 1] = out[i - 1] | free
                    touched.add(i - 1)
                continue
            # surrounding layer: each area of the layer (as it was before the effects) gives what was
            # freed in it to the layer found most along its border, or leaves it bare when the
            # bare support surrounds it most
            # outer border only: the holes of an area (e.g. letters inside it) do not vote
            cnts, _ = cv2.findContours(orig[i], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            filled = np.zeros_like(orig[i])
            cv2.drawContours(filled, cnts, -1, 255, -1)
            ncomp, comp = cv2.connectedComponents((filled > 0).astype(np.uint8), connectivity=8)
            if ncomp < 2:
                continue
            k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            near = cv2.dilate(comp.astype(np.float32), k3).astype(np.int32)   # area touching each border pixel
            ring = (filled == 0) & (near > 0)
            union = np.zeros_like(free)
            for m in orig:
                union |= m
            cands = [k for k in range(n) if k != i]
            votes = [np.bincount(near[ring & (out[k] > 0)], minlength=ncomp) for k in cands]
            votes.append(np.bincount(near[ring & (union == 0)], minlength=ncomp))   # bare support
            best = np.argmax(np.stack(votes), axis=0)          # per area: index in cands (len = bare)
            sel = free > 0
            for c, k in enumerate(cands):
                areas = np.nonzero(best == c)[0]
                areas = areas[areas > 0]
                if not len(areas):
                    continue
                part = sel & np.isin(comp, areas)
                if part.any():
                    out[k] = out[k] | _u8(part)
                    touched.add(k)
    return touched


def apply_all(masks: list, effects: dict, p, image_bgr: np.ndarray, off_px: tuple,
              limit: np.ndarray | None = None, opts: dict | None = None) -> list:
    """Applies the stacks to the colour layer masks (image area), in spraying order.
    `limit`: area the openings must stay in (removed background), None = whole image.
    `opts`: see `options` (exclusive stacking only; None = no passing on)."""
    orig = list(masks)
    out = list(masks)
    ctx = Context(ppm=p.px_per_mm, off_px=off_px, image_bgr=image_bgr, masks=out)
    done = set()
    for i in range(len(out)):
        stack = effects.get(i + 1)
        if not stack:
            continue
        ctx.index = i
        m = out[i]
        for kind, args in stack:
            m = APPLY[kind](m, ctx, args)
        out[i] = m
        done.add(i)
    if opts and getattr(p, "layering", "exclusive") == "exclusive":
        ctx.touched |= pass_on(orig, out, ctx, done | ctx.touched, opts)
    for i in sorted(done | ctx.touched):
        out[i] = clean_after(out[i], p, limit)
    return out
