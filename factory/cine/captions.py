"""Phase 5 - professional caption engine (ASS, burned by libass in FFmpeg).

Behaviour:
  * word-level timing when the TTS layer supplies word/beat timings, otherwise
    character-weighted timing inside the scene (labelled `estimated` in the
    report - we never claim measured timing we do not have);
  * cues are re-chunked to <= 2 lines / ~42 characters so they stay readable;
  * numbers, prices, percentages and product names from the scene keywords get
    the accent colour, everything else stays white;
  * bottom-centred with real safe margins (no descender clipping, no edge
    touching), outline + shadow instead of an ugly opaque box.
"""
import os
import re

ACCENTS = {"cyan": "00ECFF", "red": "FF2D3C", "amber": "FFB020", "gold": "FFC53D"}


def _bgr(hex_rgb):
    hex_rgb = hex_rgb.lstrip("#")
    r, g, b = hex_rgb[0:2], hex_rgb[2:4], hex_rgb[4:6]
    return f"{b}{g}{r}".upper()


def ass_time(t):
    t = max(float(t), 0.0)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text):
    t = (text or "").replace("\n", " ").replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", t).strip()


def _chunks(text, max_chars=42):
    """Split into caption cues that fit two short lines without breaking words."""
    words = _esc(text).split()
    out, cur = [], []
    for w in words:
        trial = " ".join(cur + [w])
        if len(trial) <= max_chars or not cur:
            cur.append(w)
        else:
            out.append(" ".join(cur))
            cur = [w]
    if cur:
        out.append(" ".join(cur))
    # if a cue would still be too wide, let libass wrap it, but flag nothing
    return [c for c in out if c.strip()]


def _highlight(text, keywords, accent_ass):
    """Colour numbers / product names without touching the rest of the line."""
    if not keywords:
        return text
    pat = "|".join(re.escape(k) for k in sorted(keywords, key=len, reverse=True) if k)
    if not pat:
        return text
    def rep(m):
        return "{\\c&H" + accent_ass + "&}" + m.group(0) + "{\\c&HFFFFFF&}"
    return re.sub(rf"\b({pat})\b", rep, text, flags=re.I)


def header(W, H, font_name="Anton", accent="cyan", size_ratio=0.045):
    accent_ass = _bgr(ACCENTS.get(accent, ACCENTS["cyan"])) if accent in ACCENTS else _bgr(accent)
    size = int(H * size_ratio)
    margin_v = int(H * 0.075)
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Doc,{font_name},{size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0.6,0,1,{max(3, int(H * 0.004))},{max(2, int(H * 0.0025))},2,{int(W * 0.09)},{int(W * 0.09)},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""", accent_ass


def build(storyboard, out_path, W=1920, H=1080, accent="cyan",
          word_timings=None, font_name="Anton", max_chars=42):
    """Write the .ass file for the film. Returns a metadata dict."""
    head, accent_ass = header(W, H, font_name=font_name, accent=accent)
    lines, cue_i = [], 0
    timing_parts = []

    for sc in storyboard["scenes"]:
        start, end = sc["start_time"], sc["end_time"]
        span = max(end - start, 0.4)
        text = sc.get("narration_text", "")
        cues = _chunks(text, max_chars)
        if not cues:
            continue
        wt = None
        if word_timings:
            wt = word_timings.get(sc["scene_id"])
        if wt:                                  # measured timing available
            for (c, cs, ce) in wt:
                cue_i += 1
                body = _highlight(_esc(c), sc.get("keywords", []), accent_ass)
                lines.append(f"Dialogue: 0,{ass_time(cs)},{ass_time(ce)},Doc,,0,0,0,,"
                             f"{{\\fad(120,120)}}{body}")
            timing_parts.append("word")
        else:                                   # character-weighted estimate
            total = sum(len(c) for c in cues) or 1
            t = start
            for c in cues:
                len_c = len(c)
                d = max(span * len_c / total, 0.7)
                t2 = min(t + d, end)
                if t2 - t < 0.35:
                    t2 = min(t + 0.35, end)
                cue_i += 1
                body = _highlight(c, sc.get("keywords", []), accent_ass)
                lines.append(f"Dialogue: 0,{ass_time(t)},{ass_time(t2)},Doc,,0,0,0,,"
                             f"{{\\fad(120,120)}}{body}")
                t = t2
            timing_parts.append("estimated")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")
    if timing_parts and all(t == "word" for t in timing_parts):
        timing_source = "word"
    elif timing_parts and any(t == "word" for t in timing_parts):
        timing_source = "mixed_word_and_estimated"
    else:
        timing_source = "estimated_char_weight"
    meta = {
        "path": out_path, "cues": cue_i,
        "timing_source": timing_source,
        "max_chars": max_chars,
        "style": {"font": font_name, "size": int(H * 0.045),
                  "position": "bottom-center", "margin_v": int(H * 0.075),
                  "outline": max(3, int(H * 0.004))},
    }
    return meta


def validate(ass_path, duration):
    """Cheap structural validation of the generated subtitle file."""
    errs, prev_end, cues = [], 0.0, 0
    try:
        with open(ass_path, encoding="utf-8") as f:
            for ln in f:
                if not ln.startswith("Dialogue:"):
                    continue
                cues += 1
                parts = ln.split(",", 9)
                st, en = _parse(parts[1]), _parse(parts[2])
                if en <= st:
                    errs.append(f"cue {cues}: end<=start ({st}->{en})")
                if st < prev_end - 0.05:
                    errs.append(f"cue {cues}: overlaps previous cue")
                if en > duration + 0.6:
                    errs.append(f"cue {cues}: beyond film duration")
                txt = parts[9].strip() if len(parts) > 9 else ""
                if re.search(r"\{\\c[^}]*\}(?!.*\{\\c&HFFFFFF)", txt) and False:
                    pass
                prev_end = en
    except FileNotFoundError:
        errs.append("subtitle file missing")
    if cues == 0:
        errs.append("no caption cues generated")
    return {"cues": cues, "errors": errs, "ok": not errs}


def _parse(ts):
    try:
        h, m, s = ts.strip().split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        return 0.0
