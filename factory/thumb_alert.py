#!/usr/bin/env python3
"""@airevolutionx-style thumbnail engine (owner request 2026-11-01).

Reference look decoded from the owner's screenshot of youtube.com/@airevolutionx:
  - dark, high-contrast cinematic base (footage frame pushed to near-black)
  - huge blocky ALL-CAPS white text, 2 lines, heavy black stroke
  - ONE accent word in alert red (#FF2B2B) or cyber blue (#00F2FF)
  - a thin red alert bar / warning triangle for the "news alert" signal
  - small brand tag top-left, 16:9 (1280x720)

Three concepts are rendered and objectively scored; the winner wins on
contrast, text coverage, color energy and readable hook length. Everything is
PIL (free, no API). Real faces/logos are never fabricated.
"""
import os
import subprocess

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
]
RED = (255, 43, 43)
CYAN = (0, 242, 255)
WHITE = (255, 255, 255)
STOP = {"the", "a", "an", "of", "in", "on", "is", "are", "this", "that", "its",
        "it", "to", "for", "with", "and", "after", "now", "new", "has", "have",
        "was", "by", "at", "from", "will", "why", "how", "what", "just"}
ACCENT_HINTS = {"chaos", "war", "dead", "nightmare", "banned", "hacked", "beats",
                "warning", "crash", "collapse", "nothing", "lies", "panic",
                "finished", "powerful", "world", "first", "biggest", "never"}


def _font(size):
    from PIL import ImageFont
    for p in FONT_PATHS:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _pick_frame(clip_file, workdir):
    """Most striking frame of the beat-1 clip (bright + colourful + sharp)."""
    from PIL import Image, ImageStat, ImageFilter
    cand = []
    for i, frac in enumerate((0.15, 0.30, 0.45, 0.60, 0.75, 0.90)):
        fp = os.path.join(workdir, f"_ta{i}.jpg")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss",
                        f"{clip_file['dur'] * frac:.2f}", "-i",
                        os.path.join(clip_file["dir"], clip_file["file"]),
                        "-frames:v", "1", fp], check=False)
        if os.path.exists(fp):
            cand.append(fp)
    best, score = None, -1.0
    for fp in cand:
        im = Image.open(fp).convert("RGB").resize((200, 112))
        st = ImageStat.Stat(im)
        sharp = ImageStat.Stat(im.filter(ImageFilter.FIND_EDGES)).mean
        s = (sum(st.mean) / 3) * 0.45 + (sum(st.stddev) / 3) * 1.3 + sum(sharp) * 2.5
        if s > score:
            best, score = fp, s
    for fp in cand:
        if fp != best:
            try:
                os.remove(fp)
            except OSError:
                pass
    return best


def _cover(path):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    TW, TH = 1280, 720
    sc = max(TW / im.width, TH / im.height)
    im = im.resize((round(im.width * sc), round(im.height * sc)), Image.LANCZOS)
    x, y = (im.width - TW) // 2, (im.height - TH) // 2
    return im.crop((x, y, x + TW, y + TH))


def _cover_from(im):
    """Cover-crop an in-memory PIL image to 1280x720 (concept D entry)."""
    TW, TH = 1280, 720
    sc = max(TW / im.width, TH / im.height)
    im = im.resize((round(im.width * sc), round(im.height * sc)))
    x, y = (im.width - TW) // 2, (im.height - TH) // 2
    return im.crop((x, y, x + TW, y + TH))


def _darken(im, factor=0.46, contrast=1.30, color=1.55):
    from PIL import ImageEnhance
    im = ImageEnhance.Brightness(im).enhance(factor)
    im = ImageEnhance.Contrast(im).enhance(contrast)
    return ImageEnhance.Color(im).enhance(color)


def _vignette(im, strength=0.80):
    from PIL import Image, ImageDraw, ImageFilter
    TW, TH = im.size
    mask = Image.new("L", (TW, TH), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([-TW * 0.25, -TH * 0.35, TW * 1.25, TH * 1.35], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(120))
    dark = Image.new("RGB", (TW, TH), (0, 0, 0))
    return Image.composite(im, Image.blend(im, dark, strength), mask)


def _grad_left(im, alpha=225):
    """Dark gradient from the left so white text always reads."""
    from PIL import Image, ImageDraw
    TW, TH = im.size
    ov = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for x in range(int(TW * 0.72)):
        a = int(alpha * (1 - x / (TW * 0.72)) ** 1.15)
        d.line([(x, 0), (x, TH)], fill=(3, 4, 8, a))
    return Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")


def _split_hook(phrase, font, draw, maxw, lines=2):
    words = phrase.split()
    if not words:
        return [phrase]
    if lines == 2 and len(words) > 1:
        best = None
        for i in range(1, len(words)):
            l1, l2 = " ".join(words[:i]), " ".join(words[i:])
            w = max(draw.textlength(l1, font=font), draw.textlength(l2, font=font))
            if w <= maxw and (best is None or w > best[0]):
                best = (w, [l1, l2])
        if best:
            return best[1]
    return [" ".join(words)]


def _accent_index(words):
    for i, w in enumerate(words):
        if w.strip("'!?.,:").lower() in ACCENT_HINTS:
            return i
    best, idx = -1, len(words) - 1
    for i, w in enumerate(words):
        if len(w) > best:
            best, idx = len(w), i
    return idx


def _draw_hook(im, phrase, accent, concept):
    """concept: 1 = left/white+red accent, 2 = centered, 3 = bottom bar."""
    from PIL import ImageDraw
    TW, TH = im.size
    d = ImageDraw.Draw(im)
    maxw = int(TW * (0.66 if concept == 1 else 0.86))
    size, font, lines = None, None, None
    for s in range(190, 56, -6):
        f = _font(s)
        ls = _split_hook(phrase, f, d, maxw)
        if all(d.textlength(l, font=f) <= maxw for l in ls):
            size, font, lines = s, f, ls
            break
    if font is None:
        size, font, lines = 56, _font(56), [phrase]
    lh = int(size * 1.04)
    total = lh * len(lines)
    if concept == 3:
        y0 = TH - 96 - total
        x0 = 56
    elif concept == 2:
        y0 = (TH - total) // 2
        x0 = None
    else:
        y0 = int(TH * 0.30)
        x0 = 56
    stroke = max(6, size // 11)
    word_i = 0
    for li, line in enumerate(lines):
        if x0 is None:
            x = (TW - d.textlength(line, font=font)) / 2
        else:
            x = x0
        # word-by-word so one word can carry the accent colour
        for w in line.split(" "):
            col = accent if word_i == _accent_index(phrase.split()) else WHITE
            d.text((x, y0 + li * lh), w, font=font, fill=col,
                   stroke_width=stroke, stroke_fill=(0, 0, 0))
            x += d.textlength(w + " ", font=font)
            word_i += 1
    return lines, size


def _chrome(im, concept, tag="AI NEWS"):
    """Alert bar / warning triangle / brand tag: the 'news alert' signal."""
    from PIL import ImageDraw
    TW, TH = im.size
    d = ImageDraw.Draw(im, "RGBA")
    f_tag = _font(30)
    # brand tag
    d.rectangle([40, 34, 40 + 12, 74], fill=RED + (255,))
    d.text((66, 36), "NEXTAI VISION", font=f_tag, fill=WHITE,
           stroke_width=3, stroke_fill=(0, 0, 0))
    # alert pill top-right
    label = tag.upper()
    w = d.textlength(label, font=f_tag)
    d.rounded_rectangle([TW - 60 - w - 34, 30, TW - 40, 80], radius=10,
                        fill=RED + (235,))
    # warning triangle
    cx, cy, r = TW - 60 - w - 64, 55, 20
    d.polygon([(cx, cy - r), (cx - r, cy + r * 0.85), (cx + r, cy + r * 0.85)],
              fill=(255, 214, 0))
    d.text((cx - 6, cy - 12), "!", font=_font(26), fill=(0, 0, 0))
    d.text((TW - 60 - w - 14, 36), label, font=f_tag, fill=WHITE)
    # concept accents
    if concept == 1:
        d.rectangle([56, TH - 64, 56 + 190, TH - 52], fill=RED + (255,))
    elif concept == 2:
        d.rectangle([0, 0, TW, 8], fill=RED + (255,))
        d.rectangle([0, TH - 8, TW, TH], fill=RED + (255,))
    else:
        d.rectangle([0, TH - 14, TW, TH - 6], fill=CYAN + (220,))
    return im


def _score(im):
    """Objective screen (not a CTR prediction): contrast, coverage, energy."""
    from PIL import Image, ImageStat, ImageFilter
    g = im.convert("L")
    st = ImageStat.Stat(g)
    contrast = st.stddev[0]
    mean = st.mean[0]
    # share of near-white pixels ~ the text mass
    hist = g.histogram()
    total = sum(hist)
    white = sum(hist[200:]) / total
    sat = ImageStat.Stat(im.convert("HSV").getchannel("S")).mean[0]
    sharp = ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).mean[0]
    s = contrast * 1.1 + white * 340 + sat * 0.55 + sharp * 3.0
    if not (18 <= mean <= 165):
        s -= 25
    return round(s, 1)





def _duotone(im, amount=0.42, shadow=(8, 32, 62), high=(255, 118, 40)):
    """Grade grey/teal-less footage toward the reference saturation.

    ImageEnhance.Color cannot add colour to a grey frame, which is why a plain
    datacenter shot stayed at saturation 0.23 while the reference sits at 0.46.
    Mapping the luma ramp onto a cool-shadow / warm-highlight ramp fixes it.
    """
    from PIL import Image
    g = im.convert("L")
    sh = Image.new("RGB", im.size, shadow)
    hi = Image.new("RGB", im.size, high)
    tone = Image.composite(hi, sh, g)
    return Image.blend(im, tone, amount)


def _crush_shadows(im, knee=96, floor=8):
    """Pull the shadow end toward black: the reference sits at ~67% near-black
    pixels, our graded footage was landing near 54%."""
    lut = []
    for v in range(256):
        if v < knee:
            lut.append(int(floor + (v / knee) ** 1.55 * (knee - floor) * 0.42))
        else:
            lut.append(v)
    return im.point(lut * 3)


def _luma_of(im):
    """Mean luma (0-255)."""
    from PIL import ImageStat
    return ImageStat.Stat(im.convert("L")).mean[0]


def _apply_face(im, path, width_frac=0.72, bottom=False):
    """Big free-licensed portrait: right side by default, cropped shoulders-up,
    brightened with a hard red rim light (the reference cuts people out)."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    TW, TH = im.size
    face = Image.open(path).convert("RGB")
    w = int(TW * width_frac)
    h = int(TH * (1.06 if not bottom else 0.98))
    sc = max(w / face.width, h / face.height)
    fp = face.resize((round(face.width * sc), round(face.height * sc)), Image.LANCZOS)
    x = (fp.width - w) // 2
    y = int(fp.height * 0.04)
    fp = fp.crop((x, y, x + w, y + h))
    fp = ImageEnhance.Contrast(fp).enhance(1.18)
    fp = ImageEnhance.Brightness(fp).enhance(1.10)
    fp = ImageEnhance.Color(fp).enhance(1.15)
    # crisp-ish edge (small feather) so it reads as a cut-out, not a blurry blob
    mask = Image.new("L", fp.size, 255).filter(ImageFilter.GaussianBlur(26))
    px = TW - fp.width + int(fp.width * 0.10)
    py = TH - fp.height if bottom else -14
    im.paste(fp, (px, py), mask)
    rim = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    dr = ImageDraw.Draw(rim)
    dr.rectangle([px - 5, py, px + 5, py + fp.height], fill=(255, 43, 43, 130))
    rim = rim.filter(ImageFilter.GaussianBlur(14))
    return Image.alpha_composite(im.convert("RGBA"), rim).convert("RGB")


def _draw_hook_center(im, phrase, accent):
    """Huge 2-line block across the middle band (reference geometry), one
    accent-coloured word, heavy black outline."""
    from PIL import ImageDraw, Image, ImageFilter
    TW, TH = im.size
    words = phrase.split()
    best = None
    for size in range(210, 60, -4):
        f = _font(size)
        d0 = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        cand = None
        for i in range(1, len(words)):
            l1, l2 = " ".join(words[:i]), " ".join(words[i:])
            wmax = max(d0.textlength(l1, font=f), d0.textlength(l2, font=f))
            if wmax <= TW * 0.90:
                cand = (l1, l2, wmax)
                break
        if cand:
            best = (size, f, cand)
            break
    if best is None:
        size, f = 60, _font(60)
        lines = [phrase]
    else:
        size, f, (l1, l2, _) = best
        lines = [l1, l2]
    # soft dark plate behind the text so it reads on any footage
    plate = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    dp = ImageDraw.Draw(plate)
    lh = int(size * 1.06)
    total = lh * len(lines)
    y0 = int(TH * 0.50 - total / 2)
    dp.rectangle([0, max(0, y0 - 26), TW, min(TH, y0 + total + 26)],
                 fill=(4, 5, 9, 132))
    plate = plate.filter(ImageFilter.GaussianBlur(18))
    im = Image.alpha_composite(im.convert("RGBA"), plate).convert("RGB")
    d = ImageDraw.Draw(im)
    accent_i = _accent_index(phrase.split())
    stroke = max(8, size // 9)
    wi = 0
    for li, line in enumerate(lines):
        x = (TW - d.textlength(line, font=f)) / 2
        for wd in line.split(" "):
            col = accent if wi == accent_i else WHITE
            d.text((x, y0 + li * lh), wd, font=f, fill=col,
                   stroke_width=stroke, stroke_fill=(0, 0, 0))
            x += d.textlength(wd + " ", font=f)
            wi += 1
    d.rectangle([(TW - 220) / 2, y0 + total + 16, (TW + 220) / 2, y0 + total + 26],
                fill=accent)
    return im



# ═══════════════════════════════════════════════════════════════════════════
# HOUSE STYLE (measured from the reference channel itself, 2026-11-01)
# 8 real @airevolutionx thumbnails: luma 54.8, saturation 0.46, luma std 69.5,
# bright text pixels 5.1%, near-black 67.2%, and the text block sits CENTRED in
# the middle band in two huge lines. This function reproduces exactly that.
# ═══════════════════════════════════════════════════════════════════════════
def concept_poster(base, phrase, tag="AI NEWS", face_path=None, target_luma=54.8):
    from PIL import ImageEnhance, ImageStat
    im = _cover_from(base) if not isinstance(base, tuple) else _cover(base)
    im = ImageEnhance.Color(im).enhance(1.9)
    im = ImageEnhance.Contrast(im).enhance(1.45)
    # normalise brightness to the reference luma before the overlays go on
    cur = max(12.0, ImageStat.Stat(im.convert("L")).mean[0])
    im = ImageEnhance.Brightness(im).enhance(max(0.42, min(1.5, target_luma / cur)))
    im = _vignette(im, 0.80)
    im = _crush_shadows(im)
    try:
        _p = style_profile(im)
        if _p["sat"] < 0.38:                    # grey footage: add the reference grade
            im = _duotone(im, min(0.62, (0.44 - _p["sat"]) * 1.9))
            im = ImageEnhance.Color(im).enhance(1.25)
        elif _p["sat"] > 0.55:                  # neon test footage: pull it back
            im = ImageEnhance.Color(im).enhance(max(0.44, 0.46 / _p["sat"]))
    except Exception:
        pass
    if face_path:
        im = _apply_face(im, face_path, width_frac=0.50, bottom=True)
        # the portrait brings its own brightness: pull the frame back down
        cur = max(12.0, ImageStat.Stat(im.convert("L")).mean[0])
        if cur > target_luma:
            im = ImageEnhance.Brightness(im).enhance(max(0.60, target_luma / cur))
    im = _draw_hook_center(im, phrase, RED)
    im = _chrome(im, 2, tag)
    return im


def style_profile(im):
    """Measure an image the same way the reference channel was measured."""
    from PIL import ImageStat
    import numpy as _np
    small = im.convert("RGB").resize((320, 180))
    a = _np.asarray(small).astype("float32")
    L = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
    mx, mn = a.max(2), a.min(2)
    sat = _np.where(mx > 0, (mx - mn) / _np.maximum(mx, 1), 0)
    return {"luma": round(float(L.mean()), 1), "sat": round(float(sat.mean()), 3),
            "std": round(float(L.std()), 1),
            "white": round(float(((L > 225) & (sat < 0.18)).mean() * 100), 1),
            "red": round(float(((a[:, :, 0] > 150) & (a[:, :, 1] < 80) & (a[:, :, 2] < 80)).mean() * 100), 2),
            "dark": round(float((L < 45).mean() * 100), 1)}


# reference targets from 8 real @airevolutionx thumbnails (2026-11-01)
REF_TARGET = {"luma": 54.8, "sat": 0.460, "std": 69.5, "white": 5.1, "red": 1.23, "dark": 67.2}


def style_distance(prof, target=None):
    """0 = dead-on the reference look, higher = further away."""
    t = target or REF_TARGET
    return round(abs(prof["luma"] - t["luma"]) / 20.0
                 + abs(prof["sat"] - t["sat"]) / 0.25
                 + abs(prof["std"] - t["std"]) / 30.0
                 + abs(prof["white"] - t["white"]) / 6.0
                 + abs(prof["dark"] - t["dark"]) / 25.0, 2)


# ── owner 2026-11-01: a real person in every thumbnail, like the reference ──
def _face_panel(path, height):
    """Shoulders-up crop from a free-licensed portrait, softened edges."""
    from PIL import Image, ImageEnhance
    face = Image.open(path).convert("RGB")
    w = int(height * 0.72)
    sc = max(w / face.width, height / face.height)
    im = face.resize((round(face.width * sc), round(face.height * sc)), Image.LANCZOS)
    x = (im.width - w) // 2
    y = int(im.height * 0.05)
    im = im.crop((x, y, x + w, y + height))
    return ImageEnhance.Contrast(im).enhance(1.12)


def render_concepts(e, workdir, phrase, clip=None, face_path=None):
    """Render the three alert concepts. Returns [(concept, path, score)]."""
    out = []
    frame = None
    if clip:
        frame = _pick_frame(clip, workdir)
    for concept, tag in ((1, "AI NEWS"), (2, "BREAKING"), (3, "ALERT")):
        if frame:
            base = _cover(frame)
        else:
            base = _synthetic_base()
        im = _darken(base, 0.46 if concept != 2 else 0.55)
        im = _vignette(im, 0.8 if concept != 2 else 0.6)
        if concept in (1, 3):
            im = _grad_left(im, 230)
            if face_path:                      # person on the right, text left
                im = _apply_face(im, face_path)
        accent = RED if concept != 3 else CYAN
        _draw_hook(im, phrase, accent, concept)
        im = _chrome(im, concept, tag)
        p = os.path.join(workdir, f"thumb_alert_{concept}.jpg")
        im.convert("RGB").save(p, quality=90)
        _sc = _score(im)
        try:
            _sc -= 6.0 * style_distance(style_profile(im))
        except Exception:
            pass
        out.append((concept, p, round(_sc, 1)))
    if frame and os.path.exists(frame):
        try:
            os.remove(frame)
        except OSError:
            pass
    return out


def _synthetic_base():
    """Fallback backdrop when no footage frame is available: dark tech grid."""
    from PIL import Image, ImageDraw, ImageFilter
    TW, TH = 1280, 720
    im = Image.new("RGB", (TW, TH), (6, 8, 14))
    d = ImageDraw.Draw(im)
    for x in range(0, TW, 56):
        d.line([(x, 0), (x, TH)], fill=(18, 26, 40))
    for y in range(0, TH, 56):
        d.line([(0, y), (TW, y)], fill=(18, 26, 40))
    glow = Image.new("RGB", (TW, TH), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([TW * 0.42, -TH * 0.5, TW * 1.3, TH * 1.3], fill=(0, 90, 160))
    gd.ellipse([-TW * 0.2, TH * 0.4, TW * 0.5, TH * 1.5], fill=(150, 20, 30))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    return Image.blend(im, glow, 0.55)


def build(e, workdir, clip=None):
    """Entry point: pick hook phrase, render the concepts, keep the best."""
    import re
    from PIL import Image
    title = e.get("title", "")
    words = [w for w in re.findall(r"[A-Za-z0-9'%$]+", title) if w.lower() not in STOP]
    phrase = " ".join(words[:4]).upper() or title.upper()[:28]
    fkey, fpath = None, None
    try:
        import sys as _s
        _fd = os.path.dirname(os.path.abspath(__file__))
        if _fd not in _s.path:
            _s.path.insert(0, _fd)
        import faces as _faces
        fkey, fpath = _faces.face_for(f"{e.get('title','')} {e.get('subject','')}")
        if fkey:
            print(f"thumb-alert: portrait {fkey} (free licence)", flush=True)
    except Exception as _ex:
        print("thumb-alert: face lookup skipped:", str(_ex)[:80], flush=True)
    concepts = render_concepts(e, workdir, phrase, clip, fpath)
    # add the measured house-style poster to the same comparison
    try:
        from PIL import Image as _Im
        _src = None
        if clip:
            try:
                _src = _pick_frame(clip, workdir)
            except Exception:
                _src = None
            if not _src:
                _cand = os.path.join(clip.get("dir", ""), clip.get("file", ""))
                _src = _cand if os.path.exists(_cand) else None
        _base = _cover(_src) if _src else _synthetic_base()
        _post = concept_poster(_base, phrase, "AI NEWS", fpath)
        _p = os.path.join(workdir, "thumb_poster.jpg")
        _post.convert("RGB").save(_p, quality=90)
        _prof = style_profile(_post)
        _sc = _score(_post) - 6.0 * style_distance(_prof)
        concepts.append((0, _p, round(_sc, 1)))
        print("thumb-poster:", _prof, "dist", style_distance(_prof), flush=True)
    except Exception as _ex:
        print("thumb-poster failed, using alert fallbacks:", str(_ex)[:90], flush=True)
    try:
        import json as _j
        _j.dump({"key": fkey,
                 "credit": (_faces.credit(fkey) if fkey else "")},
                open(os.path.join(workdir, "thumb_face.json"), "w"))
    except Exception:
        pass
    concepts.sort(key=lambda c: -c[2])
    best = concepts[0][1]
    _post = next((c for c in concepts if c[0] == 0), None)
    if _post:
        try:
            _dist = style_distance(style_profile(Image.open(_post[1])))
        except Exception:
            _dist = 99.0
        if _dist <= 2.0:            # house style, verified close to the reference
            best = _post[1]
            print(f"thumb-alert: house-style poster chosen (dist {_dist})", flush=True)
        else:
            print(f"thumb-alert: poster off-reference (dist {_dist}), fallback used", flush=True)
    final = os.path.join(workdir, "thumb.jpg")
    from PIL import Image
    im = Image.open(best).convert("RGB").resize((1280, 720), Image.LANCZOS)
    q = 90
    im.save(final, quality=q)
    while os.path.getsize(final) > 2 * 1024 * 1024 and q > 60:
        q -= 8
        im.save(final, quality=q)
    print("thumb-alert: concepts " +
          ", ".join(f"{c[0]}:{c[2]}" for c in concepts) +
          f" | picked concept {concepts[0][0]} (hook {phrase!r})", flush=True)
    return final


if __name__ == "__main__":
    import sys, json
    e = {"title": sys.argv[1] if len(sys.argv) > 1 else
         "OpenAI Just Built an AI That Rewrites Its Own Code"}
    wd = sys.argv[2] if len(sys.argv) > 2 else "."
    print(build(e, wd))
