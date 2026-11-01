"""Phase 8 - automated video QC. Machine-readable, no opinions dressed as facts.

Checks (all measured with ffprobe/ffmpeg, never assumed):
  1  resolution            8  missing scene assets
  2  frame rate            9  subtitle timing
  3  A/V duration sync    10  audio clipping
  4  missing audio        11  excessive silence
  5  black frames         12  render errors
  6  frozen frames        13  file corruption
  7  duplicate footage    14  final duration vs narration

The report states explicitly that subjective cinematic quality is NOT provable
by these checks; it only blocks objective defects.
"""
import json
import os
import re
import subprocess


def _run(args):
    return subprocess.run(args, capture_output=True, text=True)


def _probe(path):
    r = _run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
              "-of", "json", path])
    try:
        return json.loads(r.stdout or "{}")
    except Exception:
        return None


def check(mp4, storyboard=None, captions_meta=None, caption_errors=None,
          assets=None, render_errors=None, expected_w=1920, expected_h=1080,
          expected_fps=25, min_seconds=None):
    rep = {"file": os.path.abspath(mp4), "checks": [], "errors": []}

    def add(name, ok, detail, blocking=True):
        rep["checks"].append({"check": name, "ok": bool(ok),
                              "detail": detail, "blocking": blocking})

    info = _probe(mp4) or {}
    streams = info.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = info.get("format") or {}
    dur = float(fmt.get("duration") or 0)
    rep["duration_s"] = round(dur, 2)
    rep["size_bytes"] = int(fmt.get("size") or (os.path.getsize(mp4) if os.path.exists(mp4) else 0))

    if not v:
        rep["errors"].append("no video stream / corrupt container")
        add("file_integrity", False, "ffprobe could not read a video stream")
        rep["ok"] = False
        rep["score"] = 0
        return rep

    # 13 corruption / 1 resolution / 2 fps
    add("file_integrity", dur > 1 and rep["size_bytes"] > 200_000,
        f"duration={dur:.2f}s size={rep['size_bytes']//1024}KB")
    W, H = int(v.get("width") or 0), int(v.get("height") or 0)
    add("resolution", (W, H) == (expected_w, expected_h) or
        (H, W) == (expected_w, expected_h) or (W >= 1080 and H >= 1080),
        f"{W}x{H} (target {expected_w}x{expected_h})")
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0
    add("frame_rate", abs(fps - expected_fps) <= 1.0, f"{fps:.2f} fps (target {expected_fps})")

    # 4 missing audio + 3 sync
    add("audio_present", bool(a), "audio stream " + ("found" if a else "MISSING"))
    if a:
        adur = float(a.get("duration") or dur)
        vdur = float(v.get("duration") or dur)
        add("av_duration_sync", abs(adur - vdur) <= 0.6,
            f"video={vdur:.2f}s audio={adur:.2f}s delta={abs(adur - vdur):.2f}s")

    # 5 black frames / 6 frozen frames
    r = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", mp4,
              "-vf", "blackdetect=d=0.35:pix_th=0.10", "-an", "-f", "null", "-"])
    black = [(float(s), float(e)) for s, e in
             re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr or "")]
    long_black = [b for b in black if b[1] - b[0] > 0.6 and b[0] > 1.0]
    black_cov = sum(e - s for s, e in black) / dur if dur else 0.0
    add("black_frames", not long_black and black_cov < 0.5,
        f"{len(black)} black ranges, {len(long_black)} longer than 0.6s, "
        f"{black_cov * 100:.0f}% of runtime black")

    r = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", mp4,
              "-vf", "freezedetect=n=-60dB:d=3.0", "-an", "-f", "null", "-"])
    frozen = [(float(s), float(e)) for s, e in
              zip(re.findall(r"freeze_start: ([\d.]+)", r.stderr or ""),
                  re.findall(r"freeze_end: ([\d.]+)", r.stderr or ""))]
    add("frozen_frames", len(frozen) == 0,
        f"{len(frozen)} frozen ranges (>=3s)", blocking=False)

    # 7 duplicate footage / 8 missing assets
    if assets:
        used = [a.get("asset_id") for a in assets if a.get("source") != "generated"]
        dup = len(used) - len(set(used))
        add("duplicate_footage", dup == 0, f"{dup} repeated asset ids "
                                          f"of {len(used)} sourced assets")
        missing = [a["path"] for a in assets if not os.path.exists(a.get("path", ""))]
        add("scene_assets_present", not missing,
            f"{len(assets)} assets, {len(missing)} missing files")
        cards = [a for a in assets if a.get("source") == "generated"]
        add("generated_fallback_share", len(cards) <= max(1, len(assets) // 3),
            f"{len(cards)}/{len(assets)} scenes used a generated card",
            blocking=False)
        lic = sorted({a.get("license", "?") for a in assets})
        rep["licenses"] = lic
        widths = [a.get("width") or 0 for a in assets if a.get("source") != "generated"]
        if widths:
            low = sum(1 for w in widths if w and w < 960)
            add("source_resolution", low <= max(1, len(widths) // 2),
                f"{low}/{len(widths)} sourced clips are below 960px wide",
                blocking=False)

    # 9 subtitle timing
    if captions_meta:
        ce = caption_errors or []
        add("subtitle_timing", not ce,
            f"{captions_meta.get('cues', 0)} cues ({captions_meta.get('timing_source')})"
            + (f"; {len(ce)} problems: {ce[:3]}" if ce else ""))
    # 10 clipping / 11 silence
    try:
        from . import audio as A
    except ImportError:
        import audio as A
    if a:
        m = A.measure(mp4)
        rep["audio_metrics"] = m
        add("audio_clipping", (m.get("true_peak_db") or -99) < -0.5,
            f"true peak {m.get('true_peak_db')} dBTP (target < -0.5)",
            blocking=False)
        sr = m.get("silence_ratio")
        add("excessive_silence", sr is not None and sr < 0.22,
            f"silence ratio {sr} of runtime", blocking=False)
        add("loudness", m.get("lufs") is not None and -18 <= (m.get("lufs") or 0) <= -11,
            f"integrated {m.get('lufs')} LUFS (target -14 +/-3)", blocking=False)

    # 12 render errors
    add("render_errors", not render_errors, f"{len(render_errors or [])} scene errors"
        + (f": {render_errors[:2]}" if render_errors else ""))

    # 14 duration vs narration
    if storyboard:
        nd = storyboard.get("narration_duration") or 0
        if nd:
            add("final_duration", abs(dur - nd) <= max(2.5, nd * 0.03),
                f"final {dur:.2f}s vs narration {nd:.2f}s")
        scene_sum = sum(s.get("duration", 0) for s in storyboard.get("scenes", []))
        add("scene_coverage", abs(scene_sum - nd) <= max(1.5, nd * 0.02),
            f"scene timeline {scene_sum:.2f}s vs narration {nd:.2f}s")

    blocking = [c for c in rep["checks"] if c["blocking"]]
    passed = sum(1 for c in blocking if c["ok"])
    rep["score"] = round(100 * passed / len(blocking), 1) if blocking else 0
    rep["ok"] = all(c["ok"] for c in blocking)
    rep["not_provable"] = ("subjective cinematic quality (pacing taste, emotional "
                           "impact, hook strength) is NOT verified by these checks")
    return rep


def save(rep, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, ensure_ascii=False)
    return path


def summary(rep):
    bad = [c for c in rep.get("checks", []) if not c["ok"]]
    head = (f"QC {'PASS' if rep.get('ok') else 'FAIL'} — score {rep.get('score')}, "
            f"{rep.get('duration_s')}s, {rep.get('size_bytes', 0)//1024//1024} MB")
    lines = [head]
    for c in rep.get("checks", []):
        lines.append(f"  {'ok  ' if c['ok'] else 'FAIL'} {c['check']}: {c['detail']}")
    return "\n".join(lines)
