#!/usr/bin/env python3
"""Intelligent footage engine (owner spec Task 3).

Adds the pieces the old one-shot pick_footage() did not have:

  * a disk cache keyed by the search query, so a query already resolved is never
    downloaded twice (across beats AND across videos)
  * parallel, retried downloads (ThreadPoolExecutor, bounded workers)
  * visual-similarity rejection: dHash of the first frame; a clip that looks like
    an already-chosen clip is skipped even if it comes from another asset id
  * a licensing/source record for every clip that ends up in a video
  * a fallback hook so the caller can ask for a generated still instead of
    shipping unrelated footage to fill a timeline

Design rule from the owner spec: unique footage for meaningful scenes, never
unrelated footage just to fill time. If nothing relevant is available the caller
gets None for that beat so it can reuse a wide shot deliberately or fail loudly.
"""
import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

FACT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(FACT, "footage", "_cache")
QUERY_INDEX = os.path.join(CACHE_DIR, "queries.json")
MAX_WORKERS = 4
DHASH_MAX_DIST = 6


def _ensure():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _load_index():
    try:
        with open(QUERY_INDEX) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_index(idx):
    _ensure()
    tmp = QUERY_INDEX + ".tmp"
    with open(tmp, "w") as f:
        json.dump(idx, f, indent=1)
    os.replace(tmp, QUERY_INDEX)


def qhash(query):
    return hashlib.sha1(query.strip().lower().encode()).hexdigest()[:16]


def cache_lookup(query):
    return _load_index().get(qhash(query))


def cache_store(query, record):
    idx = _load_index()
    idx[qhash(query)] = record
    _save_index(idx)


def dhash_file(path, size=8):
    from PIL import Image
    im = Image.open(path).convert("L").resize((size + 1, size))
    px = list(im.getdata())
    bits = []
    for row in range(size):
        for col in range(size):
            i = row * (size + 1) + col
            bits.append(1 if px[i] > px[i + 1] else 0)
    return "".join(str(b) for b in bits)


def _first_frame(clip_path, workdir):
    fp = os.path.join(workdir, "_fx_" + hashlib.sha1(clip_path.encode()).hexdigest()[:10] + ".jpg")
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.6",
                        "-i", clip_path, "-frames:v", "1", fp],
                       capture_output=True, timeout=90)
        return fp if os.path.exists(fp) else None
    except Exception:
        return None


def clip_signature(clip_path, workdir):
    """(dHash, mean R, mean G, mean B) of the first frame.

    A structure hash alone collides on similar compositions (synthetic patterns,
    two shots of the same room), so the colour of the frame is checked as well.
    """
    fp = _first_frame(clip_path, workdir)
    if not fp:
        return None
    try:
        import colorsys
        from PIL import Image
        h = dhash_file(fp)
        im = Image.open(fp).convert("RGB").resize((32, 18))
        bins = [0.0] * 12
        n = 0
        for r, g, b in im.getdata():
            hh, _l, sat = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
            if sat > 0.12:                      # ignore near-grey pixels
                bins[min(11, int(hh * 12))] += 1.0
                n += 1
        if n:
            bins = [v / n for v in bins]
        return (h, tuple(bins))
    finally:
        try:
            os.remove(fp)
        except Exception:
            pass


def clip_dhash(clip_path, workdir):
    sig = clip_signature(clip_path, workdir)
    return sig[0] if sig else None


def is_similar(s1, s2, max_dist=DHASH_MAX_DIST, max_hue_l1=0.30):
    """Near-duplicate only when BOTH structure and colour distribution agree.

    Structure = dHash hamming distance; colour = L1 distance between 12-bin hue
    histograms (hue, not mean RGB, so a warm shot and a cool shot never collide).
    """
    if not s1 or not s2:
        return False
    ham = sum(a != b for a, b in zip(s1[0], s2[0]))
    hue_l1 = sum(abs(a - b) for a, b in zip(s1[1], s2[1]))
    return ham <= max_dist and hue_l1 <= max_hue_l1


def download(url, dest, retries=2, timeout=180):
    """Bounded retry download with size validation."""
    for attempt in range(retries + 1):
        try:
            subprocess.run(["curl", "-sSL", "--max-time", str(timeout), "-o", dest, url],
                           check=True, capture_output=True, timeout=timeout + 30)
            if os.path.exists(dest) and os.path.getsize(dest) > 20000:
                return True
        except Exception:
            pass
        if attempt < retries:
            import time as _t
            _t.sleep(1.5 * (attempt + 1))
    return False


def fetch_parallel(jobs, workers=MAX_WORKERS):
    """jobs = [{'url':..., 'dest':...}] -> {url: ok_bool}. Never raises."""
    out = {}
    if not jobs:
        return out
    with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as ex:
        futs = {ex.submit(download, j["url"], j["dest"]): j["url"] for j in jobs}
        for f in as_completed(futs):
            url = futs[f]
            try:
                out[url] = bool(f.result())
            except Exception:
                out[url] = False
    return out


def dedupe_pairs(pairs, workdir, max_dist=DHASH_MAX_DIST):
    """Return (kept, replaced) where replaced lists near-duplicate positions.

    A near-duplicate clip is dropped from the sequence; the caller decides what
    to show instead (wide shot or generated still) - this function never
    silently fills the timeline with unrelated footage.
    """
    kept, replaced, seen = [], [], []
    for entry in pairs or []:
        clip = entry[0] if isinstance(entry, tuple) else entry
        path = clip.get("file") if isinstance(clip, dict) else None
        full = os.path.join(FACT, "footage", path) if path else None
        h = clip_signature(full, workdir) if full and os.path.exists(full) else None
        dup = next((i for i, s in enumerate(seen) if is_similar(h, s, max_dist)), None)
        if dup is not None:
            replaced.append({"index": len(kept) + len(replaced), "duplicate_of": dup,
                             "file": path})
            continue
        seen.append(h)
        kept.append(entry)
    return kept, replaced


def license_record(clip, query):
    """Structured provenance for the video's credit/report."""
    return {"file": clip.get("file"), "query": query,
            "source": clip.get("source") or clip.get("provider") or "unknown",
            "license": clip.get("license") or "see source page",
            "url": clip.get("page") or clip.get("url"),
            "id": clip.get("id")}
