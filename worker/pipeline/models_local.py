"""Lazy-loaded local CPU models: CLIP (photo similarity) + an AI-image detector.
Both load on first use and stay resident. Zero API cost.
"""
from __future__ import annotations

import io
import os
import threading

import structlog

log = structlog.get_logger()
_lock = threading.Lock()
_clip = None
_detector = None

# chosen by the ml/detector_bakeoff/ run (ADR-0002): acc 0.92, separation 0.82
DETECTOR_MODEL = os.getenv("RG_AI_DETECTOR", "haywoodsloan/ai-image-detector-deploy")


def _load_clip():
    global _clip
    if _clip is None:
        with _lock:
            if _clip is None:
                import open_clip
                import torch

                model, _, preprocess = open_clip.create_model_and_transforms(
                    "ViT-B-32", pretrained="laion2b_s34b_b79k"
                )
                model.eval()
                _clip = {"model": model, "preprocess": preprocess, "torch": torch}
                log.info("models_local.clip_loaded")
    return _clip


def clip_similarity(image_a: bytes, image_b: bytes) -> float:
    """Cosine similarity of two images in CLIP image-embedding space, 0..1."""
    from PIL import Image

    c = _load_clip()
    torch = c["torch"]
    with torch.no_grad():
        embs = []
        for raw in (image_a, image_b):
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            t = c["preprocess"](img).unsqueeze(0)
            e = c["model"].encode_image(t)
            e = e / e.norm(dim=-1, keepdim=True)
            embs.append(e)
        sim = float((embs[0] @ embs[1].T).item())
    return max(0.0, min(1.0, (sim + 1) / 2))  # map [-1,1] -> [0,1]


def _load_detector():
    global _detector
    if _detector is None:
        with _lock:
            if _detector is None:
                from transformers import pipeline

                _detector = pipeline("image-classification", model=DETECTOR_MODEL)
                log.info("models_local.detector_loaded", model=DETECTOR_MODEL)
    return _detector


def ai_generated_score(image: bytes) -> dict:
    """P(image is AI-generated), 0..1, from the configured detector."""
    from PIL import Image

    det = _load_detector()
    img = Image.open(io.BytesIO(image)).convert("RGB")
    preds = det(img)
    # detectors label the AI class variously: 'artificial', 'ai', 'fake', 'sdxl', ...
    ai_labels = {"artificial", "ai", "fake", "sdxl", "generated", "ai-generated"}
    score = 0.0
    for p in preds:
        lbl = p["label"].strip().lower()
        if any(k in lbl for k in ai_labels):
            score = max(score, float(p["score"]))
    return {"ai_generated_score": round(score, 4), "model": DETECTOR_MODEL, "raw": preds}
