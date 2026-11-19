"""OpenMontage সেতু — বাইরের AGPL টুলগুলোকে আমাদের পাইপলাইনে ঢোকানোর একমাত্র দরজা।

কেন আলাদা ফাইল: OpenMontage (github.com/OpenMontageInc/OpenMontage, AGPL-3.0)
আমাদের কোডের সঙ্গে মেশানো হয়নি, শুধু দরকারমতো আমদানি করা হয়। কোনো টুল না থাকলে
এই ফাইলটা চুপচাপ None ফেরত দেয়, তাই পাইপলাইন কখনো ভাঙে না।

এখানে শুধু ffmpeg-ভিত্তিক, শূন্য-খরচের টুলগুলো ব্যবহার করা হচ্ছে:
  scene_detect          → শট বাউন্ডারি (কাট কোথায় বসবে)
  auto_reframe          → 16:9 → 9:16 (Shorts বানানোর জন্য)
  composition_validator → ফ্রেমে বিষয়বস্তু ঠিক জায়গায় আছে কি না
  visual_qa             → কালো ফ্রেম, ফ্রিজ, এক্সপোজার ইত্যাদি যাচাই
  color_grade           → একই রকম গ্রেডিং
  audio_mixer/audio_enhance → অডিও মেশানো ও পরিষ্কার করা

যেগুলো টাকা লাগে (Veo, Sora, ElevenLabs, fal, Kling) সেগুলো এখানে রাখা হয়নি।
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

OM_ROOT = os.environ.get("OPENMONTAGE_ROOT", "")


def _import(module: str, cls: str):
    """OpenMontage থেকে একটা টুল ক্লাস আনি; না পেলে None।"""
    try:
        import importlib
        if OM_ROOT and OM_ROOT not in os.sys.path:
            os.sys.path.insert(0, OM_ROOT)
        mod = importlib.import_module(module)
        return getattr(mod, cls)
    except Exception:
        return None


def available() -> dict[str, bool]:
    """কোন কোন টুল এখন ব্যবহারযোগ্য।"""
    return {
        "scene_detect": _import("tools.analysis.scene_detect", "SceneDetect") is not None,
        "auto_reframe": _import("tools.video.auto_reframe", "AutoReframe") is not None,
        "composition_validator": _import("tools.analysis.composition_validator", "CompositionValidator") is not None,
        "visual_qa": _import("tools.analysis.visual_qa", "VisualQA") is not None,
        "color_grade": _import("tools.enhancement.color_grade", "ColorGrade") is not None,
    }


def _run(module: str, cls: str, inputs: dict) -> dict[str, Any] | None:
    klass = _import(module, cls)
    if klass is None:
        return None
    try:
        res = klass().execute(inputs)
    except Exception as exc:  # টুল ভাঙলেও পাইপলাইন চলবে
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    ok = bool(getattr(res, "success", False))
    return {"ok": ok, "data": getattr(res, "data", None),
            "artifacts": getattr(res, "artifacts", None),
            "error": getattr(res, "error", None)}


def detect_scenes(video: str, threshold: float = 27.0) -> dict[str, Any] | None:
    """শট বাউন্ডারি: [(start, end, duration), ...]।"""
    out = _run("tools.analysis.scene_detect", "SceneDetect",
               {"input_path": str(video), "threshold": threshold})
    if not out or not out.get("ok"):
        return out
    data = out.get("data") or {}
    return {"ok": True, "count": data.get("scene_count"),
            "scenes": [(s["start_seconds"], s["end_seconds"], s["duration_seconds"])
                       for s in data.get("scenes", [])]}


def reframe_vertical(src: str, dst: str, aspect: str = "portrait") -> dict[str, Any] | None:
    """16:9 ভিডিওকে 9:16 বানায় (Shorts/Reels)। ফেস ট্র্যাকিং না থাকলে কেন্দ্র-ক্রপ।"""
    out = _run("tools.video.auto_reframe", "AutoReframe",
               {"input_path": str(src), "output_path": str(dst), "target_aspect": aspect})
    if not out:
        return None
    ok = out.get("ok") and Path(dst).exists()
    return {"ok": ok, "output": str(dst) if Path(dst).exists() else None,
            "error": out.get("error")}


def validate_composition(video: str) -> dict[str, Any] | None:
    return _run("tools.analysis.composition_validator", "CompositionValidator",
                {"input_path": str(video)})


def visual_qa(video: str) -> dict[str, Any] | None:
    return _run("tools.analysis.visual_qa", "VisualQA", {"input_path": str(video)})


def grade(src: str, dst: str, preset: str = "cinematic") -> dict[str, Any] | None:
    out = _run("tools.enhancement.color_grade", "ColorGrade",
               {"input_path": str(src), "output_path": str(dst), "preset": preset})
    if not out:
        return None
    return {"ok": out.get("ok") and Path(dst).exists(), "output": str(dst) if Path(dst).exists() else None,
            "error": out.get("error")}


def _ffprobe(path: str) -> dict:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json",
                            "-show_format", "-show_streams", path],
                           capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout or "{}")
    except Exception:
        return {}


def probe(path: str) -> dict:
    """নিজের ছোট প্রোব — OM না থাকলেও কাজ করে।"""
    d = _ffprobe(path)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), {})
    return {"width": v.get("width"), "height": v.get("height"),
            "duration": float((d.get("format") or {}).get("duration") or 0),
            "fps": v.get("r_frame_rate"), "has_audio": bool(a)}


if __name__ == "__main__":
    print(json.dumps(available(), indent=1))
