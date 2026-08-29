"""One-time AI-image-detector bake-off (ADR-0002).

Builds a small labeled sample:
  real/  — real product photos already in MinIO (seeded)
  ai/    — a handful of AI-generated "product damage" photos from the OpenAI
           image API (a real paid call — the only sanctioned way to get genuine
           AI images locally; see non-negotiable #5)

Runs 2-3 candidate detectors over the sample and prints accuracy / the AI-class
probability gap. The best performer is wired into the pipeline
(pipeline/models_local.py, `RG_AI_DETECTOR`) and the numbers recorded in
docs/decisions/ADR-0002.

Run: docker compose run --rm worker python -m ml.detector_bakeoff.run
"""
from __future__ import annotations

import base64
import io
import json
import pathlib

import httpx
from PIL import Image

HERE = pathlib.Path(__file__).parent
SAMPLE = HERE / "sample"
CANDIDATES = [
    "Organika/sdxl-detector",
    "umm-maybe/AI-image-detector",
    "haywoodsloan/ai-image-detector-deploy",
]
AI_LABELS = {"artificial", "ai", "fake", "sdxl", "generated", "ai-generated"}


def _openai_images(n: int) -> list[bytes]:
    from pipeline.settings import get_settings

    s = get_settings()
    prompts = [
        "a close-up photo of a cracked ceramic coffee mug on a wooden table",
        "a photo of a scratched laptop screen, product return evidence",
        "a torn cardboard shipping box with a damaged product inside",
        "a photo of a stained fabric backpack, worn and dirty",
        "a bent metal water bottle photographed on a kitchen counter",
        "a photo of a shattered phone screen on a desk",
    ][:n]
    out = []
    with httpx.Client(timeout=120) as c:
        for p in prompts:
            r = c.post(
                f"{s.bifrost_url}/v1/images/generations",
                json={"model": "openai/gpt-image-1", "prompt": p, "size": "1024x1024", "n": 1},
                headers={"Authorization": "Bearer bifrost"},
            )
            r.raise_for_status()
            d = r.json()["data"][0]
            raw = base64.b64decode(d["b64_json"]) if "b64_json" in d else \
                httpx.get(d["url"], timeout=60).content
            out.append(raw)
    return out


def build_sample(n_each: int = 6) -> None:
    (SAMPLE / "ai").mkdir(parents=True, exist_ok=True)
    (SAMPLE / "real").mkdir(parents=True, exist_ok=True)
    if not list((SAMPLE / "ai").glob("*.jpg")):
        for i, raw in enumerate(_openai_images(n_each)):
            Image.open(io.BytesIO(raw)).convert("RGB").save(SAMPLE / "ai" / f"ai_{i}.jpg", quality=90)
    if not list((SAMPLE / "real").glob("*.jpg")):
        from pipeline import db, storage_worker  # noqa: F401
        import asyncio

        async def _pull():
            await db.start()
            keys = await db.fetchall("SELECT image_key FROM products LIMIT %(n)s", {"n": n_each})
            from pipeline.storage_worker import _get  # noqa: SLF001
            for i, k in enumerate(keys):
                b = _get(k["image_key"])
                if b:
                    Image.open(io.BytesIO(b)).convert("RGB").save(
                        SAMPLE / "real" / f"real_{i}.jpg", quality=90)
            await db.stop()

        asyncio.run(_pull())


def score_dir(det, d: pathlib.Path) -> list[float]:
    scores = []
    for f in sorted(d.glob("*.jpg")):
        preds = det(Image.open(f).convert("RGB"))
        s = max((float(p["score"]) for p in preds
                 if any(k in p["label"].lower() for k in AI_LABELS)), default=0.0)
        scores.append(s)
    return scores


def main() -> None:
    build_sample()
    from transformers import pipeline as hf_pipeline

    results = {}
    for model in CANDIDATES:
        try:
            det = hf_pipeline("image-classification", model=model)
        except Exception as e:  # noqa: BLE001
            results[model] = {"error": str(e)}
            continue
        ai = score_dir(det, SAMPLE / "ai")
        real = score_dir(det, SAMPLE / "real")
        thr = 0.5
        tp = sum(s >= thr for s in ai)
        tn = sum(s < thr for s in real)
        acc = (tp + tn) / (len(ai) + len(real)) if (ai or real) else 0.0
        results[model] = {
            "n_ai": len(ai), "n_real": len(real),
            "mean_ai_score": round(sum(ai) / len(ai), 3) if ai else None,
            "mean_real_score": round(sum(real) / len(real), 3) if real else None,
            "accuracy@0.5": round(acc, 3),
            "separation": round((sum(ai) / len(ai) - sum(real) / len(real)), 3)
            if ai and real else None,
        }

    best = max((m for m in results if "error" not in results[m]),
               key=lambda m: results[m]["accuracy@0.5"], default=None)
    out = {"results": results, "chosen": best}
    (HERE / "bakeoff_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
