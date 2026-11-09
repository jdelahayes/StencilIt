"""Semantic object selection (Segment Anything, MobileSAM in ONNX).

A click on the image selects the object under it. The image is analysed once (encoder, ~0.3 s on a
CPU, whatever the image size since it works on a 1024 px copy); each click then only runs the light
mask decoder (~40 ms).

The models (MobileSAM, Apache 2.0, ONNX export by Acly) are downloaded on first use into `models/`
and checked against their SHA-256. `onnxruntime` is an optional dependency: without it, the rest of
the application works and the selection tool reports what is missing.
"""
from __future__ import annotations

import hashlib
import threading
import urllib.request
from pathlib import Path

import cv2
import numpy as np

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
_BASE = "https://huggingface.co/Acly/MobileSAM/resolve/main/"
MODELS = {
    "encoder": ("mobile_sam_image_encoder.onnx", 28157093,
                "580f5fb648ea1062c0aabc26217aed56921985f03f0cbbd852bba81d760cc749"),
    "decoder": ("sam_mask_decoder_multi.onnx", 16496559,
                "8976b90a87ba50a6a72217a5ff994f7d25ce16f2229fcc1ed259e1294c622ffe"),
}
SIDE = 1024                     # long side of the image seen by the encoder

_lock = threading.Lock()
_sessions: dict = {}


class SemanticError(RuntimeError):
    pass


def missing_models() -> list[str]:
    return [f for f, size, _ in MODELS.values() if not (MODEL_DIR / f).is_file()
            or (MODEL_DIR / f).stat().st_size != size]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download() -> None:
    MODEL_DIR.mkdir(exist_ok=True)
    for name, size, sha in MODELS.values():
        dst = MODEL_DIR / name
        if dst.is_file() and dst.stat().st_size == size:
            continue
        tmp = dst.with_suffix(".part")
        try:
            with urllib.request.urlopen(_BASE + name, timeout=60) as r, open(tmp, "wb") as out:
                while chunk := r.read(1 << 20):
                    out.write(chunk)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise SemanticError(f"Téléchargement du modèle de sélection impossible ({e})") from e
        if _sha256(tmp) != sha:
            tmp.unlink(missing_ok=True)
            raise SemanticError("Modèle de sélection téléchargé corrompu (empreinte SHA-256 inattendue)")
        tmp.replace(dst)


def _load():
    """Encoder and decoder sessions (downloaded and loaded once, thread-safe)."""
    with _lock:
        if not _sessions:
            try:
                import onnxruntime as ort
            except ImportError as e:
                raise SemanticError("Module onnxruntime absent : relancez lancer.bat (qui installe les "
                                    "dépendances de requirements.txt)") from e
            _download()
            prov = ["CPUExecutionProvider"]
            _sessions["encoder"] = ort.InferenceSession(str(MODEL_DIR / MODELS["encoder"][0]), providers=prov)
            _sessions["decoder"] = ort.InferenceSession(str(MODEL_DIR / MODELS["decoder"][0]), providers=prov)
        return _sessions["encoder"], _sessions["decoder"]


def embed(img: np.ndarray) -> dict:
    """Analyses the image (BGR): embedding + scale to the encoder frame."""
    enc, _ = _load()
    h, w = img.shape[:2]
    s = SIDE / max(h, w)
    small = cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))),
                       interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    x = cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32)
    emb = enc.run(None, {"input_image": x})[0]
    return {"emb": emb, "shape": (h, w)}


def select(state: dict, points: list[tuple[float, float, int]], out_size: tuple[int, int],
           level: int = 0) -> np.ndarray:
    """Mask (bool, out_size = (w, h)) of the object designated by the points.

    points: (x, y, label) in fractions of the image (0..1), label 1 = object, 0 = not the object.
    level: 0 = the candidate the model trusts most, then the larger ones, then the smaller ones (a
    second click on the same spot switches between the cuts: part / object / whole).
    """
    _, dec = _load()
    h, w = state["shape"]
    s = SIDE / max(h, w)
    pts = [(x * w * s, y * h * s) for x, y, _ in points] + [(0.0, 0.0)]
    lab = [float(l) for _, _, l in points] + [-1.0]     # padding point (no box prompt)
    ow, oh = out_size
    masks, iou, _ = dec.run(None, {
        "image_embeddings": state["emb"],
        "point_coords": np.array([pts], np.float32),
        "point_labels": np.array([lab], np.float32),
        "mask_input": np.zeros((1, 1, 256, 256), np.float32),
        "has_mask_input": np.zeros(1, np.float32),
        "orig_im_size": np.array([oh, ow], np.float32),
    })
    cand = masks[0] > 0
    n = cand.shape[0]
    idx = list(range(1, n)) if n > 1 else [0]           # with several outputs, #0 is the single-mask token
    best = max(idx, key=lambda i: iou[0, i])
    areas = {i: int(cand[i].sum()) for i in idx}
    order = sorted((i for i in idx if areas[i] >= areas[best]), key=lambda i: areas[i])
    order += sorted((i for i in idx if areas[i] < areas[best]), key=lambda i: areas[i])
    return cand[order[level % len(order)]]
