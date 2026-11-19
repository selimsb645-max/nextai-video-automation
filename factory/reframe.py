"""16:9 → 9:16 রিফ্রেম, শুধু ffmpeg দিয়ে — কোনো বাইরের লাইব্রেরি বা লাইসেন্স ঝামেলা নেই।

কেন নিজের কোড: OpenMontage-এর auto_reframe একই কাজ করে, কিন্তু ওটা AGPL-3.0 আর
আমাদের রেপো public। ওই একটা ফিচারের জন্য পুরো রেপো AGPL করা বা private করে
Actions মিনিট খরচ করা — দুটোই ক্ষতি। ffmpeg-এর crop/pad দিয়েই কাজটা সমান ভালো হয়।

তিনটে মোড:
  crop  — ফ্রেম ভরে ৯:১৬ করে (কেন্দ্র থেকে কাটে; top/bottom দিয়ে উপরে/নিচে ঝোঁক)
  pad   — মূল ফ্রেম অক্ষত রেখে ওপরে-নিচে ঝাপসা ব্যাকগ্রাউন্ড (Shorts-এ প্রচলিত)
  blur  — pad-এরই নামান্তর, পাঠকদের বোঝার সুবিধায়

    from factory.reframe import to_vertical
    to_vertical("long.mp4", "short.mp4", mode="pad")
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

DEFAULT_W, DEFAULT_H = 1080, 1920


def _ffprobe(path: str) -> dict:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=120,
        ).stdout
        return json.loads(out or "{}")
    except Exception:
        return {}


def probe(path: str) -> dict:
    """width/height/duration/fps/has_audio — রিফ্রেম ঠিক হলো কি না যাচাই করার জন্য।"""
    d = _ffprobe(path)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), {})
    return {
        "width": v.get("width"),
        "height": v.get("height"),
        "duration": float((d.get("format") or {}).get("duration") or 0.0),
        "fps": v.get("r_frame_rate"),
        "has_audio": bool(a),
    }


def _filters(mode: str, w: int, h: int, bias: str) -> tuple[list[str], list[str]]:
    """(input_args, filter_args) ফেরত দেয়।"""
    if mode in ("pad", "blur"):
        # পেছনে ভরা ঝাপসা ক্যানভাস, সামনে পুরো ফ্রেম — কিছুই কাটা পড়ে না
        fc = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},gblur=sigma=28,eq=brightness=-0.06[bg];"
            f"[0:v]scale={w}:-2:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1[v]"
        )
        return [], ["-filter_complex", fc, "-map", "[v]", "-map", "0:a?"]

    # crop: উচ্চতা h-এ স্কেল করে প্রস্থ কেটে ফেলা
    x = {"left": "0", "right": f"iw-{w}", "center": f"(iw-{w})/2"}.get(bias, f"(iw-{w})/2")
    vf = f"scale=-2:{h},crop={w}:{h}:{x}:0,setsar=1"
    return [], ["-vf", vf]


def to_vertical(src: str, dst: str, mode: str = "crop", bias: str = "center",
                width: int = DEFAULT_W, height: int = DEFAULT_H,
                crf: int = 20, preset: str = "veryfast") -> dict:
    """ভিডিওকে ভার্টিকাল করে dst-তে লেখে। {ok, output, error, probe} ফেরত দেয়।"""
    src, dst = str(src), str(dst)
    if not Path(src).exists():
        return {"ok": False, "error": f"missing input: {src}"}
    if not shutil.which("ffmpeg"):
        return {"ok": False, "error": "ffmpeg not installed"}
    Path(dst).parent.mkdir(parents=True, exist_ok=True)

    in_args, filt = _filters(mode, width, height, bias)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src, *in_args, *filt,
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", dst]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if r.returncode != 0 or not Path(dst).exists() or Path(dst).stat().st_size < 1024:
        return {"ok": False, "error": (r.stderr or "ffmpeg failed").strip()[-400:]}

    info = probe(dst)
    ok = info["width"] == width and info["height"] == height
    return {"ok": ok, "output": dst, "mode": mode, "probe": info,
            "error": None if ok else f"unexpected size {info['width']}x{info['height']}"}


def is_vertical(path: str) -> bool:
    p = probe(path)
    return bool(p["width"] and p["height"] and p["height"] > p["width"])


if __name__ == "__main__":
    import sys
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else str(Path(src).with_name("vertical.mp4"))
    print(json.dumps(to_vertical(src, out, mode=(sys.argv[3] if len(sys.argv) > 3 else "crop")),
                     ensure_ascii=False, indent=1))
