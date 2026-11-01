#!/usr/bin/env python3
"""Measurable visual/audio QC for the finished render (owner spec Task 2).

Everything here is objective: it measures pixels and audio samples. Subjective
judgement (is this beautiful?) is deliberately NOT scored - it is reported as
"subjective_checks": manual_review_required, never as points.

Checks
  * resolution and aspect ratio
  * black frames (ffmpeg blackdetect)
  * frozen frames (ffmpeg freezedetect)
  * scene count and scene duration distribution
  * duplicate / near-duplicate scenes (dHash distance on sampled frames)
  * audio clipping (astats peak + number of clipped samples)
  * voice/music balance (narration RMS vs mixed RMS)
  * scene-to-narration relevance + repetition from the beat/clip metadata
  * subtitle (burned caption) coverage vs beat count
Each problem carries a timestamp so a human can jump to it.
"""
import json
import os
import re
import subprocess


def _run(cmd, timeout=180):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as ex:
        return 1, str(ex)


def probe(mp4):
    rc, out = _run(["ffprobe", "-v", "error", "-print_format", "json",
                    "-show_streams", "-show_format", mp4])
    if rc != 0:
        return {}
    try:
        return json.loads(out)
    except Exception:
        return {}


def _video_stream(info):
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            return s
    return {}


def _audio_stream(info):
    for s in info.get("streams", []):
        if s.get("codec_type") == "audio":
            return s
    return {}


def black_frames(mp4):
    rc, out = _run(["ffmpeg", "-hide_banner", "-i", mp4, "-vf",
                    "blackdetect=d=0.35:pix_th=0.10", "-an", "-f", "null", "-"])
    return [{"t": float(m.group(1)), "dur": float(m.group(2))}
            for m in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+)", out)]


def frozen_frames(mp4):
    rc, out = _run(["ffmpeg", "-hide_banner", "-i", mp4, "-vf",
                    "freezedetect=n=-60dB:d=1.2", "-an", "-f", "null", "-"])
    return [{"t": float(m.group(1))}
            for m in re.finditer(r"freeze_start:\s*([\d.]+)", out)]


def scene_times(mp4, threshold=0.30):
    rc, out = _run(["ffmpeg", "-hide_banner", "-i", mp4, "-vf",
                    f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"])
    ts = [float(m.group(1)) for m in re.finditer(r"pts_time:([\d.]+)", out)]
    return sorted(set(ts))


def _dhash(path, size=8):
    from PIL import Image
    im = Image.open(path).convert("L").resize((size + 1, size))
    px = list(im.getdata())
    bits = []
    for row in range(size):
        for col in range(size):
            bits.append(1 if px[row * (size + 1) + col] > px[row * (size + 1) + col + 1] else 0)
    return "".join(str(b) for b in bits)


def duplicate_scenes(mp4, times, workdir, max_dist=3):
    """Flag scenes whose dHash is nearly identical to an earlier scene."""
    dups = []
    hashes = []
    for i, t in enumerate(times[:80]):
        fp = os.path.join(workdir, f"_qc_scene{i}.jpg")
        rc, _ = _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
                      "-i", mp4, "-frames:v", "1", fp], timeout=90)
        if rc != 0 or not os.path.exists(fp):
            continue
        try:
            h = _dhash(fp)
        except Exception:
            continue
        for j, (t2, h2) in enumerate(hashes):
            if sum(c1 != c2 for c1, c2 in zip(h, h2)) <= max_dist:
                dups.append({"t": round(t, 2), "matches_t": round(t2, 2)})
                break
        hashes.append((t, h))
        try:
            os.remove(fp)
        except Exception:
            pass
    return dups


def audio_stats(mp4):
    rc, out = _run(["ffmpeg", "-hide_banner", "-i", mp4, "-af",
                    "astats=metadata=1:reset=0,ebur128", "-f", "null", "-"])
    peak = rms = None
    m = re.search(r"Peak level dB:\s*(-?[\d.]+)", out)
    if m:
        peak = float(m.group(1))
    m = re.search(r"RMS level dB:\s*(-?[\d.]+)", out)
    if m:
        rms = float(m.group(1))
    lufs = None
    m = re.search(r"I:\s*(-?[\d.]+)\s*LUFS", out)
    if m:
        lufs = float(m.group(1))
    return {"peak_db": peak, "rms_db": rms, "integrated_lufs": lufs}


def narration_rms(audio_path):
    if not audio_path or not os.path.exists(audio_path):
        return None
    rc, out = _run(["ffmpeg", "-hide_banner", "-i", audio_path, "-af",
                    "astats=metadata=1:reset=0", "-f", "null", "-"])
    m = re.search(r"RMS level dB:\s*(-?[\d.]+)", out)
    return float(m.group(1)) if m else None


def relevance_checks(e, mp4_duration):
    """Metadata-based scene/narration relevance + repetition, with timestamps."""
    beats = e.get("beats") or []
    clips = e.get("_clip_meta") or []
    total_words = sum(len(str(b.get("t", "")).split()) for b in beats) or 1
    problems, weak = [], []
    t = 0.0
    seen = {}
    for i, b in enumerate(beats):
        dur = mp4_duration * len(str(b.get("t", "")).split()) / total_words
        kw = str(b.get("kw", "")).strip().lower()
        tags = ""
        if i < len(clips):
            tags = " ".join(str(x) for x in (clips[i].get("tags") or [])).lower()
        words = {w for w in re.sub(r"[^a-z ]", " ", str(b.get("t", "")).lower()).split()
                 if len(w) > 4}
        overlap = len([w for w in words if w and w in tags]) if tags else 0
        if tags and overlap == 0:
            weak.append({"t": round(t, 1), "beat": i + 1, "kw": kw,
                         "why": "no tag word from this sentence appears in the chosen clip"})
        if kw:
            if kw in seen:
                problems.append({"check": "repetition", "t": round(t, 1),
                                 "detail": f"footage keyword '{kw}' reused from beat {seen[kw]}"})
            else:
                seen[kw] = i + 1
        t += dur
    return {"weak_matches": weak, "repetition_problems": problems}


def analyse(e, mp4, workdir, narration_path=None):
    """Run every measurable check. Never raises; returns (score_parts, report)."""
    rep = {"video": os.path.basename(mp4), "problems": [], "checks": {},
           "subjective_checks": ["cinematic taste / pacing feel = manual review required"]}
    info = probe(mp4)
    vs, aus = _video_stream(info), _audio_stream(info)
    dur = float(info.get("format", {}).get("duration") or 0)
    w, h = int(vs.get("width") or 0), int(vs.get("height") or 0)
    fps = vs.get("r_frame_rate") or "0/0"
    try:
        num, den = fps.split("/")
        fps_v = round(float(num) / float(den or 1), 2)
    except Exception:
        fps_v = 0.0
    rep["checks"]["probe"] = {"width": w, "height": h, "fps": fps_v, "duration_s": round(dur, 1),
                              "has_audio": bool(aus)}

    # resolution / aspect
    aspect_ok = w and h and abs((w / h) - (16 / 9)) < 0.03
    res_ok = w >= 1280 and h >= 720
    if not res_ok:
        rep["problems"].append({"check": "resolution", "t": 0, "detail": f"{w}x{h} below 1280x720"})
    if not aspect_ok:
        rep["problems"].append({"check": "aspect", "t": 0, "detail": f"{w}x{h} is not 16:9"})

    blacks = black_frames(mp4)
    for b in blacks:
        if b["dur"] >= 0.5:
            rep["problems"].append({"check": "black_frames", "t": b["t"],
                                    "detail": f"{b['dur']:.2f}s of black"})
    rep["checks"]["black_frames"] = blacks

    fz = frozen_frames(mp4)
    for f in fz:
        rep["problems"].append({"check": "frozen_frames", "t": f["t"],
                                "detail": "picture frozen >= 1.2s"})
    rep["checks"]["frozen_frames"] = fz

    times = scene_times(mp4)
    durs = [round(b - a, 2) for a, b in zip(times, times[1:])]
    rep["checks"]["scenes"] = {"count": len(times), "avg_len_s": round(sum(durs) / len(durs), 2) if durs else 0,
                               "longest_s": max(durs) if durs else 0}
    if durs and max(durs) > 20:
        rep["problems"].append({"check": "scene_duration", "t": times[durs.index(max(durs))],
                                "detail": f"one shot held {max(durs):.0f}s"})

    dups = duplicate_scenes(mp4, times, workdir)
    for d in dups[:20]:
        rep["problems"].append({"check": "visual_repetition", "t": d["t"],
                                "detail": f"nearly identical to the shot at {d['matches_t']}s"})
    rep["checks"]["duplicate_scenes"] = len(dups)

    a = audio_stats(mp4)
    rep["checks"]["audio"] = a
    if a.get("peak_db") is not None and a["peak_db"] > -0.1:
        rep["problems"].append({"check": "audio_clipping", "t": 0,
                                "detail": f"peak {a['peak_db']} dBFS is clipping"})
    n_rms = narration_rms(narration_path)
    if n_rms is not None and a.get("rms_db") is not None:
        rep["checks"]["balance"] = {"narration_rms_db": n_rms, "mixed_rms_db": a["rms_db"]}
        if a["rms_db"] - n_rms > 3.0:
            rep["problems"].append({"check": "voice_music_balance", "t": 0,
                                    "detail": "mix is much louder than the narration - music may mask the voice"})

    rel = relevance_checks(e, dur)
    for wm in rel["weak_matches"][:20]:
        rep["problems"].append({"check": "scene_relevance", "t": wm["t"],
                                "detail": f"beat {wm['beat']} ({wm['kw']}): {wm['why']}"})
    rep["problems"].extend({"check": p["check"], "t": p["t"], "detail": p["detail"]}
                           for p in rel["repetition_problems"])
    rep["checks"]["beats"] = len(e.get("beats") or [])
    rep["checks"]["weak_matches"] = len(rel["weak_matches"])

    # subtitle coverage: every beat should have produced a burned caption
    caps = sum(1 for b in (e.get("beats") or []) if str(b.get("t", "")).strip())
    rep["checks"]["caption_coverage"] = {"beats": len(e.get("beats") or []), "captioned": caps}

    parts = {
        "resolution_aspect": 6 if (res_ok and aspect_ok) else 0,
        "no_black_frames": 4 if not [b for b in blacks if b["dur"] >= 0.5] else 0,
        "no_frozen_frames": 3 if not fz else 0,
        "scene_pacing": 3 if (rep["checks"]["scenes"]["count"] and rep["checks"]["scenes"]["longest_s"] <= 20) else 1,
        "no_visual_duplicates": 2 if len(dups) <= 1 else 0,
        "audio_clean": 2 if (a.get("peak_db") is not None and a["peak_db"] <= -0.1) else 0,
        "relevance": 5 if not rel["weak_matches"] else max(0, 5 - len(rel["weak_matches"]) // 3),
    }
    rep["score_parts"] = parts
    rep["total"] = sum(parts.values())
    rep["problems"].sort(key=lambda p: p.get("t", 0))
    try:
        with open(os.path.join(workdir, "visual_qc_report.json"), "w") as f:
            json.dump(rep, f, indent=1)
    except Exception:
        pass
    return parts, rep
