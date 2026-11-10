"""Serveur web local StencilIt.  Lancer : python app.py  puis ouvrir http://127.0.0.1:5000"""
from __future__ import annotations

import base64
import json
import threading
import time
import uuid
import zipfile
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_file, send_from_directory
import io

from stencilit import pipeline as pl
from stencilit import semantic
from stencilit.svg_export import export_zip

ROOT = Path(__file__).parent
MATERIALS_FILE = ROOT / "stencilit" / "materials.json"

app = Flask(__name__, static_folder=str(ROOT / "static"))
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024

# In-memory sessions (local single-user application)
SESSIONS: dict[str, dict] = {}
LOCK = threading.Lock()

PREP_KEYS = ("support_w_mm", "support_h_mm", "px_per_mm", "detail", "n_layers", "color_mode", "skip_support",
             "pre_auto_levels", "pre_clahe", "pre_gamma", "manual_thresholds", "thresholds",
             "pre_saturation", "pre_sharpen", "pre_remove_bg", "protect_lines")


def materials() -> dict:
    return json.loads(MATERIALS_FILE.read_text(encoding="utf-8"))


# ---------------- User-saved presets ----------------
USER_PRESETS_FILE = ROOT / "presets_utilisateur.json"
PRESET_KINDS = ("support", "material", "palette", "sheet")


def load_user_presets() -> dict:
    try:
        data = json.loads(USER_PRESETS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    return {k: dict(data.get(k, {})) for k in PRESET_KINDS}


def save_user_presets(data: dict) -> None:
    tmp = USER_PRESETS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(USER_PRESETS_FILE)  # atomic write


@app.get("/api/presets")
def api_presets():
    return jsonify(load_user_presets())


@app.post("/api/presets/<kind>")
def api_preset_save(kind):
    if kind not in PRESET_KINDS:
        return jsonify(error="Type de réglage inconnu"), 404
    body = request.get_json(force=True)
    name = str(body.get("name", "")).strip()[:60]
    values = body.get("values")
    if not name or not isinstance(values, dict):
        return jsonify(error="Nom ou valeurs manquants"), 400
    with LOCK:
        data = load_user_presets()
        data[kind][name] = values
        save_user_presets(data)
    return jsonify(data)


@app.post("/api/presets/<kind>/rename")
def api_preset_rename(kind):
    if kind not in PRESET_KINDS:
        return jsonify(error="Type de réglage inconnu"), 404
    body = request.get_json(force=True)
    old = str(body.get("old", "")).strip()
    new = str(body.get("new", "")).strip()[:60]
    overwrite = bool(body.get("overwrite", False))
    with LOCK:
        data = load_user_presets()
        if old not in data[kind]:
            return jsonify(error=f"« {old} » n'existe pas"), 404
        if not new:
            return jsonify(error="Nouveau nom manquant"), 400
        if new != old and new in data[kind] and not overwrite:
            return jsonify(error=f"« {new} » existe déjà", exists=True), 409
        data[kind][new] = data[kind].pop(old)
        save_user_presets(data)
    return jsonify(data)


@app.delete("/api/presets/<kind>/<path:name>")
def api_preset_delete(kind, name):
    if kind not in PRESET_KINDS:
        return jsonify(error="Type de réglage inconnu"), 404
    with LOCK:
        data = load_user_presets()
        data[kind].pop(name, None)
        save_user_presets(data)
    return jsonify(data)


def png_b64(img: np.ndarray, max_side: int = 1100) -> str:
    h, w = img.shape[:2]
    s = max_side / max(h, w)
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", img)
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()


PREVIEW_MAX = 1100  # longest side of the preview images (px)


def rgba_b64(color_bgr, alpha: np.ndarray) -> str:
    """RGBA PNG: plain layer colour, transparency = mask (0..1)."""
    h, w = alpha.shape
    img = np.empty((h, w, 4), np.uint8)
    img[..., :3] = np.asarray(color_bgr, np.uint8)
    img[..., 3] = np.clip(alpha * 255 + 0.5, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()


def hex_to_bgr(h: str):
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/materials")
def api_materials():
    return jsonify(materials())


@app.post("/api/upload")
def api_upload():
    f = request.files.get("image")
    if not f:
        return jsonify(error="Aucune image reçue"), 400
    raw = f.read()
    try:
        img = pl.decode_image(raw)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(new_session(img, raw, f.filename or "image"))


def new_session(img: np.ndarray, raw: bytes, filename: str) -> dict:
    """Creates a session; the original file is kept as is for the project export."""
    sid = uuid.uuid4().hex
    with LOCK:
        SESSIONS[sid] = {"img": img, "name": Path(filename).stem, "raw": raw,
                         "ext": (Path(filename).suffix.lower() or ".png")}
    h, w = img.shape[:2]
    return dict(id=sid, width=w, height=h, gray=pl.is_grayscale(img), original=png_b64(img),
                filename=Path(filename).name)


@app.post("/api/recommend")
def api_recommend():
    data = request.get_json(force=True)
    sess = SESSIONS.get(data.get("id", ""))
    if not sess:
        return jsonify(error="Session inconnue, rechargez l'image"), 404
    mode = data.get("color_mode", "auto")
    skip = bool(data.get("skip_support", True))
    p = pl.Params.from_dict(data.get("crop", {}))
    x0, y0, x1, y1 = pl.crop_rect(p, sess["img"].shape)
    src = pl.preprocess_image(sess["img"][y0:y1, x0:x1], p)   # recommendation on the preprocessed image
    gray = pl.is_grayscale(src) if mode == "auto" else mode == "gray"
    key = (gray, skip, x0, y0, x1, y1, p.pre_auto_levels, p.pre_clahe, p.pre_gamma, p.pre_saturation, p.pre_sharpen)
    cache = sess.setdefault("reco", {})
    if key not in cache:
        cache[key] = pl.recommend_layers(src, gray, skip)
    return jsonify(cache[key])


@app.post("/api/mask")
def api_mask():
    """Receives the painted mask (transparent PNG, at the size of the source image preview).
    Painted (opaque) pixels delimit the areas where key details are searched."""
    data = request.get_json(force=True)
    sess = SESSIONS.get(data.get("id", ""))
    if not sess:
        return jsonify(error="Session inconnue, rechargez l'image"), 404
    png = data.get("png")
    if not png:
        sess.pop("mask", None)
        return jsonify(coverage=0.0)
    try:
        raw = base64.b64decode(png.split(",", 1)[-1])
        m = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
    except (ValueError, cv2.error):
        m = None
    if m is None:
        return jsonify(error="Masque illisible"), 400
    alpha = m[..., 3] if (m.ndim == 3 and m.shape[2] == 4) else (m if m.ndim == 2 else m[..., 2])
    if not (alpha > 0).any():
        sess.pop("mask", None)
        return jsonify(coverage=0.0)
    h, w = sess["img"].shape[:2]
    full = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_LINEAR)
    sess["mask"] = np.where(full > 127, 255, 0).astype(np.uint8)
    return jsonify(coverage=round(100 * float((sess["mask"] > 0).mean()), 1))


def subject_overlay(sess) -> str | None:
    """Cut-out preview, at the size of the source image preview: darkened background (transparent elsewhere)."""
    fg = sess.get("fg")
    if fg is None:
        return None
    h, w = fg.shape
    s = min(1.0, 1100 / max(h, w))
    small = cv2.resize(fg.astype(np.uint8) * 255, (max(1, round(w * s)), max(1, round(h * s))),
                       interpolation=cv2.INTER_AREA)
    return rgba_b64((15, 15, 15), (255 - small).astype(np.float32) / 255.0 * 0.72)


def set_subject(sess, painted, exact: bool = False) -> dict:
    """Stores the painted subject area and computes the cut-out: GrabCut around a roughly painted
    area, or the mask as is when it comes from the object selection (exact outline)."""
    if painted is None or not (painted > 0).any():
        sess.pop("subject", None)
        sess.pop("fg", None)
        exact = False
    else:
        sess["subject"] = painted
        sess["fg"] = (painted > 0) if exact else pl.grabcut_subject(sess["img"], painted)
    sess["subject_exact"] = exact
    sess["fg_ver"] = sess.get("fg_ver", 0) + 1
    fg = sess.get("fg")
    return dict(coverage=round(100 * float((painted > 0).mean()), 1) if sess.get("subject") is not None else 0.0,
                subject_pct=round(100 * float(fg.mean()), 1) if fg is not None else None, exact=exact,
                overlay=subject_overlay(sess))


@app.post("/api/subject")
def api_subject():
    """Receives the area painted around the subject (transparent PNG, source image preview size)
    and returns the computed cut-out (removed background = bare support)."""
    data = request.get_json(force=True)
    sess = SESSIONS.get(data.get("id", ""))
    if not sess:
        return jsonify(error="Session inconnue, rechargez l'image"), 404
    png = data.get("png")
    painted = None
    if png:
        try:
            m = cv2.imdecode(np.frombuffer(base64.b64decode(png.split(",", 1)[-1]), np.uint8), cv2.IMREAD_UNCHANGED)
        except (ValueError, cv2.error):
            m = None
        if m is None:
            return jsonify(error="Masque illisible"), 400
        alpha = m[..., 3] if (m.ndim == 3 and m.shape[2] == 4) else (m if m.ndim == 2 else m[..., 2])
        h, w = sess["img"].shape[:2]
        painted = np.where(cv2.resize(alpha, (w, h), interpolation=cv2.INTER_LINEAR) > 127, 255, 0).astype(np.uint8)
    with LOCK:
        out = set_subject(sess, painted, bool(data.get("exact")))
    return jsonify(out)


def semantic_state(sess) -> dict:
    """Image analysed by the selection model (computed once per session; concurrent calls wait)."""
    with LOCK:
        lock = sess.setdefault("sem_lock", threading.Lock())
    with lock:
        if sess.get("sem") is None:
            sess["sem"] = semantic.embed(sess["img"])
        return sess["sem"]


@app.post("/api/semantic/prepare")
def api_semantic_prepare():
    """Analyses the image in advance (and downloads the model the first time), so that the first
    click on an object is immediate."""
    data = request.get_json(force=True)
    sess = SESSIONS.get(data.get("id", ""))
    if not sess:
        return jsonify(error="Session inconnue, rechargez l'image"), 404
    t = time.perf_counter()
    try:
        semantic_state(sess)
    except semantic.SemanticError as e:
        return jsonify(error=str(e)), 503
    return jsonify(ok=True, seconds=round(time.perf_counter() - t, 2))


@app.post("/api/semantic/select")
def api_semantic_select():
    """Mask of the object under the click: grey PNG at the size of the mask canvas (w, h).
    points = [[x, y, label], …] in fractions of the image, label 1 = object, 0 = not the object."""
    data = request.get_json(force=True)
    sess = SESSIONS.get(data.get("id", ""))
    if not sess:
        return jsonify(error="Session inconnue, rechargez l'image"), 404
    try:
        w, h = int(data["w"]), int(data["h"])
        points = [(float(x), float(y), int(l)) for x, y, l in data["points"]][:16]
        level = int(data.get("level", 0))
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Requête de sélection invalide"), 400
    if not points or not (0 < w <= 4096 and 0 < h <= 4096):
        return jsonify(error="Requête de sélection invalide"), 400
    try:
        m = semantic.select(semantic_state(sess), points, (w, h), level)
    except semantic.SemanticError as e:
        return jsonify(error=str(e)), 503
    ok, buf = cv2.imencode(".png", m.astype(np.uint8) * 255)
    return jsonify(png="data:image/png;base64," + base64.b64encode(buf.tobytes()).decode(),
                   pct=round(100 * float(m.mean()), 1))


@app.post("/api/prepreview")
def api_prepreview():
    """Instant preprocessing preview (without computing the stencils): visible part of the image,
    preprocessed at preview size and placed on the support, + luminance histogram."""
    data = request.get_json(force=True)
    sess = SESSIONS.get(data.get("id", ""))
    if not sess:
        return jsonify(error="Session inconnue, rechargez l'image"), 404
    p = pl.Params.from_dict(data.get("params", {}))
    lay, _ = pl.resolve_layout(p, sess["img"].shape)
    ppm = p.px_per_mm
    SW, SH = round(p.support_w_mm * ppm), round(p.support_h_mm * ppm)
    k = min(1.0, PREVIEW_MAX / max(SW, SH))
    size = (max(1, round(SW * k)), max(1, round(SH * k)))
    vx0, vy0, vx1, vy1 = lay.vis_mm
    r = (round(vx0 * ppm * k), round(vy0 * ppm * k), round(vx1 * ppm * k), round(vy1 * ppm * k))
    r = (r[0], r[1], min(size[0], max(r[0] + 1, r[2])), min(size[1], max(r[1] + 1, r[3])))
    x0, y0, x1, y1 = lay.src_rect
    part = cv2.resize(sess["img"][y0:y1, x0:x1], (r[2] - r[0], r[3] - r[1]), interpolation=cv2.INTER_AREA)
    part = pl.preprocess_image(part, p, ppm * k)          # same sharpening radius in mm as in the full computation
    fg = None
    if p.pre_remove_bg and sess.get("fg") is not None:
        fg = cv2.resize(sess["fg"][y0:y1, x0:x1].astype(np.uint8) * 255, (part.shape[1], part.shape[0]),
                        interpolation=cv2.INTER_LINEAR) > 127
    support = pl.hex_to_bgr(p.support_color).astype(np.uint8)
    if fg is not None:
        part[~fg] = support
    out = np.empty((size[1], size[0], 3), np.uint8)
    out[:] = support
    out[r[1]:r[3], r[0]:r[2]] = part
    L = cv2.cvtColor(part, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32) * (100.0 / 255.0)
    Lh = L[fg] if fg is not None and fg.any() else L.ravel()
    hist = np.bincount(np.clip(Lh, 0, 99.999).astype(np.int32), minlength=100).astype(np.float64)
    hist = (hist / max(1.0, hist.max())).round(4).tolist()
    return jsonify(image=png_b64(out), size=list(size), histogram=hist)


@app.post("/api/process")
def api_process():
    data = request.get_json(force=True)
    sess = SESSIONS.get(data.get("id", ""))
    if not sess:
        return jsonify(error="Session inconnue, rechargez l'image"), 404
    p = pl.Params.from_dict(data.get("params", {}))
    lay, warnings = pl.resolve_layout(p, sess["img"].shape)
    t0 = time.perf_counter()
    key = (tuple(getattr(p, k) for k in PREP_KEYS) + (lay.src_rect, tuple(round(v, 3) for v in lay.vis_mm))
           + ((sess.get("fg_ver", 0),) if p.pre_remove_bg else ()))
    if sess.get("prep_key") != key:
        sess["prep"] = pl.prepare(sess["img"], p, lay, sess.get("fg") if p.pre_remove_bg else None)
        sess["prep_key"] = key
    # Key-detail mask (painted in the Masks tab, outline mask), brought to the computed image area
    region = None
    if p.outline and sess.get("mask") is not None:
        x0, y0, x1, y1 = lay.src_rect
        H, W = sess["prep"].labels.shape
        region = cv2.resize(sess["mask"][y0:y1, x0:x1], (W, H), interpolation=cv2.INTER_NEAREST) > 0
    res = pl.build(sess["prep"], p, region)
    sess["result"] = res
    sess["material"] = data.get("material")
    sess["ui"] = data.get("ui")          # full interface state, for the project file
    sheet = hex_to_bgr((data.get("material") or {}).get("sheet_color", "#c8d3dc"))
    # Preview layers (support area): layer colour + transparency = openings.
    # The browser stacks them itself -> hiding a layer or toggling the blur is instant.
    # Everything is projected straight to the preview size (a large support costs no more).
    SW, SH = res.support_px
    k = min(1.0, PREVIEW_MAX / max(SW, SH))
    size = (max(1, round(SW * k)), max(1, round(SH * k)))
    sig = max(0.3, p.spray_mm * p.px_per_mm)
    (sx0, sy0, sx1, sy1), (ox, oy) = pl.support_overlap(res)
    dst = (round(sx0 * k), round(sy0 * k), round(sx1 * k), round(sy1 * k))

    def to_preview(arr):
        out = np.zeros((size[1], size[0]), np.float32)
        if dst[2] > dst[0] and dst[3] > dst[1]:
            part = arr[sy0 + oy:sy1 + oy, sx0 + ox:sx1 + ox]
            out[dst[1]:dst[3], dst[0]:dst[2]] = cv2.resize(part, (dst[2] - dst[0], dst[3] - dst[1]),
                                                           interpolation=cv2.INTER_AREA)
        return out

    layers = []
    for L in res.layers:
        mask = L.opening.astype(np.float32) / 255.0
        layers.append({
            "index": L.index,
            "color": pl.bgr_hex(L.color),
            # layer view without highlights + bridges and removed details as separate overlays
            # (shown / hidden in the browser)
            "image": png_b64(pl.layer_view(res, L, sheet, bridges=False, lost=False), 900),
            **{k: (png_b64(o, 900) if k != "img_merged" or L.n_merged else None)
               for k, o in zip(("img_bridges", "img_lost", "img_merged"), pl.layer_overlays(res, L))},
            "mask_flat": rgba_b64(L.color, to_preview(mask)),
            "mask_sim": rgba_b64(L.color, to_preview(cv2.GaussianBlur(mask, (0, 0), sig) * 0.97)),
            **pl.layer_stats(L),
        })
    _, reg_warn = pl.registration_shapes(res)
    # Original placed on the support, to compare at scale (raw and preprocessed)
    H, W = res.prepared.labels.shape
    ix, iy = res.prepared.off_px
    r = (round(ix * k), round(iy * k), max(round(ix * k) + 1, round((ix + W) * k)), max(round(iy * k) + 1, round((iy + H) * k)))
    r = (r[0], r[1], min(size[0], r[2]), min(size[1], r[3]))

    def on_support(im):
        out = np.empty((size[1], size[0], 3), np.uint8)
        out[:] = res.support_color.astype(np.uint8)
        out[r[1]:r[3], r[0]:r[2]] = cv2.resize(im, (r[2] - r[0], r[3] - r[1]), interpolation=cv2.INTER_AREA)
        return out
    ref = on_support(res.prepared.raw if res.prepared.raw is not None else res.prepared.resized)
    pre_on = pl.preprocess_active(p) or res.prepared.fg is not None
    sheet_sim = pl.simulate_sheet(res)
    return jsonify(
        reference=png_b64(ref),
        reference_pre=png_b64(on_support(pre_view(res))) if pre_on else None,
        subject_used=res.prepared.fg is not None,
        histogram=res.prepared.hist,
        auto_thresholds=res.prepared.auto_thresholds,
        thresholds_used=res.prepared.thresholds_used,
        palette=[pl.bgr_hex(c) for c in res.prepared.palette],
        preview_size=list(size),
        layers=layers,
        base=pl.bgr_hex(res.support_color),
        support_tone=(pl.bgr_hex(res.prepared.palette[res.support_label])
                      if res.support_label is not None else None),
        warnings=warnings + reg_warn,
        gray=res.prepared.gray,
        sheet_mm=[round(v, 1) for v in res.sheet_mm],
        sheet_rect_mm=[round(v, 2) for v in res.sheet_rect_mm],
        positioning=pl.positioning(res),
        support_mm=[round(v, 1) for v in res.support_mm],
        image_mm=[round(v, 1) for v in lay.img_mm],
        visible_mm=[round(lay.vis_mm[2] - lay.vis_mm[0], 1), round(lay.vis_mm[3] - lay.vis_mm[1], 1)],
        delta_e=round(pl.delta_e(res, sheet_sim), 1),
        lines_added=res.lines_added,
        seconds=round(time.perf_counter() - t0, 2),
    )


@app.post("/api/outline_preview")
def api_outline_preview():
    """Outline stencil detection preview, over the computed image area of the source image preview
    (Masks tab): detected lines not kept (blue), lines too short (orange), final stroke (red).
    Uses the colour layers of the last computation and the current outline settings."""
    data = request.get_json(force=True)
    sess = SESSIONS.get(data.get("id", ""))
    if not sess:
        return jsonify(error="Session inconnue, rechargez l'image"), 404
    res = sess.get("result")
    if res is None:
        return jsonify(error="Aperçu de la détection : lancez d'abord un calcul"), 409
    p = pl.Params.from_dict(data.get("params", {}))
    lay, _ = pl.resolve_layout(res.params, sess["img"].shape)
    x0, y0, x1, y1 = lay.src_rect
    H, W = res.prepared.labels.shape
    region = None
    if sess.get("mask") is not None:
        region = cv2.resize(sess["mask"][y0:y1, x0:x1], (W, H), interpolation=cv2.INTER_NEAREST) > 0
    st = pl.outline_detection(res, p, region)
    # size of the computed area in the source image preview (same scale as the mask canvas)
    h, w = sess["img"].shape[:2]
    s = min(1.0, 1100 / max(h, w))
    size = (max(1, round((x1 - x0) * s)), max(1, round((y1 - y0) * s)))
    k = size[0] / W                                   # preview px per computed px
    grow = np.ones((max(1, round(1.2 / k)),) * 2, np.uint8)   # thin lines stay visible once reduced
    rgba = np.zeros((H, W, 4), np.uint8)
    layers = [(st["detected"] & ~st["selected"], (235, 150, 40, 200), True),
              (st["short"], (0, 150, 255, 235), True)]
    if st.get("present") is not None:      # lines merged into the layers: those already cut there
        layers.append((cv2.dilate(st["present"].astype(np.uint8), np.ones((3, 3), np.uint8)) > 0,
                       (200, 60, 190, 225), True))
    layers.append((st["stroke"], (40, 30, 225, 215), False))
    for m, col, thick in layers:
        if thick:
            m = cv2.dilate(m.astype(np.uint8), grow) > 0
        rgba[m] = col
    small = cv2.resize(rgba, size, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", small, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    n_lines = cv2.connectedComponents(st["kept"].astype(np.uint8), connectivity=8)[0] - 1
    return jsonify(
        image="data:image/png;base64," + base64.b64encode(buf.tobytes()).decode(),
        rect=[x0 / w, y0 / h, (x1 - x0) / w, (y1 - y0) / h],
        lines=int(n_lines),
        present=int(cv2.connectedComponents(st["present"].astype(np.uint8), connectivity=8)[0] - 1)
        if st.get("present") is not None else None,
        stroke_pct=round(100 * float(st["stroke"].mean()), 1),
    )


def pre_view(res):
    """Preprocessed image; removed background shown in the support colour."""
    im = res.prepared.resized
    if res.prepared.fg is not None:
        im = im.copy()
        im[~res.prepared.fg] = res.support_color.astype(np.uint8)
    return im


@app.get("/api/export/<sid>")
def api_export(sid):
    sess = SESSIONS.get(sid)
    if not sess or "result" not in sess:
        return jsonify(error="Rien à exporter"), 404
    mask_png = None
    if sess.get("mask") is not None:
        ok, buf = cv2.imencode(".png", sess["mask"])
        mask_png = buf.tobytes()
    subject_png = None
    if sess.get("subject") is not None:
        ok, buf = cv2.imencode(".png", sess["subject"])
        subject_png = buf.tobytes()
    lang = "fr" if request.args.get("lang") == "fr" else "en"
    data = export_zip(sess["result"], sess.get("material"), sess["name"],
                      original=(sess.get("raw"), sess.get("ext", ".png")), mask_png=mask_png,
                      ui=sess.get("ui"), subject_png=subject_png, lang=lang,
                      subject_exact=bool(sess.get("subject_exact")))
    return send_file(io.BytesIO(data), mimetype="application/zip", as_attachment=True,
                     download_name=f"{sess['name']}_{'pochoirs' if lang == 'fr' else 'stencils'}.zip")


@app.post("/api/project")
def api_project():
    """Opens an exported project (.zip): original image, masks and full settings."""
    f = request.files.get("project")
    if not f:
        return jsonify(error="Aucun fichier reçu"), 400
    try:
        z = zipfile.ZipFile(io.BytesIO(f.read()))
    except zipfile.BadZipFile:
        return jsonify(error="Ce fichier n'est pas un zip de projet StencilIt"), 400
    names = z.namelist()
    info_name = next((n for n in names if n.endswith("_infos.json")), None)
    if not info_name:
        return jsonify(error="Fichier …_infos.json introuvable dans le zip"), 400
    info = json.loads(z.read(info_name).decode("utf-8"))
    proj = info.get("projet") or {}
    img_name = proj.get("image")
    if not img_name or img_name not in names:
        return jsonify(error="Ce zip ne contient pas l'image d'origine (export d'une version "
                             "antérieure) : chargez l'image puis ouvrez le fichier …_infos.json"), 400
    raw = z.read(img_name)
    try:
        img = pl.decode_image(raw)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    out = new_session(img, raw, proj.get("nom_image") or img_name)
    sess = SESSIONS[out["id"]]
    sess["name"] = proj.get("nom") or sess["name"]
    mask_b64, coverage = None, 0.0
    m_name = proj.get("masque")
    if m_name and m_name in names:
        m = cv2.imdecode(np.frombuffer(z.read(m_name), np.uint8), cv2.IMREAD_GRAYSCALE)
        if m is not None and m.any():
            h, w = img.shape[:2]
            m = cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)
            sess["mask"] = np.where(m > 127, 255, 0).astype(np.uint8)
            coverage = round(100 * float((sess["mask"] > 0).mean()), 1)
            ok, buf = cv2.imencode(".png", sess["mask"])
            mask_b64 = "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()
    subject = None
    s_name = proj.get("masque_sujet")
    if s_name and s_name in names:
        m = cv2.imdecode(np.frombuffer(z.read(s_name), np.uint8), cv2.IMREAD_GRAYSCALE)
        if m is not None and m.any():
            h, w = img.shape[:2]
            m = np.where(cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST) > 127, 255, 0).astype(np.uint8)
            subject = set_subject(sess, m, bool(proj.get("masque_sujet_exact")))
            ok, buf = cv2.imencode(".png", m)
            subject["png"] = "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()
    return jsonify({**out, "info": info, "mask": mask_b64, "mask_coverage": coverage, "subject": subject})


if __name__ == "__main__":
    print("StencilIt : http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
