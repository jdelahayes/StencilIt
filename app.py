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
from stencilit.svg_export import export_zip

ROOT = Path(__file__).parent
MATERIALS_FILE = ROOT / "stencilit" / "materials.json"

app = Flask(__name__, static_folder=str(ROOT / "static"))
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024

# Sessions en mémoire (application locale mono-utilisateur)
SESSIONS: dict[str, dict] = {}
LOCK = threading.Lock()

PREP_KEYS = ("support_w_mm", "support_h_mm", "px_per_mm", "detail", "n_layers", "color_mode", "skip_support")


def materials() -> dict:
    return json.loads(MATERIALS_FILE.read_text(encoding="utf-8"))


# ---------------- Réglages enregistrés par l'utilisateur ----------------
USER_PRESETS_FILE = ROOT / "presets_utilisateur.json"
PRESET_KINDS = ("support", "material")


def load_user_presets() -> dict:
    try:
        data = json.loads(USER_PRESETS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    return {k: dict(data.get(k, {})) for k in PRESET_KINDS}


def save_user_presets(data: dict) -> None:
    tmp = USER_PRESETS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(USER_PRESETS_FILE)  # écriture atomique


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


PREVIEW_MAX = 1100  # plus grand côté des images de prévisualisation (px)


def rgba_b64(color_bgr, alpha: np.ndarray) -> str:
    """PNG RGBA : couleur unie de la couche, transparence = masque (0..1)."""
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
    """Crée une session ; le fichier d'origine est gardé tel quel pour l'export du projet."""
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
    src = sess["img"][y0:y1, x0:x1]
    gray = pl.is_grayscale(src) if mode == "auto" else mode == "gray"
    key = (gray, skip, x0, y0, x1, y1)
    cache = sess.setdefault("reco", {})
    if key not in cache:
        cache[key] = pl.recommend_layers(src, gray, skip)
    return jsonify(cache[key])


@app.post("/api/mask")
def api_mask():
    """Reçoit le masque peint (PNG transparent, à la taille de l'aperçu de l'image source).
    Les pixels peints (opaques) délimitent les zones où chercher les détails clés."""
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


@app.post("/api/process")
def api_process():
    data = request.get_json(force=True)
    sess = SESSIONS.get(data.get("id", ""))
    if not sess:
        return jsonify(error="Session inconnue, rechargez l'image"), 404
    p = pl.Params.from_dict(data.get("params", {}))
    lay, warnings = pl.resolve_layout(p, sess["img"].shape)
    t0 = time.perf_counter()
    key = tuple(getattr(p, k) for k in PREP_KEYS) + (lay.src_rect, tuple(round(v, 3) for v in lay.vis_mm))
    if sess.get("prep_key") != key:
        sess["prep"] = pl.prepare(sess["img"], p, lay)
        sess["prep_key"] = key
    # Masque des détails clés (peint dans l'onglet « Masque contours »), ramené à la zone image calculée
    region = None
    if p.outline and sess.get("mask") is not None:
        x0, y0, x1, y1 = lay.src_rect
        H, W = sess["prep"].labels.shape
        region = cv2.resize(sess["mask"][y0:y1, x0:x1], (W, H), interpolation=cv2.INTER_NEAREST) > 0
    res = pl.build(sess["prep"], p, region)
    sess["result"] = res
    sess["material"] = data.get("material")
    sess["ui"] = data.get("ui")          # état complet de l'interface, pour le fichier projet
    sheet = hex_to_bgr((data.get("material") or {}).get("sheet_color", "#c8d3dc"))
    # Calques de prévisualisation (zone support) : couleur de la couche + transparence = ouvertures.
    # Le navigateur les superpose lui-même -> masquer une couche ou activer le flou est instantané.
    # Tout est projeté directement à la taille d'aperçu (un grand support ne coûte pas plus cher).
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
            "image": png_b64(pl.layer_view(res, L, sheet), 900),
            "mask_flat": rgba_b64(L.color, to_preview(mask)),
            "mask_sim": rgba_b64(L.color, to_preview(cv2.GaussianBlur(mask, (0, 0), sig) * 0.97)),
            **pl.layer_stats(L),
        })
    _, reg_warn = pl.registration_shapes(res)
    # Original placé sur le support, pour comparer à l'échelle
    ref = np.empty((size[1], size[0], 3), np.uint8)
    ref[:] = res.support_color.astype(np.uint8)
    H, W = res.prepared.labels.shape
    ix, iy = res.prepared.off_px
    r = (round(ix * k), round(iy * k), max(round(ix * k) + 1, round((ix + W) * k)), max(round(iy * k) + 1, round((iy + H) * k)))
    r = (r[0], r[1], min(size[0], r[2]), min(size[1], r[3]))
    ref[r[1]:r[3], r[0]:r[2]] = cv2.resize(res.prepared.resized, (r[2] - r[0], r[3] - r[1]), interpolation=cv2.INTER_AREA)
    sheet_sim = pl.simulate_sheet(res)
    return jsonify(
        reference=png_b64(ref),
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
        seconds=round(time.perf_counter() - t0, 2),
    )


@app.get("/api/export/<sid>")
def api_export(sid):
    sess = SESSIONS.get(sid)
    if not sess or "result" not in sess:
        return jsonify(error="Rien à exporter"), 404
    mask_png = None
    if sess.get("mask") is not None:
        ok, buf = cv2.imencode(".png", sess["mask"])
        mask_png = buf.tobytes()
    data = export_zip(sess["result"], sess.get("material"), sess["name"],
                      original=(sess.get("raw"), sess.get("ext", ".png")), mask_png=mask_png,
                      ui=sess.get("ui"))
    return send_file(io.BytesIO(data), mimetype="application/zip", as_attachment=True,
                     download_name=f"{sess['name']}_pochoirs.zip")


@app.post("/api/project")
def api_project():
    """Ouvre un projet exporté (.zip) : image d'origine, masque et réglages complets."""
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
    return jsonify({**out, "info": info, "mask": mask_b64, "mask_coverage": coverage})


if __name__ == "__main__":
    print("StencilIt : http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
