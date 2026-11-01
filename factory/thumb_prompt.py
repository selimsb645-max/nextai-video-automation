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
    # ── hook shaping ──────────────────────────────────────────────────────
    # Prefer the named thing a viewer can recognise: a model/product token,
    # optionally with its version number ("GENIE 4", "GPT-6.1 TERRA"), an
    # all-caps codename ("DUET", "ARGON"), or "<country/brand> AI".
    MODEL = re.findall(r"\b([A-Z][A-Za-z0-9]{2,}(?:[\s-]\d+(?:\.\d+)?)?)\b", title)
    CAPS = re.findall(r"\b([A-Z]{3,}[A-Z0-9.-]*)\b", title)
    DIGIT = re.findall(r"(\$?\d[\d.,]*\s?[KMB]?)\s+([A-Za-z]{3,})\b", title)
    PROPER = [w for w in re.findall(r"\b([A-Z][a-z]{2,})'?s?\b", title)
              if w.lower() not in STOP]

    def ok(words):
        ws = [w for w in words if w and w.lower().strip("'s") not in STOP]
        return ws if 1 <= len(ws) <= 3 else []

    VERSIONED = re.findall(r"\b([A-Z][A-Za-z]{2,})\s+(\d+(?:\.\d+)?)\b", title)
    if VERSIONED:                      # "Opus 6", "Mythos 5", "Genie 4"
        cand = ok([VERSIONED[0][0].upper(), VERSIONED[0][1]])
        if cand:
            return " ".join(cand)[:22]
    BIGCOUNT = [d for d in DIGIT
                if d[0].startswith("$") or re.search(r"[KMB]$", d[0])
                or (d[0].isdigit() and int(float(d[0])) >= 100)]
    if BIGCOUNT:                       # "89K ROBOT", "$4 TRILLION"
        cand = ok([BIGCOUNT[0][0].upper(), BIGCOUNT[0][1].upper()])
        if cand:
            return " ".join(cand)[:22]
    if CAPS:
        extra = [PROPER[0].upper()] if PROPER and PROPER[0].isalpha() else []
        cand = ok(extra + [m for m in MODEL if m in CAPS][:1])
        if cand:
            return " ".join(cand)[:22]
    big = [m for m in MODEL if re.search(r"\d", m) or len(m) >= 5]
    big.sort(key=lambda m: (0 if re.search(r"\d", m) else 1))   # "GPT-6.1 TERRA"
    if big:
        two = big[:2]
        cand = ok([w.upper() for w in two])
        if cand:
            return " ".join(cand)[:22]
    if re.search(r"\bAI\b", title) and PROPER:
        cand = ok([PROPER[0].upper(), "AI"])
        if cand:
            return " ".join(cand)[:22]
    if not scored:
        return title.upper()[:18]
    keep = sorted(sorted(scored, key=lambda x: (-x[0], x[1]))[:n], key=lambda x: x[1])
    words = [w for _, _, w in keep]
    while len(" ".join(words)) > 22 and len(words) > 1:
        words.pop()                     # never cut a word in half
    return " ".join(words)


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


# ── A-to-Z master prompt (owner 2026-11-01: "সম্পূর্ণ থাম্বনেল প্রম্পট দিবে A to Z") ──
FONT_SPEC = ("heavy condensed grotesque, Impact/Anton/American-Captain style, "
             "ALL CAPS, very tight leading, no letter-spacing on the headline, "
             "wide letter-spacing (+35%) on the small kicker line")

LAYOUT_SPEC = ("Layout: text block anchored LEFT, occupying the left 45% of the "
               "frame, vertically centred on the subject's eye-line. Subject "
               "occupies the right 55%, cropped at mid-chest, head in the upper "
               "third, looking slightly off-lens for tension. Keep a 48 px safe "
               "margin on every edge; nothing important inside the bottom-right "
               "corner (timestamp overlay) or the top-right corner on Shorts.")

QUALITY_SPEC = ("Render as a finished graphic, not a photo: photoreal base image "
                "+ graphic-design finishing, razor-sharp details, high micro-contrast, "
                "clean edges on the type, subtle film grain, no motion blur, "
                "no lens distortion, colour-graded like a Netflix documentary poster.")


def build_full(title, subject=None, kicker=None, headline=None, accent_word=None,
               descriptor=None, accent="electric cyan", background=None,
               accent_hex="#00ECFF", kind="long"):
    """The complete A-to-Z prompt the owner pastes into an image model.

    Everything is spelled out - scene, subject, light, palette, exact words,
    font, sizes, positions, margins, quality and negatives - so the output needs
    no further design work. Falls back to title-derived slots when the caller
    (the nightly agent step) does not supply story-specific ones.
    """
    base = build(title, kind)
    hook = headline or base["text_overlay"]
    subj = subject or SUBJECTS.get(base["subject_key"], SUBJECTS["human"])
    fam = _hook_family(title)
    KICK = {"warning": "THE WARNING", "launch": "JUST RELEASED",
            "money": "THE MONEY", "job": "YOUR JOB", "china_us": "THE AI RACE",
            "default": "AI NEWS"}
    brand = None
    for b in ("google", "openai", "anthropic", "nvidia", "deepseek", "microsoft",
              "meta", "tesla", "apple", "china"):
        if re.search(rf"\b{b}\b", title, re.I):
            brand = b.upper()
            break
    kick = (kicker or (f"{brand} · AI" if brand else KICK[fam])).upper()
    hw = hook.split()
    desc = (descriptor or " ".join(w for w in hw[-2:])).upper()
    if desc == hook.upper():
        desc = "WHAT COMES NEXT"
    acc = accent_word or next((w for w in reversed(hw) if re.search(r"[A-Za-z]", w)), hw[0])
    acc = acc.upper()
    scene = background or (
        "a dark cinematic environment belonging to this story: matte black "
        "surfaces, faint volumetric haze, out-of-focus bokeh lights, one large "
        "glowing screen or device supplying the practical light")

    L = []
    L.append("Create a premium YouTube thumbnail. Aspect ratio 16:9, export 1280x720. "
             "Style reference: high-end AI-news documentary channel (cinematic, "
             "teal-and-amber, dark, glossy, zero clutter).")
    L.append("")
    L.append(f"1) SCENE. {scene[0].upper()}{scene[1:]}. Deep navy-to-black gradient, atmosphere near-black "
             f"so the type pops. Single accent hue: {accent} ({accent_hex}).")
    L.append("")
    L.append(f"2) SUBJECT. {subj[0].upper()}{subj[1:]}. Expressive and readable at 320 px wide: clear eyes, "
             f"defined jawline, one strong emotion (alarm, awe, or defiance, never "
             f"neutral). Lit from camera-left with a hard key, then a thin {accent} "
             f"rim light tracing the shoulder and hair from behind.")
    L.append("")
    L.append("3) TYPE - render these words exactly, spelled correctly:")
    L.append(f'   top line (kicker, small): "{kick}"')
    L.append(f'   headline (huge, 2-4 words): "{hook}"')
    L.append(f'   signature word in {accent}: "{acc}", the rest of the headline pure '
             f'white (#FFFFFF)')
    L.append(f'   bottom line (descriptor, small): "{desc}"')
    L.append(f"   {FONT_SPEC}. Headline height about 22% of frame height, kicker about "
             f"5%, descriptor about 4.5%. Hard 6 px black outline plus a soft 30% "
             f"black drop shadow behind all type; white stays 100% white.")
    L.append("")
    L.append(f"4) {LAYOUT_SPEC}")
    L.append("")
    L.append(f"5) {QUALITY_SPEC}")
    L.append("")
    L.append("6) NEVER include: garbled or misspelled text, gibberish letters, random "
             "extra words, watermark, signature, stock watermark, extra fingers, "
             "distorted hands, plastic skin, cartoon shading, oversaturated colour, "
             "cluttered background, more than two people, emoji, flame or explosion "
             "cliches, fake YouTube UI.")
    L.append("")
    L.append("7) The ONLY text in the image is the three lines specified in step 3, "
             "spelled exactly as written.")
    prompt = "\n".join(L)

    fallback = (
        f"Create a premium YouTube thumbnail BACKGROUND, 16:9, 1280x720, photoreal, "
        f"cinematic. {subj}. {scene}. Deep navy-to-black gradient, {accent} "
        f"({accent_hex}) rim light, volumetric haze, {QUALITY_SPEC} "
        f"Subject on the RIGHT 55%, left 45% kept dark and empty for typography. "
        f"Absolutely no text, numbers, logos or watermarks in the image. "
        f"Negative: {NEGATIVE}.")

    steps = [
        "১. উপরের A-to-Z প্রম্পটটা Gemini / GPT-image / Midjourney / Flux-এ পেস্ট করুন, 16:9 ও 1280x720।",
        f"২. মডেল বানান ভুল করলে ফলব্যাক প্রম্পটে শুধু ছবি বানান, তারপর Canva-তে লেখা বসান: "
        f'kicker "{kick}", headline "{hook}" (শেষ শব্দ {accent_hex}), নিচে "{desc}"।',
        "৩. JPG quality 85-92, ফাইল ২ MB-এর নিচে।",
        "৪. YouTube Studio → ভিডিও → Thumbnail → Upload; মোবাইলে ৩২০ px-এ কেমন দেখায় মিলিয়ে নিন।",
    ]
    return {
        "title": title, "kind": kind, "headline": hook, "kicker": kick,
        "accent_word": acc, "descriptor": desc, "accent_hex": accent_hex,
        "full_prompt": prompt, "image_prompt": fallback, "negative": NEGATIVE,
        "steps": steps,
    }


def format_full_message(entry, f):
    t, v = entry.get("title", ""), entry.get("videoId", "")
    url = entry.get("url") or (f"https://www.youtube.com/watch?v={v}" if v else "")
    head = f"🎬 *{t}*" + (f"\n{url}" if url else "")
    steps = "\n".join(f"  {x}" for x in f["steps"])
    return (
        head + "\n\n*A-to-Z প্রম্পট (কপি করে বসান):*\n"
        f"```{f['full_prompt']}```\n"
        f"*হেডলাইন:* {f['headline']}  |  *কিকার:* {f['kicker']}  |  "
        f"*অ্যাকসেন্ট শব্দ:* {f['accent_word']}\n"
        f"*ফলব্যাক (শুধু ছবি, লেখা ছাড়া):*\n```{f['image_prompt']}```\n"
        f"*কীভাবে বসাবেন:*\n{steps}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--kind", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--title", default=None, help="build from a title directly")
    ap.add_argument("--full", action="store_true", help="A-to-Z master prompt")
    a = ap.parse_args()
    if a.title and a.full:
        f = build_full(a.title, kind=a.kind or "long")
        print(json.dumps(f, indent=1, ensure_ascii=False) if a.json
              else format_full_message({"title": a.title}, f))
        return
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
    if a.full:
        f = build_full(e["title"], kind=e.get("kind", "long"))
        f["videoId"] = e.get("videoId")
        f["url"] = e.get("url")
        f["found"] = True
        print(json.dumps(f, indent=1, ensure_ascii=False) if a.json
              else format_full_message(e, f))
        return
    p = build(e["title"], e.get("kind", "long"))
    p["videoId"] = e.get("videoId")
    p["url"] = e.get("url")
    print(json.dumps({**p, "found": True}, indent=1, ensure_ascii=False) if a.json
          else format_message(e, p))


if __name__ == "__main__":
    main()
