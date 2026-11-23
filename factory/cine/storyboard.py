"""Phase 2 - AI storyboard engine.

Turns an approved script + narration into a scene-by-scene storyboard:

    scene_id, narration_text, start_time, end_time, visual_description,
    search_query, visual_type, transition, motion_style

Timing strategy (honest, in this order):
 1. MEASURED per-beat TTS spans (beat_spans, from factory's beats_timing.json:
    the exact sample-count boundaries of each synthesized beat, rescaled onto
    the final narration file's duration). Scene boundaries ARE the moments
    the sentences are actually spoken - no estimation anywhere in the chain.
 2. otherwise `ffmpeg silencedetect` on the real narration: scene boundaries
    are snapped to the nearest actual pause, which is far closer to the voice
    than a naive word split;
 3. word-count weighting inside each scene for caption timing.
The report records which strategy was used as `timing_source`, so nothing is
presented as measured when it was only estimated.

HOOK RULE (owner, 2026-11-23, after rejecting demo #2): in the FIRST 30
SECONDS the visual changes about every second and every visual shows exactly
what the script is saying at that moment. So hook beats are never merged:
one scene per sentence, and any hook sentence longer than HOOK_MAX_S is
split at clause boundaries (commas / semicolons / dashes) into sub-scenes,
each with its own keywords, query and visual - a new visual for every new
point in the narration.
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


HOOK_SECONDS = 30.0        # owner rule: the hook window
HOOK_MAX_S = 2.4           # longest a single hook visual may stay on screen
HOOK_MIN_S = 0.7           # never split a clause shorter than this


_PREP = ("of", "for", "with", "from", "in", "on", "at", "to", "by")


def _split_long(part, max_words=8):
    """Last-resort split of one over-long clause at the preposition nearest
    its middle (a breath-point a viewer can follow), recursively."""
    words = part.split()
    if len(words) <= max_words:
        return [part]
    mid = len(words) // 2
    cut = None
    for d in range(0, 5):
        for j in (mid + d, mid - d):
            if 2 <= j < len(words) - 1 and words[j].lower() in _PREP:
                cut = j
                break
        if cut:
            break
    cut = cut or mid
    return (_split_long(" ".join(words[:cut]), max_words) +
            _split_long(" ".join(words[cut:]), max_words))


def _clauses(text):
    """Split a sentence at clause boundaries a viewer can follow:
    punctuation first, then conjunctions. Over-splitting is harmless - the
    hook packer greedily re-joins pieces until the next one would push the
    sub-scene past HOOK_MAX_S, so a cut only lands where timing needs one."""
    parts = re.split(r"(?<=[,;:])\s+|\s+—\s+|\s+--\s+", text or "")
    out = []
    for p in parts:
        for q in re.split(r"\s+(?:and|but|while|so)\s+", p):
            out.extend(_split_long(q.strip()))
    return [p.strip(" ") for p in out if p and p.strip()]


def _interp(texts, start, end):
    """Give each text a sub-span of [start, end] weighted by word count.
    The outer anchors are exact; only the split INSIDE one spoken sentence
    is interpolated, so error is bounded by a fraction of that sentence."""
    ws = [max(len(_words(t)), 1) for t in texts]
    tot = sum(ws) or 1
    out, t = [], start
    for i, (tx, w) in enumerate(zip(texts, ws)):
        e = end if i == len(texts) - 1 else t + (end - start) * w / tot
        out.append((tx, t, e))
        t = e
    return out


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
          beat_spans=None, announce=None):
    """Build the storyboard dict for an entry and return it (also JSON-ready).

    entry: the library entry dict (narration, beats, kind, title)
    narration_path: the rendered narration mp3/wav (for real boundary snapping)
    beats_timing: legacy list of per-beat durations (s) from the TTS layer
    beat_spans: measured per-beat {"start","end"} spans (factory's
        beats_timing.json) - when present and aligned with the beats, scene
        boundaries are the real spoken boundaries, not estimates.
    """
    title = entry.get("title", "")
    beats = [b for b in (entry.get("beats") or []) if b.get("t")]
    if not beats:
        beats = [{"t": s} for s in _split_sentences(entry.get("narration", ""))]

    dur = duration or (audio_duration(narration_path) if narration_path else 0.0)
    if not dur:
        words = max(len(_words(entry.get("narration", ""))), 1)
        dur = words / 2.6                     # ~156 wpm documentary pace

    # ── 1: expand beats into sentence units with times ─────────────────────
    # A beat may carry several sentences; each sentence is the smallest unit
    # a visual can honestly illustrate.
    measured = False
    spans = None
    if beat_spans and len(beat_spans) == len(beats):
        try:
            raw_end = float(beat_spans[-1]["end"])
            if raw_end > 0:
                scale = dur / raw_end        # map wav-domain spans onto the
                spans = [(float(s["start"]) * scale, float(s["end"]) * scale)
                         for s in beat_spans]  # final file's real duration
                measured = True
        except Exception:
            spans = None
    if not measured and beats_timing and len(beats_timing) == len(beats):
        # legacy durations-only path: lay the beats end to end proportionally
        tot = sum(max(float(x), 0.4) for x in beats_timing) or 1.0
        spans, t = [], 0.0
        for x in beats_timing:
            seg = dur * max(float(x), 0.4) / tot
            spans.append((t, t + seg))
            t += seg
        measured = True

    units = []                     # {t, tags, beat, start, end, hook}
    if measured:
        timing_source = "tts_measured"
        for bi, b in enumerate(beats):
            bs, be = spans[bi]
            sents = _split_sentences(b["t"]) or [b["t"]]
            for tx, s, e in _interp(sents, bs, be):
                units.append({"t": tx, "tags": b.get("tags") or [],
                              "beat": bi, "start": s, "end": e})
    else:
        timing_source = "estimated_words"
        tot_w = sum(max(len(_words(b["t"])), 1) for b in beats) or 1
        t = 0.0
        for bi, b in enumerate(beats):
            seg = dur * max(len(_words(b["t"])), 1) / tot_w
            sents = _split_sentences(b["t"]) or [b["t"]]
            for tx, s, e in _interp(sents, t, t + seg):
                units.append({"t": tx, "tags": b.get("tags") or [],
                              "beat": bi, "start": s, "end": e})
            t += seg

    # ── 2: the hook - one visual per spoken point, ~1s granularity ─────────
    split_units = []
    for u in units:
        u["hook"] = u["start"] < HOOK_SECONDS
        if u["hook"] and (u["end"] - u["start"]) > HOOK_MAX_S:
            cls = _clauses(u["t"])
            if len(cls) > 1:
                # greedily pack clauses into <=HOOK_MAX_S sub-units
                chunks, cur = [], []
                spans_c = _interp(cls, u["start"], u["end"])
                for (tx, s, e) in spans_c:
                    if cur and (e - cur[0][1]) > HOOK_MAX_S:
                        chunks.append(cur)
                        cur = []
                    cur.append((tx, s, e))
                if cur:
                    chunks.append(cur)
                for ch in chunks:
                    split_units.append({
                        "t": " ".join(x[0] for x in ch).strip(),
                        "tags": u["tags"], "beat": u["beat"],
                        "start": ch[0][1], "end": ch[-1][2], "hook": True})
                continue
        split_units.append(u)
    units = split_units

    # ── 3: assemble scenes - hook units stand alone, the rest merge ────────
    target = 6.5
    groups, cur = [], []
    for u in units:
        if u["hook"]:
            if cur:
                groups.append(cur)
                cur = []
            groups.append([u])
        else:
            cur.append(u)
            if (cur[-1]["end"] - cur[0]["start"]) >= target:
                groups.append(cur)
                cur = []
    if cur:
        if groups and not groups[-1][0]["hook"] and \
                (cur[-1]["end"] - cur[0]["start"]) < 2.2:
            groups[-1].extend(cur)          # avoid a 1-second stub
        else:
            groups.append(cur)

    # boundaries: scene end = next scene's start (a scene holds through the
    # breath pause after its last sentence, exactly like a human edit)
    bounds = [g[0]["start"] for g in groups] + [dur]
    bounds[0] = 0.0

    # estimated path only: snap internal boundaries to real pauses. Measured
    # spans are NEVER snapped - moving them would break the sync they give.
    gaps = []
    if not measured and narration_path:
        gaps = silence_pauses(narration_path)
        if gaps:
            timing_source = "silence_snapped (" + timing_source + ")"
            for i in range(1, len(bounds) - 1):
                win = 0.45 if groups[i][0]["hook"] else 0.9
                nb = _snap(bounds[i], gaps, window=win)
                lo = bounds[i - 1] + (HOOK_MIN_S if groups[i][0]["hook"]
                                      else 1.2)
                hi = bounds[i + 1] - 0.7 if i + 1 < len(bounds) else nb
                bounds[i] = min(max(nb, lo), max(hi, lo))

    out = []
    for i, g in enumerate(groups):
        t, end = bounds[i], bounds[i + 1]
        # per-unit segments with boundary-adjusted times, so caption cues can
        # anchor to each sentence's own measured span even inside a merged
        # scene (without this, a merged scene's later beats were placed by
        # character weight and could drift ~2 s off the voice - demo #3
        # verification, 2026-11-23)
        segments = []
        for j, u in enumerate(g):
            s0 = t if j == 0 else u["start"]
            s1 = g[j + 1]["start"] if j + 1 < len(g) else end
            segments.append({"t": u["t"], "start": round(s0, 3),
                             "end": round(s1, 3)})
        text = " ".join(u["t"].strip() for u in g).strip()
        tags = []
        for u in g:
            tags.extend(u["tags"])
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
            "beat_index": sorted({u["beat"] for u in g}),
            "hook": bool(g[0]["hook"]),
            "sync": "measured" if measured else "estimated",
            "segments": segments,
        })

    sb = {
        "title": title,
        "kind": entry.get("kind", "long"),
        "narration_duration": round(dur, 3),
        "scene_count": len(out),
        "timing_source": timing_source,
        "target_scene_seconds": target,
        "hook_seconds": HOOK_SECONDS,
        "hook_scene_count": sum(1 for s in out if s["hook"]),
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
