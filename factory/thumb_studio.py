#!/usr/bin/env python3
"""Thumbnail studio: the "product announcement slide" language.

Owner spec 2026-11-01 (annotated reference row, all four): the thumbnails that
work look like a professional launch SLIDE, not a text overlay:

    Google            <- real brand wordmark, small, top-left
    INTRODUCING       <- letterspaced kicker, thin, white
    GENIE 4           <- product name, MASSIVE, one accent colour
    SYNTHETIC REALITY <- descriptor, medium white

plus a cinematic stage / LED-screen background, and a person or device as the
subject. The bottom-three "alert bar" designs are explicitly rejected.

So this module renders three announcement compositions (bell / hero / stack),
each with real typography (Anton for display, Archivo Black for the wordmark),
no black caption plate, dark graded footage, screen glow, and an optional
free-licensed portrait. Everything here is deterministic and free.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")

W, H = 1280, 720
WHITE = (255, 255, 255)
CYAN = (0, 236, 255)
RED = (255, 43, 43)
GOLD = (255, 196, 0)

BRANDS = {
    "google": "Google", "gemini": "Google", "deepmind": "Google DeepMind",
    "openai": "OpenAI", "chatgpt": "OpenAI", "gpt": "OpenAI",
    "anthropic": "Anthropic", "claude": "Anthropic",
    "nvidia": "NVIDIA", "jensen": "NVIDIA",
    "microsoft": "Microsoft", "copilot": "Microsoft",
    "meta": "Meta", "llama": "Meta",
    "xai": "xAI", "grok": "xAI", "tesla": "Tesla", "spacex": "SpaceX",
    "moonshot": "Moonshot AI", "kimi": "Moonshot AI",
    "perplexity": "Perplexity", "mistral": "Mistral", "deepseek": "DeepSeek",
    "amazon": "Amazon", "apple": "Apple", "sora": "OpenAI",
}

# product-name shape cues: keep the name, drop filler
KICKERS = ("introducing", "breaking", "leaked", "revealed", "official")


def font(name, size):
    from PIL import ImageFont
    p = os.path.join(FONTS, name)
    if os.path.exists(p):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)


def display(size):
    return font("Anton-Regular.ttf", size)


def wordmark(size):
    return font("ArchivoBlack-Regular.ttf", size)


def brand_for(text):
    t = (text or "").lower()
    for k, v in BRANDS.items():
        if re.search(rf"\b{re.escape(k)}\b", t):
            return v
    return None


def parse_story(title, subject=""):
    """Title -> slide elements. Never invents a fake product name."""
    raw = (title or subject or "").strip()
    m = re.match(r"^\s*([A-Za-z0-9 .&'-]{2,24}?)\s+(?:just\s+)?(?:broke|beats|built|"
                 r"launched|released|unveiled|introduces|shipped|revealed|warns|"
                 r"killed|changed|made)\b(.*)$", raw, re.I)
    brand = brand_for(raw)
    rest = raw
    if m:
        rest = (m.group(2) or "").strip(" .:-")
    words = [w for w in re.split(r"\s+", rest) if w]
    # product name: shortest leading run with a digit, else first two words
    cut = 2
    for i in range(1, min(3, len(words)) + 1):
        if re.search(r"\d", " ".join(words[:i])):
            cut = i
            break
    product = " ".join(words[:cut]).upper().strip(" .,:") or raw.upper()[:22]
    desc = " ".join(words[cut:cut + 4]).upper().strip(" .,:-") or (subject or raw).upper()[:26]
    if desc == product:
        desc = (subject or "AI").upper()[:26]
    return {"brand": brand or (m.group(1).strip() if m else None),
            "kicker": "INTRODUCING",
            "product": product, "descriptor": desc}



# ── reference conformance (targets measured from the real channel) ──────────
REF = {"luma": 54.8, "sat": 0.460, "std": 69.5, "white": 5.1, "dark": 67.2}


def _profile(im):
    from PIL import ImageStat
    import numpy as _np
    a = _np.asarray(im.convert("RGB").resize((320, 180))).astype("float32")
    L = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
    mx, mn = a.max(2), a.min(2)
    sat = _np.where(mx > 0, (mx - mn) / _np.maximum(mx, 1), 0)
    return {"luma": float(L.mean()), "sat": float(sat.mean()),
            "std": float(L.std()),
            "white": float(((L > 225) & (sat < 0.18)).mean() * 100),
            "dark": float((L < 45).mean() * 100)}


def _tint_darks(im, amount=0.30, shadow=(6, 30, 60), high=(255, 116, 44), protect=198):
    """Grade that never touches the bright type (text must stay crisp white)."""
    from PIL import Image
    g = im.convert("L")
    tone = Image.composite(Image.new("RGB", im.size, high),
                           Image.new("RGB", im.size, shadow), g)
    blended = Image.blend(im, tone, amount)
    mask = g.point(lambda v: 255 if v < protect else 0)
    return Image.composite(blended, im, mask)


def _scale_darks(im, k):
    lut = [int(v * k) if v < 205 else v for v in range(256)]
    return im.point(lut * 3)


def _crush(im, knee=112, gamma=1.5, target=0.55):
    lut = [int((v / knee) ** gamma * knee * target) if v < knee else v
           for v in range(256)]
    return im.point(lut * 3)


def conform(im, rounds=3):
    """Luma / saturation / near-black matched to the reference profile."""
    from PIL import ImageEnhance
    for _ in range(rounds):
        p = _profile(im)
        if p["luma"] > REF["luma"] + 8:
            im = _scale_darks(im, max(0.50, (REF["luma"] + 3) / max(20.0, p["luma"])))
        if p["dark"] < REF["dark"] - 12:
            im = _crush(im)
        if p["sat"] < REF["sat"] - 0.10:
            im = _tint_darks(im, 0.28)
        elif p["sat"] > REF["sat"] + 0.18:
            im = ImageEnhance.Color(im).enhance(max(0.5, (REF["sat"] + 0.06) / p["sat"]))
    return im

# ── background ──────────────────────────────────────────────────────────────
def stage(base=None, glow=(0, 200, 255), horizon=0.62):
    """Dark stage: graded footage (or generated LED wall) + light beams + bloom."""
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageStat
    if base is not None:
        im = base.convert("RGB").resize((W, H), Image.LANCZOS)
        im = ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(1.35)).enhance(1.25)
        cur = max(12.0, ImageStat.Stat(im.convert("L")).mean[0])
        im = ImageEnhance.Brightness(im).enhance(max(0.32, min(1.1, 42.0 / cur)))
    else:
        im = Image.new("RGB", (W, H), (6, 8, 12))
        d = ImageDraw.Draw(im)
        for i in range(H):                                   # LED wall gradient
            k = i / H
            d.line([(0, i), (W, i)], fill=(int(6 + 26 * (1 - k)), int(10 + 46 * (1 - k)),
                                           int(18 + 70 * (1 - k))))
    # LED panel seams
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for x in range(0, W, 128):
        d.line([(x, 0), (x, H)], fill=(0, 0, 0, 46))
    for y in range(0, int(H * horizon), 96):
        d.line([(0, y), (W, y)], fill=(0, 0, 0, 38))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    # screen bloom
    bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    db = ImageDraw.Draw(bl)
    cy = int(H * 0.34)
    for r in range(700, 40, -30):
        a = int(46 * (1 - r / 700))
        db.ellipse([W * 0.52 - r, cy - r * 0.6, W * 0.52 + r, cy + r * 0.6],
                   fill=glow + (max(2, a),))
    bl = bl.filter(ImageFilter.GaussianBlur(80))
    im = Image.alpha_composite(im.convert("RGBA"), bl).convert("RGB")
    # light beams from the top
    bm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(bm)
    for i, x0 in enumerate(range(-200, W + 200, 260)):
        d.polygon([(x0, 0), (x0 + 120, 0), (x0 + 340, int(H * 0.95)),
                   (x0 + 150, int(H * 0.95))], fill=(180, 230, 255, 10))
    bm = bm.filter(ImageFilter.GaussianBlur(26))
    im = Image.alpha_composite(im.convert("RGBA"), bm).convert("RGB")
    # floor
    fl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(fl)
    d.rectangle([0, int(H * horizon), W, H], fill=(2, 3, 6, 150))
    im = Image.alpha_composite(im.convert("RGBA"), fl).convert("RGB")
    return im


# ── type ────────────────────────────────────────────────────────────────────
def fit_size(text, max_w, max_size, min_size=40, f=None):
    from PIL import Image, ImageDraw
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    size = max_size
    while size > min_size:
        ft = f(size) if f else display(size)
        if probe.textlength(text, font=ft) <= max_w:
            return ft
        size -= 4
    return (f(min_size) if f else display(min_size))


def tracked(d, xy, text, ft, fill, tracking=0.0, stroke=0, stroke_fill=None):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=ft, fill=fill, stroke_width=stroke,
               stroke_fill=stroke_fill or (0, 0, 0))
        x += d.textlength(ch, font=ft) + tracking
    return x


def headline(im, lines, x, y, max_w, accent_word=None, accent=CYAN,
             max_size=200, leading=0.94, align="left", stroke=6):
    """Display type with a soft shadow only (no plate), one accent word."""
    from PIL import Image, ImageDraw, ImageFilter
    rendered = []
    for text in lines:
        ft = fit_size(text, max_w, max_size)
        rendered.append((text, ft))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sh)
    yy = y
    for text, ft in rendered:
        w = ds.textlength(text, font=ft)
        xx = x if align == "left" else (x + (max_w - w) / 2)
        ds.text((xx + 4, yy + 6), text, font=ft, fill=(0, 0, 0, 210),
                stroke_width=stroke + 3, stroke_fill=(0, 0, 0, 210))
        yy += int(ft.size * leading)
    sh = sh.filter(ImageFilter.GaussianBlur(11))
    im = Image.alpha_composite(im.convert("RGBA"), sh).convert("RGB")
    d = ImageDraw.Draw(im)
    yy = y
    for text, ft in rendered:
        w = d.textlength(text, font=ft)
        xx = x if align == "left" else (x + (max_w - w) / 2)
        if accent_word and accent_word.upper() in text.upper():
            idx = text.upper().index(accent_word.upper())
            pre, mid, post = text[:idx], text[idx:idx + len(accent_word)], text[idx + len(accent_word):]
            cx = xx + d.textlength(pre, font=ft)
            for seg, col, sx in ((pre, WHITE, xx), (mid, accent, cx),
                                 (post, WHITE, cx + d.textlength(mid, font=ft))):
                if seg:
                    d.text((sx, yy), seg, font=ft, fill=col, stroke_width=stroke,
                           stroke_fill=(0, 0, 0))
        else:
            d.text((xx, yy), text, font=ft, fill=WHITE, stroke_width=stroke,
                   stroke_fill=(0, 0, 0))
        yy += int(ft.size * leading)
    return im, yy


def subject(im, path, anchor="right", width_frac=0.44, glow=(0, 200, 255),
            bright=1.08):
    """Cut-out person/device on a dark stage, rim-lit, with a soft drop shadow."""
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
    if not path or not os.path.exists(path):
        return im
    w = int(W * width_frac)
    h = int(H * 0.92)
    face = Image.open(path).convert("RGB")
    sc = max(w / face.width, h / face.height)
    fp = face.resize((round(face.width * sc), round(face.height * sc)), Image.LANCZOS)
    cx = (fp.width - w) // 2
    top = int(fp.height * 0.03)
    fp = fp.crop((cx, top, cx + w, top + h))
    fp = ImageEnhance.Contrast(fp).enhance(1.12)
    fp = ImageEnhance.Brightness(fp).enhance(bright)
    mask = Image.new("L", fp.size, 255).filter(ImageFilter.GaussianBlur(12))
    px = W - w + int(w * 0.10) if anchor == "right" else -int(w * 0.10)
    py = H - h - int(H * 0.02)
    # rim glow
    rim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rim.paste(Image.new("RGB", fp.size, glow), (px, py), mask)
    rim = rim.filter(ImageFilter.GaussianBlur(30))
    im = Image.alpha_composite(im.convert("RGBA"), rim).convert("RGB")
    im.paste(fp, (px, py), mask)
    return im


def brand_mark(im, brand, xy=(58, 44), size=54, accent=None):
    """Real-looking wordmark: heavy type + optional accent dot."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(im, "RGBA")
    if not brand:
        return im
    ft = wordmark(size)
    x, y = xy
    d.text((x, y), brand, font=ft, fill=WHITE, stroke_width=3, stroke_fill=(0, 0, 0))
    w = d.textlength(brand, font=ft)
    if accent:
        d.ellipse([x + w + 10, y + size * 0.52, x + w + 10 + size * 0.18,
                   y + size * 0.52 + size * 0.18], fill=accent)
    return im


def kicker(im, text, xy, color=WHITE, size=34, tracking=7):
    from PIL import ImageDraw
    d = ImageDraw.Draw(im, "RGBA")
    tracked(d, xy, text.upper(), font("ArchivoBlack-Regular.ttf", size), color,
            tracking=tracking, stroke=3, stroke_fill=(0, 0, 0))
    return im


def tag_bottom(im, text="NEXTAI VISION"):
    from PIL import ImageDraw
    d = ImageDraw.Draw(im, "RGBA")
    ft = font("ArchivoBlack-Regular.ttf", 22)
    d.text((60, H - 48), text, font=ft, fill=(226, 232, 240, 235),
           stroke_width=2, stroke_fill=(0, 0, 0))
    return im


# ── the three compositions ──────────────────────────────────────────────────
def render_bell(base, story, face=None, accent=CYAN):
    """Brand top-left, INTRODUCING, huge product name, descriptor, subject right."""
    im = stage(base, accent)
    im = subject(im, face, "right", 0.42, accent)
    im = brand_mark(im, story.get("brand"), (60, 46), 50, accent)
    im = kicker(im, story.get("kicker", "INTRODUCING"), (62, 150), WHITE, 30, 9)
    lines = [story["product"]]
    im, y = headline(im, lines, 60, 208, int(W * 0.62), None, accent, 190)
    im, y = headline(im, [story["descriptor"]], 62, y + 6, int(W * 0.58), None,
                     accent, 76, stroke=4)
    return tag_bottom(im)


def render_hero(base, story, face=None, accent=CYAN):
    """KIMI style: brand top, product name stacked bottom-left in the accent colour."""
    im = stage(base, accent, horizon=0.66)
    im = subject(im, face, "right", 0.46, accent)
    im = brand_mark(im, story.get("brand"), (58, 40), 46, accent)
    prod_words = story["product"].split()
    lines = [" ".join(prod_words[:-1]), prod_words[-1]] if len(prod_words) > 1 \
        else [story["product"]]
    im, y = headline(im, [l for l in lines if l], 56, int(H * 0.44), int(W * 0.66),
                     lines[-1] if len(lines) > 1 else str(None), accent, 168, stroke=7)
    im = kicker(im, story["descriptor"][:34], (60, int(H * 0.46) + 0 + 4), WHITE, 26, 6)
    return tag_bottom(im)


def render_stack(base, story, face=None, accent=RED):
    """AI-CRISIS style: brand rows, each with an accent word; big close at bottom."""
    im = stage(base, accent, horizon=0.6)
    im = subject(im, face, "right", 0.40, accent)
    im = brand_mark(im, story.get("brand"), (58, 40), 44, accent)
    rows = [story["product"], " ".join(story["descriptor"].split()[:2])]
    y = int(H * 0.20)
    for i, row in enumerate([r for r in rows if r]):
        im, y = headline(im, [row[:26]], 58, y, int(W * 0.60), None, WHITE, 92,
                         stroke=5)
        y += 8
    im, y = headline(im, [story["descriptor"].split()[-1][:14] or "AI"], 58,
                     int(H * 0.62), int(W * 0.58), None, accent, 150, stroke=7)
    return tag_bottom(im)


COMPOSITIONS = {"bell": render_bell, "hero": render_hero, "stack": render_stack}


def render_all(base, story, face=None, workdir=None, accents=None):
    """Render every composition; returns list of (name, path, profile)."""
    out = []
    for i, (name, fn) in enumerate(COMPOSITIONS.items()):
        acc = (accents or [CYAN, CYAN, RED])[i % 3]
        try:
            im = fn(base, story, face, acc)
            try:
                im = conform(im)
            except Exception as _ex:
                print("studio: conform skipped:", str(_ex)[:60], flush=True)
        except Exception as ex:
            print(f"studio: {name} failed: {str(ex)[:90]}", flush=True)
            continue
        p = os.path.join(workdir or ".", f"thumb_{name}.jpg")
        im.save(p, quality=91, subsampling=1)
        out.append((name, p, im))
    return out


# ── pipeline entry point ────────────────────────────────────────────────────
def build(e, workdir, clip=None, save_names=("thumb.jpg", "thumbnail.jpg")):
    """Default thumbnail for a video: three announcement compositions, scored,
    winner saved under the upload guard names. Returns the winner path."""
    from PIL import Image
    import glob

    src = None
    if clip:
        _c = os.path.join(clip.get("dir", ""), clip.get("file", ""))
        if os.path.exists(_c):
            cand = sorted(glob.glob(os.path.join(os.path.dirname(_c) or ".",
                                                 "_thumb_c*.jpg")))
            src = cand[0] if cand else _c
    base = None
    if src:
        try:
            base = stage(Image.open(src) if src.lower().endswith((".jpg", ".png")) else None)
        except Exception:
            base = None

    story = parse_story(e.get("title", ""), e.get("subject", ""))
    face = None
    try:
        import sys as _s
        if HERE not in _s.path:
            _s.path.insert(0, HERE)
        import faces as F
        key, face = F.face_for(f"{story.get('brand') or ''} {e.get('title','')}")
        if key:
            print(f"studio: portrait {key} (free licence)", flush=True)
    except Exception as _e:
        print("studio: no portrait:", str(_e)[:70], flush=True)

    outs = render_all(base, story, face, workdir)
    if not outs:
        return None
    # objective screen: contrast, legibility (white share), colour, sharpness
    from PIL import ImageStat, ImageFilter
    scored = []
    for name, path, im in outs:
        g = im.convert("L")
        contrast = ImageStat.Stat(g).stddev[0]
        sharp = ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).mean[0]
        prof = _profile(im)
        legible = min(prof["white"], 9.0) / 9.0
        score = (contrast * 1.0 + sharp * 1.6 + legible * 34
                 - abs(prof["luma"] - REF["luma"]) * 0.6)
        scored.append((round(score, 1), name, path))
        print(f"studio: {name} -> {round(score,1)} ({prof['luma']:.0f} luma, "
              f"{prof['sat']:.2f} sat)", flush=True)
    scored.sort(key=lambda x: -x[0])
    best = scored[0]
    im = Image.open(best[2]).convert("RGB").resize((W, H), Image.LANCZOS)
    out = os.path.join(workdir, save_names[0])
    im.save(out, quality=92, subsampling=1)
    for extra in save_names[1:]:
        im.save(os.path.join(workdir, extra), quality=92, subsampling=1)
    if os.path.getsize(out) > 1_900_000:
        im.save(out, quality=82, subsampling=2)
    try:
        import json as _j
        _j.dump({"composition": best[1], "score": best[0],
                 "scores": {n: sc for sc, n, _ in scored},
                 "note": "objective quality screen, not a CTR prediction"},
                open(os.path.join(workdir, "thumb_choice.json"), "w"))
    except Exception:
        pass
    print(f"studio: picked {best[1]} ({best[0]}) -> {out}", flush=True)
    return out
