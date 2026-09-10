"""One-off: pull a real, on-topic product photo per SKU into seed/images/.

Source: Wikimedia Commons (public-domain / CC media, no API key). For each SKU we
search the File: namespace, score the hits by how well the file title matches the
product noun (and against a people/scene block-list), download the best one's
1000px thumbnail, and centre-crop it to a square JPEG.

Run from the repo root; results are committed so `make seed` is offline:

    python seed/fetch_images.py                 # fetch missing only
    python seed/fetch_images.py --force         # refetch all
    python seed/fetch_images.py RG-009 RG-012   # refetch just these

`seed/seed.py` prefers seed/images/<SKU>.jpg over products.json's `image_url`.
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

OUT = Path(__file__).parent / "images"
API = "https://commons.wikimedia.org/w/api.php"
UA = "returnguard-seed/1.0 (local portfolio project; contact: local dev)"
SIZE = 900

# SKU -> search phrases, best first. The first phrase's words are the ones scored
# against each candidate file title.
QUERIES = {
    "RG-001": ["computer lcd display screen", "widescreen monitor", "flatscreen monitor"],
    "RG-002": ["headphones", "over ear headphones", "hifi headphones"],
    "RG-003": ["mechanical keyboard", "computer keyboard"],
    "RG-004": ["computer mouse", "optical mouse", "wireless mouse"],
    "RG-005": ["usb hub 4 port", "usb-c multiport adapter", "usb splitter hub"],
    "RG-006": ["desk lamp", "table lamp", "reading lamp"],
    "RG-007": ["portable speaker", "bluetooth speaker", "loudspeaker"],
    "RG-008": ["usb charger", "power adapter charger", "wall charger"],
    "RG-009": ["ceramic mug", "coffee mug", "stoneware mug"],
    "RG-010": ["stovetop kettle", "whistling kettle", "tea kettle stainless"],
    "RG-011": ["cast iron skillet", "cast iron pan", "frying pan"],
    "RG-012": ["santoku kitchen knife", "chef knife blade", "kitchen knife steel"],
    "RG-013": ["duvet", "bed linen", "bedding set"],
    "RG-014": ["kitchen chopping board", "wooden chopping board vegetables", "cutting board kitchen"],
    "RG-015": ["plastic food storage container", "food container with lid", "lunch box container"],
    "RG-016": ["candle in glass jar", "scented candle glass", "votive candle jar"],
    "RG-017": ["wool sweater", "knitted sweater", "pullover jumper"],
    "RG-018": ["hardshell jacket", "waterproof hiking jacket", "anorak jacket"],
    "RG-019": ["plain white t-shirt", "blank t-shirt cotton", "white cotton shirt"],
    "RG-020": ["chino trousers", "chinos trousers", "cotton trousers"],
    "RG-021": ["beanie hat", "knit cap", "wool hat"],
    "RG-022": ["leather belt", "belt clothing", "belt buckle leather"],
    "RG-023": ["sneakers shoes", "canvas shoes", "trainers footwear"],
    "RG-024": ["backpack", "hiking backpack", "rucksack"],
    "RG-025": ["reusable sports water bottle", "insulated drink bottle", "metal water bottle"],
    "RG-026": ["gym exercise mat", "foam fitness mat", "yoga"],
    "RG-027": ["dumbbell", "adjustable dumbbell", "hand weight dumbbell"],
    "RG-028": ["bicycle front light led", "bike headlight lamp", "bicycle safety light"],
    "RG-029": ["wool blanket", "picnic blanket", "camping blanket"],
}

# A few products have no clean studio shot on Commons — pull those from
# loremflickr instead (real CC Flickr photo matched to keyword tags, fixed lock).
LF_OVERRIDE = {
    "RG-026": "https://loremflickr.com/900/900/exercise,mat/all?lock=12",
}

BLOCK = ("nude", "naked", "woman", "women", "man ", "men ", "girl", "boy",
         "child", "people", "person", "portrait", "model ", "dog", "cat",
         "church", "cathedral", "building", "mall", "statue", "monument",
         "street", "protest", "war", "gun", "map", "diagram", "logo", "icon",
         "sign ", "poster", "stamp", "coin", "flag", "aerial", "wikimania",
         "water ", "ocean", "sea ", "pond", "lake", "river", "flood", "rain",
         "poncho", "museum", "excavat", "broken", "plank", "floor", "ruin",
         "damage", "trash", "waste", "abandoned", "graffiti", "porcelain",
         "kiln", "antique", "vendor", "balancing", "load ", "on head", "ming")


def _get(url: str, timeout: int = 40) -> bytes:
    """GET with polite 429 back-off (Commons rate-limits anonymous bursts)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                wait = int(e.headers.get("Retry-After", 0)) or 8 * (attempt + 1)
                print(f"    429 — waiting {wait}s")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("unreachable")


def _search(phrase: str) -> list[dict]:
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search",
        "gsrnamespace": "6", "gsrsearch": f"{phrase} filetype:bitmap",
        "gsrlimit": "15", "prop": "imageinfo", "iiprop": "url|size|mime",
        "iiurlwidth": "1000", "maxlag": "5",
    })
    d = json.loads(_get(f"{API}?{q}"))
    return list((d.get("query", {}).get("pages") or {}).values())


def _score(page: dict, words: list[str]) -> float:
    title = page.get("title", "").lower()
    ii = (page.get("imageinfo") or [{}])[0]
    if ii.get("mime") not in ("image/jpeg", "image/png"):
        return -99
    if any(b in title for b in BLOCK):
        return -50
    hit = sum(1 for w in words if w in title)
    s = 4 * hit + (2 if hit == len(words) else 0)
    w, h = ii.get("width") or 0, ii.get("height") or 0
    if w >= 700 and h >= 500:
        s += 1
    if w and h and 0.6 <= w / h <= 1.9:
        s += 1
    return s


def fetch_one(sku: str) -> str:
    if sku in LF_OVERRIDE:
        try:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(_get(LF_OVERRIDE[sku]))))
            img = ImageOps.fit(img.convert("RGB"), (SIZE, SIZE), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=87)
            (OUT / f"{sku}.jpg").write_bytes(buf.getvalue())
            return "ok  [loremflickr]"
        except Exception as e:  # noqa: BLE001
            print(f"  {sku}: loremflickr override failed ({e})")
    phrases = QUERIES[sku]
    words = phrases[0].replace("-", " ").split()
    cands: list[tuple[float, dict]] = []
    for ph in phrases:
        try:
            for pg in _search(ph):
                cands.append((_score(pg, words), pg))
        except Exception as e:  # noqa: BLE001
            print(f"  {sku}: search '{ph}' failed ({e})")
        time.sleep(2.5)
        if any(sc >= 8 for sc, _ in cands):
            break
    for sc, pg in sorted(cands, key=lambda x: -x[0]):
        if sc < 2:
            break
        ii = (pg.get("imageinfo") or [{}])[0]
        src = ii.get("thumburl") or ii.get("url")
        if not src:
            continue
        try:
            raw = _get(src)
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
            if img.mode != "RGB":
                img = img.convert("RGB")
            img = ImageOps.fit(img, (SIZE, SIZE), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=87)
        except Exception as e:  # noqa: BLE001
            print(f"  {sku}: {src[:70]} -> {e}")
            continue
        if buf.tell() < 4000:
            continue
        (OUT / f"{sku}.jpg").write_bytes(buf.getvalue())
        return f"ok  [{pg['title'][5:52]}]"
    return "FAILED"


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv
    OUT.mkdir(exist_ok=True)
    targets = args or list(QUERIES)
    failed = []
    for sku in targets:
        if sku not in QUERIES:
            print(f"{sku}  unknown SKU"); continue
        if (OUT / f"{sku}.jpg").exists() and not force and not args:
            print(f"{sku}  kept"); continue
        status = fetch_one(sku)
        print(f"{sku}  {status}", flush=True)
        if status == "FAILED":
            failed.append(sku)
        time.sleep(0.4)
    print(f"\n{len(targets) - len(failed)}/{len(targets)} done"
          + (f"; missing: {failed}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
