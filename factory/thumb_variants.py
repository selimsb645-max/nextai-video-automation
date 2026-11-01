#!/usr/bin/env python3
"""Three genuinely different thumbnail concepts + objective scoring.

Owner spec 2026-11-01 (Task 1). Google removed free image generation, so every
concept is drawn with PIL from the video's own footage frame - original artwork,
zero cost, no third-party API.

Concepts (structurally different layouts, not text swaps):
  A "cinematic"  - letterboxed, teal/orange grade, lower-left text block, heavy vignette
  B "news"       - red breaking band on top, subject right of centre, left text column
  C "curiosity"  - neon radial glow, centre subject ring, huge question-style hook

Scoring is objective image measurement (contrast, sharpness, colourfulness,
text legibility, focal saliency) plus a metadata relevance proxy (does the
footage keyword overlap the title). It is a quality screen, NOT a CTR promise:
a higher score never guarantees a higher click-through rate.
"""
import json
import math
import os
import subprocess

TW, TH = 1280, 720

try:
    import numpy as np
except Exception:                                    # pragma: no cover
    np = None


# ───────────────────────── frame extraction ─────────────────────────
def _grab_frames(clip_path, workdir, n=6):
    """Sample n frames across the clip; return the most striking one."""
    out = []
    dur = 2.0
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", clip_path],
                           capture_output=True, text=True, timeout=60)
        dur = float((r.stdout or "2").strip() or 2.0)
    except Exception:
        pass
    for i in range(n):
        t = dur * (0.1 + 0.8 * i / max(1, n - 1))
        fp = os.path.join(workdir, f"_tv_frame{i}.jpg")
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
                            "-i", clip_path, "-frames:v", "1", fp],
                           capture_output=True, timeout=90)
            if os.path.exists(fp) and os.path.getsize(fp) > 5000:
                out.append(fp)
        except Exception:
            continue
    return out


def _cover(im):
    sc = max(TW / im.width, TH / im.height)
    im = im.resize((round(im.width * sc), round(im.height * sc)))
    x = (im.width - TW) // 2
    y = (im.height - TH) // 2
    return im.crop((x, y, x + TW, y + TH))


def _font(size):
    from PIL import ImageFont
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    raise SystemExit("THUMB_FONT_MISSING")


def _hook_lines(text, max_words=4, max_lines=2):
    words = [w for w in "".join(c if c.isalnum() or c.isspace() else " "
                                for c in text).split() if w]
    lines, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words:
            lines.append(" ".join(cur))
            cur = []
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(" ".join(cur))
    return [l.upper() for l in lines][:max_lines] or ["AI NEWS"]


# ───────────────────────── the three concepts ─────────────────────────
def concept_a_cinematic(base, hook):
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    im = _cover(base.copy())
    im = ImageEnhance.Color(im).enhance(1.25)
    im = ImageEnhance.Contrast(im).enhance(1.20)
    # teal/orange split tone
    ov = Image.new("RGB", (TW, TH), (8, 26, 38))
    im = Image.blend(im, ov, 0.22)
    warm = Image.new("RGB", (TW, TH), (58, 28, 8))
    mask = Image.linear_gradient("L").resize((TW, TH))
    im = Image.composite(Image.blend(im, warm, 0.28), im, mask)
    d = ImageDraw.Draw(im, "RGBA")
    # cinematic letterbox
    d.rectangle([0, 0, TW, 58], fill=(0, 0, 0, 235))
    d.rectangle([0, TH - 58, TW, TH], fill=(0, 0, 0, 235))
    # lower-left text block
    f = _font(96)
    y = TH - 96 - 78
    for line in reversed(hook):
        d.text((58, y), line, font=f, fill=(255, 255, 255), stroke_width=3,
               stroke_fill=(0, 0, 0))
        y -= 104
    d.rectangle([52, TH - 70, 240, TH - 62], fill=(255, 176, 32, 255))
    return im


def concept_b_news(base, hook, tag="AI NEWS"):
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    src = _cover(base.copy())
    # subject pushed right of centre for a left text column
    sub = src.crop((TW // 5, 0, TW, TH)).resize((TW, TH))
    im = ImageEnhance.Contrast(ImageEnhance.Color(sub).enhance(1.1)).enhance(1.1)
    d = ImageDraw.Draw(im, "RGBA")
    # dark left column so text always reads
    for x in range(int(TW * 0.56)):
        a = int(232 * (1 - x / (TW * 0.56)) ** 0.55)
        d.rectangle([x, 0, x + 1, TH], fill=(6, 10, 16, a))
    # red breaking band
    d.rectangle([0, 0, TW, 96], fill=(196, 28, 32, 245))
    tf = _font(46)
    d.text((40, 24), tag.upper()[:22], font=tf, fill=(255, 255, 255))
    f = _font(104)
    y = 150
    for line in hook:
        d.text((40, y), line, font=f, fill=(255, 255, 255), stroke_width=4,
               stroke_fill=(0, 0, 0))
        y += 112
    d.rectangle([40, y + 10, 200, y + 20], fill=(255, 255, 255, 230))
    return im


def concept_c_curiosity(base, hook):
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    im = ImageEnhance.Color(_cover(base.copy())).enhance(1.35)
    im = ImageEnhance.Contrast(im).enhance(1.28)
    im = im.filter(ImageFilter.GaussianBlur(1.2))
    # neon radial glow behind the subject
    glow = Image.new("RGB", (TW, TH), (4, 8, 18))
    dg = ImageDraw.Draw(glow, "RGBA")
    cx, cy = int(TW * 0.62), int(TH * 0.46)
    for r in range(430, 40, -26):
        dg.ellipse([cx - r, cy - r * 0.62, cx + r, cy + r * 0.62],
                   fill=(30, 90, 200, max(6, 46 - r // 14)))
    im = Image.blend(im, glow, 0.46)
    d = ImageDraw.Draw(im, "RGBA")
    f = _font(112)
    y = 54
    for i, line in enumerate(hook):
        t = line + ("?" if i == len(hook) - 1 else "")
        d.text((50, y), t, font=f, fill=(120, 220, 255), stroke_width=4,
               stroke_fill=(2, 6, 14))
        y += 122
    # heavy dark edge so the centre pops
    for k in range(24):
        a = int(16 * (1 - k / 24))
        d.rectangle([k, k, TW - k, TH - k], outline=(0, 0, 0, a))
    return im


# ───────────────────────── objective scoring ─────────────────────────
def _luma(arr):
    return 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]


def _score(img, hook, footage_tags, title):
    """Return (total 0-100, components) using measurable image properties."""
    from PIL import Image
    small = img.resize((320, 180))
    a = np.asarray(small).astype("float32") if np is not None else None
    comp = {}
    if a is None:                                   # numpy missing -> neutral
        return 50.0, {"note": "numpy unavailable"}

    L = _luma(a)
    # contrast: spread of luminance (0-100 mapped 0..25 -> 0..100)
    contrast = min(1.0, float(L.std()) / 66.0)
    # sharpness: mean |Laplacian|
    lap = np.abs(4 * L[1:-1, 1:-1] - L[:-2, 1:-1] - L[2:, 1:-1]
                 - L[1:-1, :-2] - L[1:-1, 2:])
    sharp = min(1.0, float(lap.mean()) / 24.0)
    # colourfulness (Hasler-Suesstrunk)
    rg = a[:, :, 0] - a[:, :, 1]
    yb = 0.5 * (a[:, :, 0] + a[:, :, 1]) - a[:, :, 2]
    colorful = min(1.0, (math.sqrt(float(rg.std()) ** 2 + float(yb.std()) ** 2)
                         + 0.3 * math.sqrt(float(rg.mean()) ** 2 + float(yb.mean()) ** 2)) / 90.0)
    # text legibility: the brightest 6% of pixels must stand far above the mean
    hi = np.percentile(L, 94)
    legib = min(1.0, float(hi - L.mean()) / 120.0)
    # focal saliency: edge energy in the central third (where text/subject live)
    h, w = lap.shape
    centre = lap[h // 3:2 * h // 3, w // 3:2 * w // 3]
    sal = min(1.0, float(centre.mean()) / max(1e-6, float(lap.mean())) / 1.6)
    # relevance proxy from metadata (footage tags vs title words)
    tw = {w for w in title.lower().replace("-", " ").split() if len(w) > 3}
    ft = " ".join(footage_tags or []).lower()
    rel = 1.0 if not tw else min(1.0, len([w for w in tw if w in ft]) / max(1, len(tw)))
    # empty-frame guard: a nearly black thumb is worthless no matter what
    dark_pen = 0.55 if float(L.mean()) < 28 else 1.0

    comp = {"contrast": round(contrast * 100, 1), "sharpness": round(sharp * 100, 1),
            "colorfulness": round(colorful * 100, 1), "legibility": round(legib * 100, 1),
            "saliency": round(sal * 100, 1), "relevance": round(rel * 100, 1),
            "mean_luma": round(float(L.mean()), 1), "dark_penalty": dark_pen}
    total = (contrast * 22 + sharp * 18 + colorful * 10 + legib * 24
             + sal * 14 + rel * 12) * dark_pen
    return round(total, 1), comp


def _save_under_2mb(im, *paths, limit=1_950_000):
    """JPEG-encode to every path, stepping quality down until it fits 2 MB."""
    from PIL import Image
    for path in paths:
        q = 92
        while q >= 60:
            im.save(path, quality=q, optimize=True)
            try:
                if os.path.getsize(path) <= limit:
                    break
            except OSError:
                break
            q -= 8
    return paths[0]


def horde_backgrounds(prompts, workdir, budget_s=240):
    """Free crowdsourced diffusion (AI Horde, anonymous key) -> local jpg paths.

    Zero budget: AI Horde is a volunteer GPU network with a free anonymous tier
    (key "0000000000"). Queues can be minutes long, so this is time-boxed and the
    caller falls back to a footage frame when nothing lands in time.
    """
    import urllib.request as u
    import json as _json
    out, ids = [], []
    for i, p in enumerate(prompts):
        body = _json.dumps({
            "prompt": p, "params": {"width": 1280, "height": 720,
                                    "steps": 20, "sampler_name": "k_euler",
                                    "cfg_scale": 7, "n": 1},
            "nsfw": False, "censor_nsfw": True, "r2": True,
            "models": ["AlbedoBase XL (SDXL)"],
        }).encode()
        try:
            rq = u.Request("https://aihorde.net/api/v2/generate/async", data=body,
                           headers={"apikey": "0000000000",
                                    "Content-Type": "application/json",
                                    "Client-Agent": "nextai-vision:1.0"})
            jd = _json.loads(u.urlopen(rq, timeout=30).read())
            if jd.get("id"):
                ids.append((i, jd["id"]))
        except Exception:
            continue
    import time as _t
    end = _t.time() + budget_s
    while ids and _t.time() < end:
        _t.sleep(12)
        for i, jid in list(ids):
            try:
                st = _json.loads(u.urlopen(
                    f"https://aihorde.net/api/v2/generate/status/{jid}", timeout=30).read())
            except Exception:
                continue
            gens = st.get("generations") or []
            if gens and gens[0].get("img"):
                try:
                    fp = os.path.join(workdir, f"_horde_bg{i}.jpg")
                    with open(fp, "wb") as fh:
                        fh.write(u.urlopen(gens[0]["img"], timeout=90).read())
                    out.append(fp)
                except Exception:
                    pass
                ids.remove((i, jid))
            elif st.get("faulted"):
                ids.remove((i, jid))
    return out

def generate_three(e, workdir, clip_path, footage_tags=None, hooks=None):
    """Build A/B/C, score them, pick the winner. Returns dict (never raises)."""
    from PIL import Image
    res = {"variants": [], "selected": None, "scores": {}, "note": ""}
    frames = _grab_frames(clip_path, workdir)
    if not frames:
        res["note"] = "no frame extractable from footage"
        return res
    best, best_s = frames[0], -1.0
    for fp in frames:
        im = Image.open(fp).convert("RGB").resize((160, 90))
        a = np.asarray(im).astype("float32") if np is not None else None
        s = float(_luma(a).std()) if a is not None else 0.0
        if s > best_s:
            best, best_s = fp, s
    base = Image.open(best).convert("RGB")

    title = str(e.get("title", ""))
    hook = _hook_lines(e.get("headline") or title)
    hooks = [h for h in (hooks or []) if h][:3]
    tag = str(e.get("subject") or "AI NEWS").upper()

    # each concept gets its OWN copy when the LLM supplied three angles
    copy = hooks if len(hooks) == 3 else [hook, hook, hook]
    builds = [("A_cinematic", lambda: concept_a_cinematic(base, _hook_lines(copy[0]))),
              ("B_news", lambda: concept_b_news(base, _hook_lines(copy[1]), tag)),
              ("C_curiosity", lambda: concept_c_curiosity(base, _hook_lines(copy[2])))]
    for name, fn in builds:
        try:
            img = fn()
            path = os.path.join(workdir, f"thumb_{name}.jpg")
            img.save(path, quality=92)
            total, comp = _score(img, hook, footage_tags, title)
            res["variants"].append({"concept": name, "path": path,
                                    "score": total, "components": comp})
            res["scores"][name] = total
        except Exception as ex:
            res["variants"].append({"concept": name, "error": str(ex)[:160]})
    ranked = [v for v in res["variants"] if v.get("path")]
    if not ranked:
        res["note"] = "all concepts failed"
        return res
    ranked.sort(key=lambda v: v["score"], reverse=True)
    res["selected"] = ranked[0]["path"]
    final = os.path.join(workdir, "thumbnail.jpg")
    # The rest of the pipeline (factory.set_thumbnail, the upload guard, the
    # render guard) all look for workdir/thumb.jpg - that mismatch is why the
    # thumbnail was generated but never applied to the upload (owner 2026-11-01).
    compat = os.path.join(workdir, "thumb.jpg")
    try:
        im = Image.open(ranked[0]["path"]).convert("RGB")
        _save_under_2mb(im, final, compat)
        res["final"] = final
        res["thumb_jpg"] = compat
    except Exception as ex:
        res["note"] = f"copy failed: {ex}"
    res["note"] = ("scores are an objective quality screen, not a CTR prediction")
    try:
        with open(os.path.join(workdir, "thumbs_report.json"), "w") as f:
            json.dump(res, f, indent=1)
    except Exception:
        pass
    return res
