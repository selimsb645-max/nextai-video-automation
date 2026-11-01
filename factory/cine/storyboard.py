"""Phase 2 - AI storyboard engine.

Turns an approved script + narration into a scene-by-scene storyboard:

    scene_id, narration_text, start_time, end_time, visual_description,
    search_query, visual_type, transition, motion_style

Timing strategy (honest, in this order):
 1. per-beat TTS timings if the caller supplies them (beats_timing.json);
 2. otherwise `ffmpeg silencedetect` on the real narration: scene boundaries
    are snapped to the nearest actual pause, which is far closer to the voice
    than a naive word split;
 3. word-count weighting inside each scene for caption timing.
The report records which strategy was used as `timing_source`, so nothing is
presented as measured when it was only estimated.
"""
import json
import os
import re
import subprocess

STOP = set("""a an the of to in on for and or but with without from into over under
is are was were be been being it its this that these those as at by if then than
so such very just about after before now new more most other some any our your
their his her they them we you i he she not no can could will would should may
might have has had do does did which who whom what when where why how""".split())

# what kind of visual a sentence needs
DEMO_CUES = ("demo", "walk", "walking", "running", "grab", "pick up", "dance",
             "test", "launch", "unbox", "fold", "bow", "jump", "roll", "spin",
             "tested", "shown", "watch it")
GRAPH_CUES = ("compare", "first time", "increase", "grew", "billion", "million",
              "percent", "%", "cost", "price", "faster", "cheaper", "twice",
              "three times", "timeline", "before", "after", "ranking", "chart")
INFO_CUES = ("number", "revenue", "valuation", "funding", "share", "index",
             "data", "study", "report", "survey", "statistics")
PERSON_CUES = ("said", "told", "CEO", "founder", "researcher", "team",
               "engineer", "spokesperson", "announced", "warned")


def _words(t):
    return re.findall(r"[A-Za-z0-9'$%.-]+", t or "")


def keywords(text, limit=4):
    """Concrete filmable nouns first: capitals, digits, then long words."""
    toks = [w.strip(".,!?;:\"'") for w in _words(text)]
    out = []
    for w in toks:
        lw = w.lower()
        if lw in STOP or len(lw) < 3:
            continue
        score = 0
        if re.search(r"\d", w):
            score += 3                      # "89K", "GPT-6.1", "$40"
        if w[:1].isupper() and w.lower() not in STOP:
            score += 2                      # brand / product / place
        score += min(len(w), 9) / 10.0
        out.append((score, -len(out), w))
    out.sort(reverse=True)
    seen, keep = set(), []
    for _, _, w in out:
        if w.lower() in seen:
            continue
        seen.add(w.lower())
        keep.append(w)
        if len(keep) >= limit:
            break
    return keep


def _split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def visual_type_for(text):
    low = text.lower()
    if any(c in low for c in DEMO_CUES):
        return "technology_demonstration"
    if any(c in low for c in INFO_CUES):
        return "infographic"
    if any(c in low for c in GRAPH_CUES):
        return "motion_graphics"
    if any(c in low for c in PERSON_CUES):
        return "real_world_footage"
    return "real_world_footage"


def motion_for(index, vtype, text):
    """Vary the move per scene - identical motion on every scene is the
    fastest way to look machine-made."""
    if vtype == "infographic":
        return "push_in_slow"
    if vtype == "motion_graphics":
        return "pan_right"
    # rotate the move so no two neighbouring scenes repeat the same motion
    moves = ["zoom_in", "pan_left", "zoom_out", "drift_up", "pan_right", "push_in_slow"]
    return moves[index % len(moves)]


def transition_for(index, text):
    if text.rstrip().endswith("?"):
        return "fade"
    if index == 0:
        return "fade"
    return ["dissolve", "smoothleft", "wipeleft", "dissolve"][index % 4]


def description_for(text, kw, vtype):
    base = ", ".join(kw[:3]) if kw else "the subject of the sentence"
    return {
        "technology_demonstration": f"close, dynamic shot of {base} performing the action the narration describes",
        "motion_graphics": f"clean motion-graphics overlay illustrating {base}, dark background, thin accent lines",
        "infographic": f"minimal data graphic showing {base}, large numerals, dark palette, accent highlights",
        "real_world_footage": f"realistic documentary b-roll of {base}, shallow depth of field, filmic light",
    }.get(vtype, f"realistic b-roll of {base}")


def query_for(text, kw, vtype, tags=None):
    """Concrete, filmable query - stock libraries have no abstract concepts."""
    if tags:
        q = " ".join([t for t in tags if t])[:48].strip()
        if q:
            return q
    pick = kw[:2] or ["technology"]
    if vtype == "technology_demonstration" and len(pick) > 1:
        return " ".join(pick[:2])
    if len(pick) == 1:
        return f"{pick[0]} technology"
    return " ".join(pick[:2])


def audio_duration(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def silence_pauses(path, noise_db=-32, min_gap=0.22):
    """Return [(start,end)] of real pauses in the narration (ffmpeg only)."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
             "-af", f"silencedetect=noise={noise_db}dB:d={min_gap}",
             "-f", "null", "-"], capture_output=True, text=True)
        out = r.stderr
        starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", out)]
        ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", out)]
        gaps = []
        for i, s in enumerate(starts):
            e = ends[i] if i < len(ends) else None
            if e is not None:
                gaps.append((s, e))
        return gaps
    except Exception:
        return []


def _snap(t, gaps, window=0.9):
    best, bestd = t, window
    for s, e in gaps:
        mid = (s + e) / 2.0
        d = abs(mid - t)
        if d < bestd:
            best, bestd = mid, d
    return best


def build(entry, narration_path=None, duration=None, beats_timing=None,
          announce=None):
    """Build the storyboard dict for an entry and return it (also JSON-ready).

    entry: the library entry dict (narration, beats, kind, title)
    narration_path: the rendered narration mp3/wav (for real boundary snapping)
    beats_timing: optional list of per-beat durations (s) from the TTS layer
    """
    title = entry.get("title", "")
    beats = [b for b in (entry.get("beats") or []) if b.get("t")]
    if not beats:
        beats = [{"t": s} for s in _split_sentences(entry.get("narration", ""))]

    dur = duration or (audio_duration(narration_path) if narration_path else 0.0)
    if not dur:
        words = max(len(_words(entry.get("narration", ""))), 1)
        dur = words / 2.6                     # ~156 wpm documentary pace

    # ── 1: merge short beats into readable scenes (target 4.5-9 s) ──────────
    if beats_timing and len(beats_timing) == len(beats):
        weights = [max(float(x), 0.4) for x in beats_timing]
        timing_source = "tts_beats"
    else:
        weights = [max(len(_words(b["t"])), 1) for b in beats]
        timing_source = "estimated_words"

    target = 6.5
    scenes, cur, curw = [], [], 0.0
    per_sec = sum(weights) / dur if dur else 1
    for b, w in zip(beats, weights):
        cur.append((b, w))
        curw += w
        if curw / per_sec >= target:
            scenes.append(cur)
            cur, curw = [], 0.0
    if cur:
        if scenes and (curw / per_sec) < 2.2:      # avoid a 1-second stub
            scenes[-1].extend(cur)
        else:
            scenes.append(cur)

    # ── 2: timing, snapped to real pauses when we have the audio ───────────
    gaps = silence_pauses(narration_path) if narration_path else []
    if gaps:
        timing_source = "silence_snapped (" + timing_source + ")"
    total_w = sum(w for sc in scenes for _, w in sc) or 1.0
    out, t = [], 0.0
    for i, sc in enumerate(scenes):
        sw = sum(w for _, w in sc)
        seg = dur * sw / total_w
        end = dur if i == len(scenes) - 1 else t + seg
        if i < len(scenes) - 1 and gaps:
            end = _snap(end, gaps)
            end = max(end, t + 1.2)
        text = " ".join(b["t"].strip() for b, _ in sc).strip()
        tags = []
        for b, _ in sc:
            tags.extend(b.get("tags") or [])
        kw = keywords(text)
        vtype = visual_type_for(text)
        out.append({
            "scene_id": i + 1,
            "narration_text": text,
            "start_time": round(t, 3),
            "end_time": round(end, 3),
            "duration": round(end - t, 3),
            "visual_description": description_for(text, kw, vtype),
            "search_query": query_for(text, kw, vtype, tags=tags),
            "visual_type": vtype,
            "transition": transition_for(i, text),
            "motion_style": motion_for(i, vtype, text),
            "keywords": kw,
            "word_count": len(_words(text)),
            "beat_index": [j for j, (b, _) in enumerate(sc)
                           if beats[j] is b] or [0],
        })
        t = end

    sb = {
        "title": title,
        "kind": entry.get("kind", "long"),
        "narration_duration": round(dur, 3),
        "scene_count": len(out),
        "timing_source": timing_source,
        "target_scene_seconds": target,
        "scenes": out,
    }
    if announce:
        announce(f"storyboard: {len(out)} scenes / {dur/60:.1f} min "
                 f"({timing_source})")
    return sb


def save(sb, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sb, f, indent=1, ensure_ascii=False)
    return path


def validate(sb, tol=0.05):
    """Structural checks that must hold before a single frame is rendered."""
    errs = []
    if not sb.get("scenes"):
        return ["storyboard has no scenes"]
    prev_end = 0.0
    for s in sb["scenes"]:
        for k in ("scene_id", "narration_text", "start_time", "end_time",
                  "visual_description", "search_query", "visual_type",
                  "transition", "motion_style"):
            if k not in s:
                errs.append(f"scene {s.get('scene_id')}: missing {k}")
        if s["end_time"] <= s["start_time"]:
            errs.append(f"scene {s['scene_id']}: non-positive duration")
        if abs(s["start_time"] - prev_end) > tol:
            errs.append(f"scene {s['scene_id']}: gap/overlap at {s['start_time']}"
                        f" (expected {prev_end})")
        prev_end = s["end_time"]
        if not s.get("narration_text", "").strip():
            errs.append(f"scene {s['scene_id']}: empty narration")
    if sb["scenes"] and abs(sb["scenes"][-1]["end_time"]
                            - sb.get("narration_duration", 0)) > 0.35:
        errs.append("last scene does not reach the end of the narration")
    dur_list = [s["duration"] for s in sb["scenes"]]
    if len(set(round(d, 1) for d in dur_list)) == 1 and len(dur_list) > 3:
        errs.append("every scene has an identical duration (not dynamic)")
    return errs
