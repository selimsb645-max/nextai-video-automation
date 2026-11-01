#!/usr/bin/env python3
"""Premium thumbnail PROMPTS for the owner's image model.

Owner decision 2026-11-01: Solas no longer designs the thumbnail. After each
upload Solas delivers a ready-to-paste, premium thumbnail prompt written in the
visual language of @airevolutionx (cinematic AI-documentary keyart: dark teal
stage, glowing accents, photoreal subject, dramatic rim light, one accent
colour, big clean type area).

Output has three parts so the owner can use any tool:
  1. IMAGE_PROMPT   - paste into Midjourney / Flux / Imagen / Gemini image
  2. TEXT_OVERLAY   - the 2-4 words to set on top (Canva, Photopea, CapCut)
  3. ALL_IN_ONE     - single prompt for models that render text well

Usage:
  python3 factory/thumb_prompt.py --date 2026-11-01 --kind long
  python3 factory/thumb_prompt.py --today
  python3 factory/thumb_prompt.py --today --json
"""
import argparse
import datetime as dt
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "published_log.json")

W = "1280x720"

STYLE = ("cinematic AI-documentary keyart, photorealistic, shot on 50mm f/1.8, "
         "dramatic rim lighting from behind, subject lit from camera-left, "
         "deep navy-to-black gradient background with glowing cyan and amber "
         "accents, volumetric haze, subtle lens flare, floating holographic UI "
         "fragments, ultra sharp subject, shallow depth of field, 16:9, "
         "high dynamic range, magazine cover grade")

NEGATIVE = ("text, watermark, logo, signature, distorted hands, extra fingers, "
            "cartoon, plastic skin, oversaturated, low resolution, jpeg artifacts, "
            "cluttered background, more than two subjects")

SUBJECTS = {
    "robot": "a sleek white humanoid robot, head turned slightly toward camera",
    "chip": "a glowing silicon AI chip on a dark circuit board, macro detail",
    "phone": "a premium smartphone floating upright with a glowing screen",
    "brain": "a translucent holographic human brain made of light filaments",
    "data": "an endless dark data-centre aisle with pulsing blue server lights",
    "city": "a futuristic skyline at night with violet and cyan window lights",
    "office": "a modern glass office at dusk, one desk lit",
    "car": "a driverless car on a wet city street at night, headlights on",
    "human": "a single person in a dark room face-lit by a screen",
    "space": "a satellite above a glowing blue Earth horizon",
}

CUES = [
    (r"\b(robot|humanoid|android|humanoid)\b", "robot"),
    (r"\b(chip|gpu|silicon|semiconductor|nvidia|tsmc)\b", "chip"),
    (r"\b(iphone|phone|smartphone|galaxy|pixel)\b", "phone"),
    (r"\b(brain|mind|conscious|neuron|think)\b", "brain"),
    (r"\b(data ?cent(er|re)|server|cloud|cpu|compute)\b", "data"),
    (r"\b(city|urban|traffic|street)\b", "city"),
    (r"\b(job|worker|work|office|hire|layoff|employee)\b", "office"),
    (r"\b(car|tesla|drive|driverless|autonomous|waymo)\b", "car"),
    (r"\b(satellite|space|orbit|rocket|moon)\b", "space"),
    (r"\b(warn|risk|danger|threat|ban|shut|kill|fear|panic)\b", "human"),
]

HOOK_WORDS = {
    "warning": ["THE WARNING", "GAME OVER", "NO ONE SAW IT"],
    "launch": ["JUST DROPPED", "IT'S HERE", "NEW ERA"],
    "money": ["$1 TRILLION", "THE MONEY", "WHO PAYS"],
    "job": ["YOUR JOB", "GONE IN 2 YEARS", "SOON OBSOLETE"],
    "china_us": ["CHINA vs USA", "THE RACE", "WHO WINS"],
    "default": ["IT'S OVER", "THE TRUTH", "TOO LATE"],
}


def _subject_for(title, subject=""):
    t = f"{title} {subject}".lower()
    for pat, key in CUES:
        if re.search(pat, t):
            return key
    return "human"


def _hook_family(title):
    t = title.lower()
    if re.search(r"\b(warn|risk|danger|threat|ban|shut|kill|fear|panic|obsolete)\b", t):
        return "warning"
    if re.search(r"\b(launch|launched|unveil|introduc|release|new)\b", t):
        return "launch"
    if re.search(r"\b(\$|billion|trillion|money|cost|price|revenue|fund)\b", t):
        return "money"
    if re.search(r"\b(job|work|hire|layoff|employ|salary|career)\b", t):
        return "job"
    if re.search(r"\b(china|chinese|us\b|america|beijing|washington)\b", t):
        return "china_us"
    return "default"


STOP = set("""a an the and or but for with from that this these those its his her
their our your my is are was were be been being can could will would should may
might must just now not no more most very into onto out up down over under about
after before while when where who whom which what how why all any some such than
then there here they them we you he she it i of in on at to as by do does did
done have has had new news""".split())


def short_text(title, n=3):
    """Hook words for the image. Deterministic scaffolding; the nightly agent
    step rewrites it when a sharper 2-4 word hook exists in the title."""
    toks = re.findall(r"\$?[A-Za-z0-9][A-Za-z0-9$.'-]*", title)
    scored = []
    for i, w in enumerate(toks):
        lw = w.lower().strip(".,'")
        if lw in STOP or len(lw) < 2:
            continue
        score = 0
        if re.search(r"\d", w):
            score += 3
        if w[:1].isupper():
            score += 1
        if len(lw) >= 5:
            score += 1
        if i >= len(toks) - 4:
            score += 1
        scored.append((score, i, w.upper().strip(".,'")))
    if not scored:
        return title.upper()[:18]
    keep = sorted(sorted(scored, key=lambda x: (-x[0], x[1]))[:n], key=lambda x: x[1])
    return " ".join(w for _, _, w in keep)[:26]


def build(title, kind="long", brand=None):
    key = _subject_for(title)
    subj = SUBJECTS[key]
    hook = short_text(title)
    fam = _hook_family(title)
    accent = "electric cyan" if fam != "warning" else "warning red"
    image_prompt = (
        f"YouTube thumbnail, {W}, 16:9 composition. {subj.capitalize()}, "
        f"centre-right of frame, eyes/head toward the viewer. Behind it: "
        f"{STYLE}. Single accent colour: {accent}. Leave the LEFT THIRD as a "
        f"dark, clean, low-detail area (it will carry big bold type). "
        f"Mood: {fam.replace('_', ' ')} documentary, urgent but premium, "
        f"no clutter, no text of any kind in the image."
    )
    if brand is None:
        all_in_one = (image_prompt + ' Add bold condensed uppercase type on the '
                      'left third: "' + hook + '" in white with one word in '
                      + accent + ', tight leading, heavy impact-style sans-serif, '
                      'plus a thin white letterspaced kicker above it. Keep all '
                      'text inside the safe area, perfectly legible at 320px wide.')
    else:
        all_in_one = (image_prompt + ' Add bold condensed uppercase type on the '
                      'left third: "' + brand + '" wordmark small on top, then "'
                      + hook + '" huge in white with one word in ' + accent
                      + ', heavy impact sans-serif, plus a thin letterspaced '
                      'descriptor line under it. Legible at 320px wide, inside '
                      'the safe area.')
    return {
        "title": title,
        "kind": kind,
        "subject_key": key,
        "text_overlay": hook,
        "image_prompt": image_prompt,
        "text_spec": (f'Headline: "{hook}" - bold condensed caps, one word in '
                      f"{accent}. Add a 3-5 word descriptor line under it in "
                      f"thin letterspaced white caps. Type area: left third, "
                      f"inside a 40px safe margin."),
        "all_in_one": all_in_one,
        "negative": NEGATIVE,
    }


def latest(date=None, kind=None):
    """Newest published entry, optionally for a specific date / kind."""
    if not os.path.exists(LOG):
        return None
    rows = json.load(open(LOG))
    if not isinstance(rows, list):
        rows = rows.get("entries", [])
    if date:
        rows = [r for r in rows
                if str(r.get("uploaded_at", "")).startswith(date)
                or str(r.get("scheduled_for", "")).startswith(date)]
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    rows = [r for r in rows if r.get("videoId")]
    return rows[-1] if rows else None


def format_message(entry, p):
    """Owner-facing WhatsApp message: one main prompt + the text to set on it."""
    t, v = entry.get("title", ""), entry.get("videoId", "")
    url = entry.get("url") or (f"https://www.youtube.com/watch?v={v}" if v else "")
    head = f"🎬 *{t}*"
    if url:
        head += f"\n{url}"
    return (
        head + "\n\n"
        "*প্রম্পট (ছবি, লেখা ছাড়া — Midjourney / Flux / Gemini image):*\n"
        f"```{p['image_prompt']}```\n"
        f"*উপরে বসানোর লেখা:* `{p['text_overlay']}`\n"
        f"*টাইপোগ্রাফি:* {p['text_spec']}\n"
        f"*Negative:* {p['negative']}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--kind", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--title", default=None, help="build from a title directly")
    a = ap.parse_args()
    if a.title:
        p = build(a.title, a.kind or "long")
        print(json.dumps(p, indent=1, ensure_ascii=False) if a.json
              else format_message({"title": a.title}, p))
        return
    date = a.date or (dt.datetime.now(dt.timezone(dt.timedelta(hours=6)))
                      .date().isoformat() if a.today else None)
    e = latest(date, a.kind)
    if not e:
        print(json.dumps({"found": False, "date": date}) if a.json
              else "no upload found for that date")
        return
    p = build(e["title"], e.get("kind", "long"))
    p["videoId"] = e.get("videoId")
    p["url"] = e.get("url")
    print(json.dumps({**p, "found": True}, indent=1, ensure_ascii=False) if a.json
          else format_message(e, p))


if __name__ == "__main__":
    main()
