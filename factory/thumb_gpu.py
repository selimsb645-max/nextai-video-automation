#!/usr/bin/env python3
"""Free-GPU thumbnail generator for GitHub Actions.

Owner decision 2026-11-01: no Base44 integration credits are spent on images,
and the diffusion model must NOT run on the Actions CPU runner (too slow, poor
quality). Instead the workflow calls a FREE GPU endpoint over HTTPS for the
text-free keyart, and the exact typography is composited locally with PIL/Anton
because diffusion models cannot spell reliably.

Backend chain (first that works wins, all optional except the last):
  1. Cloudflare Workers AI  - free 10k neurons/day, FLUX.1-schnell, REST
       secrets: CF_ACCOUNT_ID, CF_API_TOKEN
  2. Hugging Face Space      - free ZeroGPU quota, needs a free HF token
       secret:  HF_TOKEN, optional HF_SPACE (default FLUX.1-schnell)
  3. Procedural stage        - always available, no network (thumb_studio)

Usage:
  python3 factory/thumb_gpu.py --title "..." --out thumb.jpg
  python3 factory/thumb_gpu.py --title "..." --dry-run
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
W, H = 1280, 720
MAX_BYTES = 2 * 1024 * 1024

ACCENTS = {"cyan": (0, 236, 255), "red": (255, 45, 60), "amber": (255, 176, 32),
           "green": (60, 255, 158)}


def _font(size, name="Anton-Regular.ttf"):
    for cand in (os.path.join(FONTS, name),
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            continue
    return ImageFont.load_default()


# ── 1. Cloudflare Workers AI (FLUX.1-schnell, free daily neurons) ───────────
def cloudflare(prompt, w=W, h=H, timeout=90):
    acct = os.environ.get("CF_ACCOUNT_ID", "").strip()
    tok = os.environ.get("CF_API_TOKEN", "").strip()
    if not acct or not tok:
        raise RuntimeError("cloudflare: CF_ACCOUNT_ID / CF_API_TOKEN not set")
    url = (f"https://api.cloudflare.com/client/v4/accounts/{acct}"
           f"/ai/run/@cf/black-forest-labs/flux-1-schnell")
    body = json.dumps({"prompt": prompt, "steps": 8}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    if not data.get("success"):
        raise RuntimeError(f"cloudflare: {json.dumps(data.get('errors'))[:160]}")
    b64 = data["result"]["image"]
    import base64
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")


# ── 2. Hugging Face Space (ZeroGPU, free token) ─────────────────────────────
def hf_space(prompt, w=W, h=H, timeout=180):
    tok = os.environ.get("HF_TOKEN", "").strip()
    if not tok:
        raise RuntimeError("hf: HF_TOKEN not set")
    from gradio_client import Client
    space = os.environ.get("HF_SPACE", "black-forest-labs/FLUX.1-schnell").strip()
    cli = Client(space, hf_token=tok, verbose=False)
    out = cli.predict(prompt=prompt, seed=0, width=w, height=h,
                      num_inference_steps=4, api_name="/infer")
    path = out if isinstance(out, str) else out[0]
    return Image.open(path).convert("RGB")


BACKENDS = [("cloudflare", cloudflare), ("hf_space", hf_space)]


def gpu_keyart(prompt, w=W, h=H):
    """First GPU backend that answers. Returns (image, backend_name)."""
    for name, fn in BACKENDS:
        try:
            img = fn(prompt, w, h)
            img = img.convert("RGB")
            print(f"thumb_gpu: {name} OK {img.size}", flush=True)
            return img, name
        except Exception as e:
            print(f"thumb_gpu: {name} unavailable: {str(e)[:120]}", flush=True)
    return None, "none"


def procedural_fallback(hue=(0, 236, 255)):
    for fn in ("stage", "launch_stage"):
        try:
            m = __import__("thumb_studio")
            out = getattr(m, fn)(hue)
            if isinstance(out, tuple):          # stage() may return (image, info)
                out = out[0]
            if isinstance(out, Image.Image):
                return out
        except Exception as e:
            print(f"thumb_gpu: procedural {fn} failed: {str(e)[:90]}", flush=True)
    return Image.new("RGB", (W, H), (6, 9, 16))


def grade(img, w=W, h=H):
    """Cover-crop to 16:9, darken the left third so type always reads."""
    from PIL import ImageEnhance
    img = img.convert("RGB")
    sc = max(w / img.width, h / img.height)
    img = img.resize((max(w, int(img.width * sc)), max(h, int(img.height * sc))),
                     Image.LANCZOS)
    left = (img.width - w) // 3          # keep the subject (right side) in frame
    img = img.crop((left, (img.height - h) // 2, left + w, (img.height - h) // 2 + h))
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    for i in range(int(w * 0.52)):
        a = int(190 * (1 - i / (w * 0.52)) ** 1.4)
        d.line([(i, 0), (i, h)], fill=(0, 0, 0, a))
    img = Image.alpha_composite(img.convert("RGBA"), shade).convert("RGB")
    return ImageEnhance.Contrast(img).enhance(1.06)


def _fit(draw, text, max_w, start=170, floor=54, font_name="Anton-Regular.ttf"):
    size = start
    while size > floor:
        f = _font(size, font_name)
        if draw.textlength(text, font=f) <= max_w:
            return f, size
        size -= 6
    return _font(floor, font_name), floor


def wrap(draw, words, font, max_w):
    lines, cur = [], []
    for wd in words:
        trial = " ".join(cur + [wd])
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur.append(wd)
        else:
            lines.append(cur)
            cur = [wd]
    if cur:
        lines.append(cur)
    return lines


def add_type(img, headline, kicker="", descriptor="", accent="cyan", accent_word=None):
    """Draw the A-to-Z type stack: kicker, huge headline (accent word picked),
    descriptor. Left 45% block, safe margins, black outline + soft shadow."""
    img = img.convert("RGB")
    accent_rgb = ACCENTS.get(accent, ACCENTS["cyan"]) if isinstance(accent, str) else accent
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    margin, block_w = 56, int(W * 0.48)
    words = headline.upper().split()
    aw = (accent_word or (words[-1] if len(words) > 1 else words[0])).upper()

    f_kick = _font(34)
    f_desc = _font(30)
    f_head, size = _fit(d, " ".join(words), block_w)
    lines = wrap(d, words, f_head, block_w)
    lh = int(size * 1.02)
    total = (lh * len(lines)) + (46 if kicker else 0) + (44 if descriptor else 0)
    y = max(margin + 24, (H - total) // 2 - 20)

    if kicker:
        k = ""
        for ch in kicker.upper():
            k += ch + " "
        d.text((margin, y), k.strip(), font=f_kick, fill=(238, 244, 252, 255),
               stroke_width=4, stroke_fill=(0, 0, 0, 255))
        y += 46
    for ln in lines:
        x = margin
        for wi, wd in enumerate(ln):
            col = accent_rgb + (255,) if wd.strip(".,!?") == aw else (255, 255, 255, 255)
            d.text((x, y), wd, font=f_head, fill=col, stroke_width=7,
                   stroke_fill=(0, 0, 0, 255))
            x += d.textlength(wd + " ", font=f_head)
        y += lh
    if descriptor:
        d.text((margin, y + 8), descriptor.upper(), font=f_desc,
               fill=(224, 232, 242, 255), stroke_width=4, stroke_fill=(0, 0, 0, 255))
    shadow = layer.filter(ImageFilter.GaussianBlur(9))
    shadow.putalpha(shadow.getchannel("A").point(lambda v: int(v * 0.55)))
    out = Image.alpha_composite(img.convert("RGBA"), shadow)
    out = Image.alpha_composite(out, layer).convert("RGB")
    return out


def save_capped(img, paths, quality=90):
    """Save under YouTube's 2 MB limit to every path the pipeline expects."""
    q = quality
    while q >= 60:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q, subsampling=1, optimize=True)
        if buf.tell() <= MAX_BYTES:
            break
        q -= 6
    data = buf.getvalue()
    saved = []
    for p in paths:
        os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        saved.append(p)
    return saved, len(data)


def build(title, headline=None, kicker="", descriptor="", accent="cyan",
          accent_word=None, image_prompt=None, out_paths=("thumb.jpg",)):
    """Full path: A-to-Z prompt -> free GPU keyart -> local typography -> jpg."""
    try:
        import thumb_prompt as TP
        spec = TP.build_full(title, headline=headline, kicker=kicker or None,
                             descriptor=descriptor or None, accent_word=accent_word)
        prompt = image_prompt or spec["image_prompt"]
        headline = spec["headline"]
        kicker = kicker or spec["kicker"]
        descriptor = descriptor or spec["descriptor"]
        accent_word = accent_word or spec["accent_word"]
    except Exception as e:
        print("thumb_gpu: prompt builder unavailable:", str(e)[:90], flush=True)
        prompt = image_prompt or title
        headline = headline or title.upper()[:24]
    img, backend = gpu_keyart(prompt)
    if img is None:
        img = procedural_fallback()
        backend = "procedural"
    img = grade(img)
    img = add_type(img, headline, kicker, descriptor, accent, accent_word)
    paths, nbytes = save_capped(img, list(out_paths))
    print(f"thumb_gpu: {backend} -> {paths} ({nbytes // 1024} KB)", flush=True)
    return {"paths": paths, "bytes": nbytes, "backend": backend,
            "headline": headline, "kicker": kicker, "descriptor": descriptor,
            "prompt": prompt}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--headline")
    ap.add_argument("--kicker", default="")
    ap.add_argument("--descriptor", default="")
    ap.add_argument("--accent", default="cyan")
    ap.add_argument("--accent-word")
    ap.add_argument("--out", default="thumb.jpg")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    r = build(a.title, a.headline, a.kicker, a.descriptor, a.accent,
              a.accent_word, out_paths=(a.out,))
    print(json.dumps(r, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
