"""Premium PIL thumbnail generator (2026-11-22).

Why this module exists: the pipeline already had thumbnail engines
(thumb_variants / make_thumb_ai / thumb_studio), but the attach step's
outcome was invisible - factory.set_thumbnail is fail-soft with stdout-only
feedback and the produce report recorded nothing, so videos could (and did)
ship with YouTube's auto-grabbed frame while nobody could prove otherwise
from the repo. This generator is the deterministic, dependency-light
primary: PIL + ffmpeg only, no LLM, no image-model quota, no network.

Design, measured from a real @airevolutionx thumbnail (GPT 6.2 Astra,
_VXBCcECXJ4, read 2026-11-22): near-black canvas, a short subject line in
white ("GPT 6.2 ASTRA"), a thin gold rule under it, then a 3-5 word hook in
very large bold caps - white with ONE emotional word in glowing red.
Ours: the produced video's own frame as the background (darkened, with a
left-weighted black gradient so text always wins), the model/subject line
on top, the hook below it, and the channel bug (red bar + NEXTAI VISION)
in the top-left corner, matching the house branding.

Writes BOTH workdir/thumb.jpg (what factory.set_thumbnail reads) and
workdir/thumbnail.jpg (what the QC gate and the variants engine use).
Returns the thumb.jpg path, or None. Never raises.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

W, H = 1280, 720
ACCENT = (255, 32, 32)          # the one accent colour: signal red
GOLD = (255, 194, 26)           # subject rule, as in the reference
WHITE = (255, 255, 255)
BRAND = "NEXTAI VISION"

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "its", "it", "is", "are", "was", "were", "be", "been", "just", "now",
    "how", "what", "when", "who", "this", "that", "these", "those", "from",
    "by", "at", "as", "into", "over", "after", "before", "will", "can",
    "could", "should", "would", "than", "then", "so", "such", "not", "no",
    "every", "all", "about", "against", "between", "through", "during",
}
_STRONG = {
    "shock", "shocking", "shockingly", "secret", "secrets", "banned", "ban",
    "exposed", "exposes", "leaked", "leaks", "unlocked", "unlocks", "beats",
    "beat", "wins", "won", "fails", "failed", "failure", "dead", "dies",
    "killed", "crash", "crashed", "huge", "massive", "insane", "crazy",
    "warning", "alert", "finally", "free", "first", "never", "nobody",
    "everyone", "mad", "angry", "furious", "worst", "best", "destroyed",
    "destroys", "stunned", "panic", "dangerous", "unstoppable", "explodes",
}
_BRANDS = {
    "openai", "chatgpt", "claude", "anthropic", "gemini", "google", "grok",
    "xai", "deepseek", "qwen", "tesla", "nvidia", "meta", "microsoft",
    "apple", "samsung", "llama", "mistral",
}
_MODELWORDS = _BRANDS | {
    "gpt", "opus", "sonnet", "haiku", "optimus", "sora", "dall-e",
}


def _tokens(title):
    """Title -> ordered content tokens (stopwords dropped, case kept)."""
    raw = re.split(r"\s+", str(title or "").replace("|", " ").strip())
    out = []
    for tok in raw:
        t = tok.strip("\"'“”‘’()[]{}<>.,;:!?")
        if not t:
            continue
        if t.lower() in _STOP:
            continue
        if len(t) == 1 and not t.isdigit():
            continue
        out.append(t)
    return out


def hook_from_title(title):
    """Derive (subject_line, hook_lines, highlight_word) from a title.

    subject: the model/subject a viewer searches for ("CLAUDE OPUS 4.5",
    "GPT-6.2") or None. hook: 3-4 content words split into 2-3 lines.
    highlight: the emotional/digit word rendered in the accent colour.
    """
    toks = _tokens(title)
    if not toks:
        return None, ["UNTITLED"], None
    used = set()

    subject = None
    dig = next((i for i, t in enumerate(toks) if any(c.isdigit() for c in t)),
               None)
    if dig is not None:
        parts = [toks[dig]]
        used.add(dig)
        j = dig - 1
        while j >= 0 and len(parts) < 3 and \
                toks[j].lower().strip("-") in _MODELWORDS:
            parts.insert(0, toks[j])
            used.add(j)
            j -= 1
        subject = " ".join(p.upper() for p in parts)
    else:
        b = next((i for i, t in enumerate(toks)
                  if t.lower() in _BRANDS), None)
        if b is not None:
            subject = toks[b].upper()
            used.add(b)

    pool = [t for i, t in enumerate(toks) if i not in used]
    if subject:
        # do not repeat a leading brand token inside the hook
        pool = [t for t in pool if t.lower() not in _BRANDS]
    if not pool:
        pool = [t for i, t in enumerate(toks) if i not in used] or toks[:]
    hook = pool[:4]
    def _charged(t):
        return t.lower().strip("-") in _STRONG or \
            any(c.isdigit() for c in t)
    if hook and not any(_charged(t) for t in hook):
        swap = next((t for t in pool[4:6] if _charged(t)), None)
        if swap:
            hook[-1] = swap
    hook = [t.upper() for t in hook]
    hi = next((t for t in hook if _charged(t)), hook[-1] if hook else None)

    # split into 2 or 3 lines, whichever keeps the widest line shortest
    def _layouts(words):
        n = len(words)
        if n <= 2:
            yield [" ".join(words)] if n == 1 else [words[0], words[1]]
            return
        for k in range(1, n):
            yield [" ".join(words[:k]), " ".join(words[k:])]
        if n >= 3:
            for a in range(1, n - 1):
                for b in range(a + 1, n):
                    yield [" ".join(words[:a]), " ".join(words[a:b]),
                           " ".join(words[b:])]
    best = min(_layouts(hook),
               key=lambda ls: (max(len(x) for x in ls), len(ls)))
    return subject, best, hi


# --------------------------------------------------------------------------
# background

def _frame_score(img):
    """Higher = sharper and better lit (for picking a video frame)."""
    from PIL import ImageFilter, ImageStat
    g = img.convert("L")
    edges = g.filter(ImageFilter.FIND_EDGES)
    mean, std = ImageStat.Stat(edges).mean[0], ImageStat.Stat(g).stddev[0]
    bright = ImageStat.Stat(g).mean[0]
    if bright < 18:            # near-black frame: useless as a backdrop
        return -1.0
    return std + mean * 0.6


def _video_frame(video, workdir):
    """Best-scoring frame of the video as an RGB image, or None."""
    from PIL import Image
    try:
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video], capture_output=True, text=True,
            timeout=30).stdout.strip() or 0)
    except Exception:
        dur = 0
    fracs = [0.30, 0.5, 0.7, 0.15] if dur > 20 else [0.4, 0.1]
    best, best_sc = None, -2.0
    for i, fr in enumerate(fracs):
        t = max(1.0, dur * fr) if dur else 2.0 + 3 * i
        tmp = os.path.join(workdir, f"_prem_f{i}.jpg")
        try:
            subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{t:.1f}", "-i", video,
                 "-frames:v", "1", "-q:v", "3", tmp],
                capture_output=True, timeout=60)
            if not os.path.exists(tmp):
                continue
            im = Image.open(tmp).convert("RGB")
            sc = _frame_score(im)
            if sc > best_sc:
                best, best_sc = im.copy(), sc
            im.close()
        except Exception:
            continue
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass
    return best


def _procedural_bg():
    """Self-contained fallback: dark tech gradient with a soft glow + grid."""
    from PIL import Image, ImageDraw, ImageFilter
    small = Image.new("RGB", (320, 180))
    spx = small.load()
    for y in range(180):
        for x in range(320):
            v = int(26 * (x / 320) + 10 * (1 - y / 180))
            spx[x, y] = (6 + v // 3, 9 + v // 2, 16 + v)
    im = small.resize((W, H), Image.BICUBIC)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([760, -180, 1420, 420], fill=(24, 60, 92))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    from PIL import ImageChops
    im = ImageChops.add(im, glow)
    d = ImageDraw.Draw(im, "RGBA")
    for gx in range(0, W, 64):
        d.line([(gx, 0), (gx, H)], fill=(120, 180, 255, 14))
    for gy in range(0, H, 64):
        d.line([(0, gy), (W, gy)], fill=(120, 180, 255, 14))
    return im


def _cover(img):
    """Resize + centre-crop to exactly W x H."""
    from PIL import Image
    iw, ih = img.size
    sc = max(W / iw, H / ih)
    im = img.resize((round(iw * sc), round(ih * sc)), Image.LANCZOS)
    x = (im.width - W) // 2
    y = (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def _darken(img):
    """Boost a touch, darken, then lay a left-weighted black gradient so
    the text side is always close to the reference's black canvas."""
    from PIL import Image, ImageDraw, ImageEnhance
    im = ImageEnhance.Color(img).enhance(1.12)
    im = ImageEnhance.Contrast(im).enhance(1.07)
    im = ImageEnhance.Brightness(im).enhance(0.52)
    grad = Image.new("L", (W, 1))
    grad.putdata([int(228 - 108 * (x / W)) for x in range(W)])
    black = Image.new("RGB", (W, H), (0, 0, 0))
    im = Image.composite(black, im, grad.resize((W, H)))
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle([0, H - 190, W, H], fill=(0, 0, 0, 66))
    return im


# --------------------------------------------------------------------------
# text

def _font(size):
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("Anton-Regular.ttf", "ArchivoBlack-Regular.ttf"):
        p = os.path.join(here, "fonts", name)
        if os.path.exists(p):
            try:
                from PIL import ImageFont
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    from PIL import ImageFont
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _fit(draw, lines, max_w, start, floor):
    size = start
    while size > floor:
        f = _font(size)
        if all(draw.textlength(t, font=f) <= max_w for t in lines):
            return f, size
        size -= 6
    return _font(floor), floor


def build(e, workdir, video_path=None, clip_path=None):
    """Generate the premium thumbnail for entry `e` into `workdir`.

    Returns the thumb.jpg path or None. Fail-soft: never raises.
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter
        title = (e or {}).get("title", "")
        subject, lines, hi = hook_from_title(title)

        bg = None
        for src in (video_path, clip_path):
            if src and os.path.exists(src):
                if os.path.splitext(src)[1].lower() in (
                        ".jpg", ".jpeg", ".png", ".webp"):
                    try:
                        bg = Image.open(src).convert("RGB")
                    except Exception:
                        bg = None
                else:
                    bg = _video_frame(src, workdir)
                if bg is not None:
                    break
        if bg is None:
            bg = _procedural_bg()
        im = _darken(_cover(bg))
        draw = ImageDraw.Draw(im)

        mx = 62                      # left margin
        max_w = W - mx - 40

        # brand bug (top-left): red bar + wordmark, as on existing thumbs
        bf = _font(40)
        draw.rectangle([mx, 40, mx + 10, 40 + 46], fill=ACCENT)
        draw.text((mx + 24, 42), BRAND, font=bf, fill=WHITE)

        # subject line + gold rule (the reference's top text block)
        y = 148
        if subject:
            sf, _ = _fit(draw, [subject], max_w, 96, 54)
            draw.text((mx + 2, y), subject, font=sf, fill=WHITE)
            y += int(sf.size * 1.18)
            glow = Image.new("RGB", (W, H), (0, 0, 0))
            gd = ImageDraw.Draw(glow)
            gd.line([(mx + 2, y), (min(W - 40, mx + 560), y)],
                    fill=(120, 84, 0), width=9)
            glow = glow.filter(ImageFilter.GaussianBlur(7))
            from PIL import ImageChops
            im = ImageChops.add(im, glow)
            draw = ImageDraw.Draw(im)
            draw.line([(mx + 2, y), (min(W - 40, mx + 560), y)],
                      fill=GOLD, width=4)
            y += 34

        # hook: fit by width AND by the height left under the subject
        avail_h = H - y - 44
        hf, hs = _fit(draw, lines, max_w, 196, 76)
        while len(lines) * hs * 1.07 > avail_h and hs > 76:
            hs -= 6
            hf = _font(hs)
        stroke = max(4, hs // 15)

        # soft shadow pass
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        yy = y
        for ln in lines:
            sd.text((mx + 7, yy + 9), ln, font=hf, fill=(0, 0, 0, 200),
                    stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
            yy += int(hs * 1.07)
        im = Image.alpha_composite(
            im.convert("RGBA"),
            shadow.filter(ImageFilter.GaussianBlur(5))).convert("RGB")
        draw = ImageDraw.Draw(im)

        yy = y
        for ln in lines:
            x = mx
            for w_i, word in enumerate(ln.split(" ")):
                wtxt = word + (" " if w_i < len(ln.split(" ")) - 1 else "")
                fill = ACCENT if word == hi else WHITE
                draw.text((x, yy), wtxt, font=hf, fill=fill,
                          stroke_width=stroke, stroke_fill=(0, 0, 0))
                x += draw.textlength(wtxt, font=hf)
            yy += int(hs * 1.07)

        out1 = os.path.join(workdir, "thumb.jpg")
        out2 = os.path.join(workdir, "thumbnail.jpg")
        q = 90
        im.save(out1, quality=q)
        while os.path.getsize(out1) > 1_900_000 and q > 60:
            q -= 10
            im.save(out1, quality=q)
        im.save(out2, quality=q)
        print(f"thumb-premium: OK subject={subject!r} hook={lines!r} "
              f"hi={hi!r} ({os.path.getsize(out1) // 1024} KB)", flush=True)
        return out1
    except Exception as ex:
        print("thumb-premium: failed:", str(ex)[:140], flush=True)
        return None


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--video")
    ap.add_argument("--clip")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    print(build({"title": a.title}, a.out,
                video_path=a.video, clip_path=a.clip))
    sys.exit(0)
