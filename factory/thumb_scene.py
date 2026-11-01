#!/usr/bin/env python3
"""Cinematic launch-scene thumbnails: presenter + product + LED screen + badge.

Owner reference (2026-11-01, attached twice): "GENIE 4" keynote frame -
a real presenter on the left, a floating product with its name on it, a huge
curved LED wall behind showing the launch keyart (city skyline, glowing globe,
brand wordmark, INTRODUCING, product name, descriptor), a white "UNVEILED!"
badge top-right, spotlight cones, reflective floor, audience silhouettes.

Every element is either a free-licence photo (Wikimedia/Openverse, credit kept)
or drawn here. No AI image API is used or needed.
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageStat

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
W, H = 1280, 720
WHITE = (255, 255, 255)
CYAN = (0, 236, 255)
GRAY = (228, 232, 240)

GOOGLE_COLS = [(66, 133, 244), (234, 67, 53), (251, 188, 5), (66, 133, 244),
               (52, 168, 83), (234, 67, 53)]


def _f(name, size):
    from PIL import ImageFont
    p = os.path.join(FONTS, name)
    try:
        return ImageFont.truetype(p, size)
    except Exception:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)


def disp(size):
    return _f("Anton-Regular.ttf", size)


def black(size):
    return _f("ArchivoBlack-Regular.ttf", size)


# ── keyart: what the LED wall shows ─────────────────────────────────────────
def keyart(words, brand="Google", product="GENIE 4", desc="SYNTHETIC REALITY",
           hue=CYAN):
    """Launch keyart drawn at 2x, to be warped onto the LED wall."""
    import random
    cw, ch = 1800, 980
    im = Image.new("RGB", (cw, ch), (2, 8, 16))
    d = ImageDraw.Draw(im)
    # horizon glow
    for y in range(ch):
        k = y / ch
        d.line([(0, y), (cw, y)], fill=(int(2 + 10 * (1 - k)), int(10 + 30 * (1 - k)),
                                       int(22 + 58 * (1 - k))))
    # skyline
    random.seed(23)
    x = 0
    while x < cw:
        bw = random.randint(44, 120)
        bh = random.randint(int(ch * 0.10), int(ch * 0.34))
        top = int(ch * 0.52) - bh
        d.rectangle([x, top, x + bw, int(ch * 0.60)], fill=(4, 16, 30))
        for wy in range(top + 12, int(ch * 0.58), 14):
            for wx in range(x + 8, x + bw - 8, 14):
                if random.random() < 0.45:
                    d.rectangle([wx, wy, wx + 4, wy + 6],
                                fill=(int(40 + 80 * random.random()),
                                      int(150 + 90 * random.random()),
                                      int(200 + 55 * random.random())))
        x += bw + random.randint(6, 22)
    # glowing globe
    gx, gy, gr = int(cw * 0.5), int(ch * 0.30), int(ch * 0.20)
    globe = Image.new("RGB", (cw, ch), (0, 0, 0))
    gd = ImageDraw.Draw(globe)
    for i in range(gr, 0, -2):
        a = 1 - i / gr
        gd.ellipse([gx - i, gy - i, gx + i, gy + i],
                   fill=(int(6 + 20 * a), int(60 + 150 * a), int(110 + 145 * a)))
    gd.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], outline=(180, 245, 255), width=3)
    for k in range(1, 5):
        r = int(gr * k / 5)
        gd.ellipse([gx - r, gy - gr, gx + r, gy + gr], outline=(150, 230, 255), width=2)
        gd.ellipse([gx - gr, gy - r, gx + gr, gy + r], outline=(150, 230, 255), width=2)
    globe = globe.filter(ImageFilter.GaussianBlur(3))
    im = Image.blend(im, Image.composite(globe, im, globe.convert("L").point(
        lambda v: 255 if v > 12 else 0)), 0.92)
    # text block on the wall
    d = ImageDraw.Draw(im)
    y = int(ch * 0.10)
    if brand:
        fb = black(74)
        tw = sum(d.textlength(c, font=fb) for c in brand)
        bx = (cw - tw) / 2
        for i, c in enumerate(brand):
            col = GOOGLE_COLS[i % len(GOOGLE_COLS)] if brand.lower() == "google" else WHITE
            d.text((bx, y), c, font=fb, fill=col)
            bx += d.textlength(c, font=fb)
        y += 92
    fk = _f("ArchivoBlack-Regular.ttf", 44)
    kx = (cw - sum(d.textlength(c, font=fk) + 6 for c in "INTRODUCING")) / 2
    cx = kx
    for c in "INTRODUCING":
        d.text((cx, y), c, font=fk, fill=(238, 242, 250))
        cx += d.textlength(c, font=fk) + 6
    y += 72
    fp = disp(210)
    pw = d.textlength(product, font=fp)
    d.text(((cw - pw) / 2, y), product, font=fp, fill=WHITE,
           stroke_width=5, stroke_fill=(0, 0, 0))
    y += 205
    fd = _f("ArchivoBlack-Regular.ttf", 40)
    dx = (cw - sum(d.textlength(c, font=fd) + 7 for c in desc)) / 2
    cx = dx
    for c in desc:
        d.text((cx, y), c, font=fd, fill=hue)
        cx += d.textlength(c, font=fd) + 7
    # scanlines
    for yy in range(0, ch, 4):
        d.line([(0, yy), (cw, yy)], fill=(0, 0, 0))
    return im


def led_wall(canvas, art, box, curve=0.06):
    """Warp the keyart onto a curved LED wall with pixel seams and bloom."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    aw, ah = art.size
    strip = Image.new("RGB", (w, h), (0, 0, 0))
    cols = max(60, w // 6)
    for i in range(cols):
        sx0, sx1 = int(i * aw / cols), int((i + 1) * aw / cols)
        if sx1 <= sx0:
            continue
        col = art.crop((sx0, 0, sx1, ah)).resize((max(1, int(w / cols)) + 1, h),
                                                  Image.LANCZOS)
        dx0 = int(i * w / cols)
        off = int(curve * h * (1 - (2 * i / cols - 1) ** 2) ** 0.5)
        strip.paste(col, (dx0, -off + int(curve * h * 0.5)))
    # LED seam grid
    d = ImageDraw.Draw(strip)
    for gx in range(0, w, 7):
        d.line([(gx, 0), (gx, h)], fill=(0, 0, 0))
    for gy in range(0, h, 7):
        d.line([(0, gy), (w, gy)], fill=(0, 0, 0))
    # bezel
    d.rectangle([0, 0, w - 1, h - 1], outline=(14, 16, 20), width=7)
    canvas.paste(strip, (x0, y0))
    bloom = strip.filter(ImageFilter.GaussianBlur(38))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(bloom, (x0, y0))
    layer.putalpha(layer.convert("L").point(lambda v: min(150, int(v * 0.62))))
    return Image.alpha_composite(canvas.convert("RGBA"), layer).convert("RGB"), strip


def cut_person(path, target_h, keep_bottom=False):
    """Load a photo, grade it, feather the edges, optionally cut at the waist."""
    im = Image.open(path).convert("RGB")
    sc = target_h / im.height
    im = im.resize((max(1, int(im.width * sc)), target_h), Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.10)
    im = ImageEnhance.Brightness(im).enhance(1.02)
    mask = Image.new("L", im.size, 255).filter(ImageFilter.GaussianBlur(10))
    return im, mask


def bust_crop(path, target_h, pad=2.1):
    """Face-aware bust crop: the presenter must read as a cut-out person on the
    stage, not a wide event photo pasted over it (the reference is a bust)."""
    import numpy as np
    im = Image.open(path).convert("RGB")
    box = None
    try:
        import cv2
        arr = np.asarray(im)[:, :, ::-1].copy()
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cas.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            cw = int(w * pad)
            ch = int(h * pad * 2.0)
            cx = x + w // 2
            cy = y + int(h * 0.9)
            x0 = max(0, cx - cw // 2)
            y0 = max(0, cy - int(ch * 0.42))
            box = (x0, y0, min(im.width, x0 + cw), min(im.height, y0 + ch))
            print(f"scene: face {w}x{h} -> bust crop {box}", flush=True)
    except Exception as _e:
        print("scene: face detect skipped:", str(_e)[:70], flush=True)
    if box:
        im = im.crop(box)
    sc = target_h / im.height
    im = im.resize((max(1, int(im.width * sc)), target_h), Image.LANCZOS)
    # lift exposure a little: presenters are lit on stage
    im = ImageEnhance.Brightness(im).enhance(1.06)
    im = ImageEnhance.Contrast(im).enhance(1.10)
    im = ImageEnhance.Color(im).enhance(1.08)
    mask = Image.new("L", im.size, 255).filter(ImageFilter.GaussianBlur(9))
    return im, mask


def cut_product(path, target_w, key_black=True):
    """Product photo with its dark background removed (luminance key)."""
    im = Image.open(path).convert("RGB")
    sc = target_w / im.width
    im = im.resize((target_w, max(1, int(im.height * sc))), Image.LANCZOS)
    g = im.convert("L")
    mask = g.point(lambda v: 0 if v < 26 else (255 if v > 60 else int((v - 26) / 34 * 255)))
    mask = mask.filter(ImageFilter.GaussianBlur(2))
    return im, mask


def badge(canvas, top_text="UNVEILED!", bottom_text="GENIE 4 TECH", hue=CYAN):
    d = ImageDraw.Draw(canvas)
    fa = _f("ArchivoBlack-Regular.ttf", 30)
    fb = _f("ArchivoBlack-Regular.ttf", 26)
    tw = max(d.textlength(top_text, font=fa), d.textlength(bottom_text, font=fb))
    x1, y1 = W - 44, 40 + 34 + 42
    x0, y0 = int(x1 - tw - 56), 40
    d.rectangle([x0, y0, x1, y0 + 40], fill=WHITE)
    d.text((x0 + 14, y0 + 5), top_text, font=fa, fill=(10, 10, 10))
    d.rectangle([x0, y0 + 40, x1, y1], fill=(6, 8, 12))
    d.rectangle([x0, y0 + 40, x1, y1], outline=hue, width=2)
    d.text((x0 + 14, y0 + 46), bottom_text, font=fb, fill=WHITE)
    return canvas


def build(presenter, product=None, product_label="GENIE 4", brand="Google",
          product_name="GENIE 4", desc="SYNTHETIC REALITY", hue=CYAN,
          out="thumb.jpg", badge_bottom=None):
    """Compose the keynote scene. Returns the saved path."""
    art = keyart(None, brand, product_name, desc, hue)
    canvas = Image.new("RGB", (W, H), (3, 4, 7))
    canvas, strip = led_wall(canvas, art, (int(W * 0.05), int(H * 0.05),
                                           int(W * 0.95), int(H * 0.64)))
    horizon = int(H * 0.66)
    d = ImageDraw.Draw(canvas, "RGBA")
    # spotlight cones
    for x0 in (int(W * 0.18), int(W * 0.52), int(W * 0.86)):
        d.polygon([(x0 - 22, 0), (x0 + 22, 0), (x0 + 170, horizon), (x0 - 170, horizon)],
                  fill=(150, 215, 255, 16))
    # floor + reflection of the wall
    d.rectangle([0, horizon, W, H], fill=(4, 6, 11, 250))
    ref = strip.transpose(Image.FLIP_TOP_BOTTOM).resize((strip.width, int((H - horizon) * 0.7)))
    ref = ref.filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.30))
    canvas.paste(ref, (int(W * 0.05), horizon))
    # presenter
    if presenter and os.path.exists(presenter):
        ph = int(H * 0.70)
        pim, pmask = bust_crop(presenter, ph)
        px = int(W * 0.035)
        py = horizon - int(ph * 0.92)
        # contact shadow + floor reflection
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse([px + 20, horizon - 18, px + pim.width - 20, horizon + 26],
                                   fill=(0, 0, 0, 200))
        sh = sh.filter(ImageFilter.GaussianBlur(16))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), sh).convert("RGB")
        refl = pim.transpose(Image.FLIP_TOP_BOTTOM).resize(
            (pim.width, int(pim.height * 0.42))).filter(ImageFilter.GaussianBlur(7))
        refl = refl.point(lambda v: int(v * 0.26))
        canvas.paste(refl, (px, horizon + 4),
                     pmask.resize(refl.size).point(lambda v: int(v * 0.5)))
        canvas.paste(pim, (px, py), pmask)
    # floating product
    if product and os.path.exists(product):
        prw = int(W * 0.20)
        prim, prmask = cut_product(product, prw)
        gx = int(W * 0.40)
        gy = int(horizon * 0.40)
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([gx - 40, gy - 30, gx + prw + 40, gy + prim.height + 30],
                                     fill=hue + (70,))
        glow = glow.filter(ImageFilter.GaussianBlur(34))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), glow).convert("RGB")
        canvas.paste(prim, (gx, gy), prmask)
        d2 = ImageDraw.Draw(canvas)
        fl = black(34)
        d2.text((gx + 8, gy + prim.height + 12), product_label, font=fl,
                fill=WHITE, stroke_width=3, stroke_fill=(0, 0, 0))
    # audience
    import random
    random.seed(3)
    d3 = ImageDraw.Draw(canvas, "RGBA")
    for i in range(14):
        x = int(W * 0.30 + i * (W * 0.05) + random.randint(-6, 6))
        hh = random.randint(40, 70)
        d3.ellipse([x - 13, H - hh - 22, x + 13, H - hh + 4], fill=(2, 3, 5, 245))
        d3.rounded_rectangle([x - 22, H - hh, x + 22, H + 40], radius=14, fill=(2, 3, 5, 245))
    canvas = badge(canvas, "UNVEILED!", badge_bottom or f"{product_name} TECH", hue)
    canvas.save(out, quality=92, subsampling=1)
    return out
