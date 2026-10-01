#!/usr/bin/env python3
"""Content Factory — fully automated nightly video pipeline.
Usage:
  python3 factory.py --next           # produce the next unused library entry
  python3 factory.py --id twinkle_star  # produce a specific entry
Zero-cost stack: Pollinations (images) + Edge-TTS (voice) + ffmpeg (render) + YouTube resumable upload.
"""
import json, os, re, sys, time, subprocess, urllib.parse, urllib.request
import datetime as _dt
from zoneinfo import ZoneInfo


BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
LIB = json.load(open(os.path.join(BASE, "library.json")))
STATE_F = os.path.join(BASE, "state.json")
TOKEN_F = os.path.join(ROOT, "yt-auth", "token_nextai.json")
def next_bd_slot(kind="long", now=None):
    """Select an unfilled owner-approved BD slot 8-10h ahead, fail closed."""
    cfg = json.load(open(os.path.join(BASE, "content_policy.json")))["schedules"]
    bd = ZoneInfo(cfg["timezone"])
    now = (now or _dt.datetime.now(_dt.timezone.utc)).astimezone(bd)
    reserved = set()
    log_path = os.path.join(BASE, "published_log.json")
    if os.path.exists(log_path):
        for row in json.load(open(log_path)):
            if row.get("kind") == kind and row.get("scheduled_for"):
                reserved.add(_dt.datetime.fromisoformat(row["scheduled_for"].replace("Z", "+00:00")))
    for day in range(3):
        for hhmm in sorted(cfg["slots"][kind]):
            hh, mm = map(int, hhmm.split(":"))
            candidate = (now + _dt.timedelta(days=day)).replace(hour=hh, minute=mm, second=0, microsecond=0)
            if kind == "long" and hhmm == "19:30" and candidate.date().isoformat() < cfg["first_new_evening_long_date"]:
                continue  # Oct 1 existing 18:30 upload is preserved, no extra evening Long.
            gap = (candidate - now).total_seconds() / 3600
            if cfg["lead_hours_min"] <= gap <= cfg["lead_hours_max"] and candidate not in reserved:
                return candidate.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), candidate
    raise SystemExit("SCHEDULE_WINDOW_MISSED: no unfilled " + kind + " BD slot 8-10 hours ahead; preserve rendered file, never immediate-publish")


def next_et_slot(min_gap_hours=8, kind="long", now=None):
    """Legacy CLI compatibility; owner BD schedule supersedes ET-fixed slots."""
    return next_bd_slot(kind, now)


def get_token():
    """Load token file; mint a fresh access token headlessly if expired/missing."""
    tok = json.load(open(TOKEN_F)) if os.path.exists(TOKEN_F) else {}
    now = int(time.time())
    if tok.get("access_token") and tok.get("expires_at", 0) > now + 120:
        return tok
    if not (tok.get("refresh_token") and tok.get("client_id") and tok.get("client_secret")):
        raise SystemExit("TOKEN_MISSING_NO_REFRESH")
    body = urllib.parse.urlencode({
        "client_id": tok["client_id"], "client_secret": tok["client_secret"],
        "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read().decode())
    tok["access_token"] = out["access_token"]
    tok["expires_at"] = now + int(out.get("expires_in", 3599))
    tok["minted"] = time.strftime("%Y-%m-%dT%H:%M:%S+06:00")
    json.dump(tok, open(TOKEN_F, "w"), indent=1)
    print("token: minted headlessly (own OAuth client)", flush=True)
    return tok

RUNS = os.path.join(BASE, "runs")
os.makedirs(RUNS, exist_ok=True)


def load_state():
    if os.path.exists(STATE_F):
        return json.load(open(STATE_F))
    return {"done": {}}


def save_state(st):
    json.dump(st, open(STATE_F, "w"), indent=1)


def content_eligible(e):
    """Fail closed for future production and upload under owner scope rules."""
    policy_path = os.path.join(BASE, "content_policy.json")
    policy = json.load(open(policy_path))
    return (e.get("content_policy_version") == policy["version"]
            and e.get("content_pillar") in policy["allowed_pillars"]
            and e.get("scope_reviewed") is True
            and isinstance(e.get("verified_sources"), list)
            and bool(e["verified_sources"])
            and bool(e.get("demand_evidence"))
            and not e.get("recycled_from"))


def pick_entry(eid, kind="long"):
    st = load_state()
    if eid:
        for e in LIB["entries"]:
            if e["id"] == eid:
                if not content_eligible(e):
                    raise SystemExit("CONTENT_SCOPE_BLOCKED: " + eid)
                return e
        raise SystemExit(f"no library entry with id {eid}")
    for e in LIB["entries"]:
        if e.get("kind", "long") != kind:
            continue
        if e["id"] not in st["done"] and content_eligible(e):
            return e
    raise SystemExit("NO_ELIGIBLE_CONTENT: top up verified " + kind + " entries within content_policy.json; do not use legacy out-of-scope stories")


FOOTAGE = os.path.join(BASE, "footage")
KW2CAT = {
    "lab": ["microscope", "scientist"], "laboratory": ["microscope", "scientist"],
    "microscope": ["microscope"], "experiment": ["scientist", "microscope"],
    "scientist": ["scientist"], "research": ["scientist", "microscope"],
    "dna": ["dna"], "gene": ["dna"], "genetic": ["dna"],
    "protein": ["protein", "dna"], "molecule": ["protein", "dna"], "cell": ["microscope", "dna"],
    "bacteria": ["microscope"], "antibiotic": ["pills", "microscope"], "drug": ["pills"],
    "medicine": ["pills", "doctor"], "pill": ["pills"], "cure": ["pills", "doctor"],
    "hospital": ["doctor"], "doctor": ["doctor"], "patient": ["doctor"], "heart": ["heart"],
    "health": ["heart", "doctor"], "disease": ["microscope", "doctor"],
    "ai": ["ai", "network"], "artificial": ["ai", "network"], "algorithm": ["code", "ai"],
    "model": ["ai", "datacenter"], "neural": ["network", "ai"], "network": ["network"],
    "data": ["datacenter", "code"], "computer": ["code", "chip"], "code": ["code"],
    "software": ["code"], "screen": ["code"], "chip": ["chip"], "circuit": ["chip"],
    "cpu": ["chip", "datacenter"], "server": ["datacenter"], "internet": ["datacenter", "network"],
    "robot": ["robot"], "machine": ["robot", "chip"], "walk": ["walk"], "walking": ["walk"],
    "car": ["car"], "drive": ["car"], "driving": ["car"], "vehicle": ["car"], "road": ["car", "city"],
    "space": ["space", "planet"], "earth": ["space"], "planet": ["planet"], "galaxy": ["planet"],
    "star": ["planet"], "universe": ["planet", "space"], "satellite": ["space"],
    "city": ["city"], "night": ["city"], "world": ["city", "space"],
    "ocean": ["ocean"], "sea": ["ocean"], "water": ["ocean"],
    "brain": ["ai", "network"], "mind": ["ai"], "future": ["city", "space"],
    "startup": ["city", "code"], "money": ["city"], "news": ["city"],
}
GENERIC_ROT = ["ai", "network", "code", "city", "space", "datacenter"]


def load_footage():
    return json.load(open(os.path.join(FOOTAGE, "index.json")))


def cats_for_text(text):
    words = re.findall(r"[a-z]+", (text or "").lower())
    cats = []
    for w in words:
        for c in KW2CAT.get(w, []):
            if c not in cats:
                cats.append(c)
    return cats


def derive_beats(e):
    """Return list of (beat_text, [categories]) sized 10-14 from entry."""
    if e.get("beats"):
        return [(b["t"], b.get("tags", [])) for b in e["beats"]]
    # fallback for old-schema entries: split narration into ~10 chunks
    words = e["narration"].split()
    n = 10
    chunks = [words[i * len(words) // n:(i + 1) * len(words) // n] for i in range(n)]
    beats = []
    scenes = e.get("scenes", [])
    for i, ch in enumerate(chunks):
        txt = " ".join(ch)
        sc = scenes[i % len(scenes)] if scenes else txt
        beats.append((txt, cats_for_text(sc)))
    return beats


def pick_footage(e, workdir):
    """Strict semantic Pexels matching with zero clip repeats inside one video.

    Declared beat tags have priority; categories inferred from the actual narration
    are secondary. Generic fallback footage is forbidden: if the local pool has no
    unused relevant clip, the run stops instead of showing an unrelated visual.
    """
    idx = load_footage()
    beats = derive_beats(e)
    clips, used_files = [], set()
    for beat_i, (txt, tags) in enumerate(beats, 1):
        declared = [c for c in tags if c in idx and idx[c]]
        inferred = [c for c in cats_for_text(txt) if c in idx and idx[c]]
        cats = []
        for c in declared + inferred:
            if c not in cats:
                cats.append(c)
        if not cats:
            raise SystemExit(
                f"FOOTAGE_MATCH_MISSING beat={beat_i}: no semantic category for: {txt[:120]}")

        clip = None
        chosen_cat = None
        # Rotate deterministically by video+beat so different stories do not always
        # start with the same stock shot, while keeping runs reproducible.
        for c in cats:
            pool = idx[c]
            offset = sum(ord(ch) for ch in f"{e['id']}:{beat_i}:{c}") % len(pool)
            ordered = pool[offset:] + pool[:offset]
            for candidate in ordered:
                key = candidate.get("file") or candidate.get("url")
                if key and key not in used_files:
                    clip, chosen_cat = candidate, c
                    break
            if clip:
                break
        if not clip:
            raise SystemExit(
                f"FOOTAGE_MATCH_MISSING beat={beat_i}: relevant pools exhausted "
                f"({','.join(cats)}); refusing repeated/unrelated footage")
        used_files.add(clip.get("file") or clip.get("url"))
        clips.append((clip, len(txt.split())))
        print(f"beat: {beat_i} <- {clip['file']} [{chosen_cat}] ({len(txt.split())}w)", flush=True)
    return clips


# ---- Kokoro TTS (owner-approved 2026-09-22: human-like, emotion-aware) ----
KOKORO_VOICE = "am_michael"
KOKORO_SR = 24000
# mood keyword -> (match list, speaking speed). Lower speed = slower/heavier.
# Owner rule: emotion must fit the story (sad slow, tense tight, exciting bright),
# overall pacing slow and steady with natural pauses between beats.
_MOODS = [
    ("sad", ["sad", "tragedy", "tragic", "died", "death", "lost", "grief",
             "mourning", "devastat", "tears", "farewell", "heartbroken",
             "funeral", "passed away", "no one knew"], 0.90),
    ("tense", ["warning", "danger", "threat", "war", "attack", "emergency",
               "panic", "fear", "crisis", "alarm", "risk", "nearly",
               "countdown", "collapse", "too late", "under control"], 0.94),
    ("excited", ["amazing", "incredible", "record", "fastest", "first ever",
                 "breakthrough", "stunned", "shocked", "massive", "historic",
                 "unbelievable", "exploded", "smashed", "milestone"], 1.04),
]
_MOOD_DEFAULT_SPEED = 0.97  # slightly slower than natural = steady documentary pace


def _kokoro_speed(text):
    low = text.lower()
    for _m, kws, sp in _MOODS:
        if any(k in low for k in kws):
            return sp
    return _MOOD_DEFAULT_SPEED


def _kokoro_voice(e, out):
    """Try Kokoro TTS: per-beat synthesis with mood-based speed and natural
    pauses between beats. Returns True on success, False to fall back."""
    try:
        import io, contextlib
        import numpy as np
        import soundfile as sf
        with contextlib.redirect_stderr(io.StringIO()):  # silence onnx warnings
            from kokoro_onnx import Kokoro
            kokoro = Kokoro(os.path.join(BASE, "tts_kokoro", "kokoro-v1.0.fp16.onnx"),
                            os.path.join(BASE, "tts_kokoro", "voices-v1.0.bin"))
    except Exception as ex:
        print("kokoro unloadable, falling back to edge-tts:", str(ex)[:120], flush=True)
        return False
    parts = [b["t"].strip() for b in e.get("beats", []) if b.get("t")]
    if not parts:
        parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", e["narration"]) if s.strip()]
    pieces, moods = [], []
    try:
        # shorts: keep under the 61s vertical gate; longs: slow steady pace
        sp_factor = 1.05 if e.get("kind") == "short" else 1.0
        for i, txt in enumerate(parts):
            sp = _kokoro_speed(txt) * sp_factor
            moods.append(f"{sp:.2f}")
            audio, _sr = kokoro.create(txt, voice=KOKORO_VOICE, speed=sp, lang="en-us")
            pieces.append(audio)
            if i < len(parts) - 1:
                # natural beat pause: base + longer after question/dramatic dots
                pause = 0.45
                if txt.endswith("?"):
                    pause += 0.25
                elif txt.endswith("..."):
                    pause += 0.20
                pieces.append(np.zeros(int(KOKORO_SR * pause), dtype=audio.dtype))
        full = np.concatenate(pieces)
        wav = out.replace(".mp3", ".wav")
        sf.write(wav, full, KOKORO_SR)
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav,
                            "-codec:a", "libmp3lame", "-b:a", "192k", out],
                           capture_output=True, text=True)
        if os.path.exists(wav):
            os.remove(wav)
        if r.returncode or not os.path.exists(out):
            return False
        print(f"voice: OK (kokoro {KOKORO_VOICE}, {len(parts)} beats, speeds {','.join(moods[:6])}...)", flush=True)
        return True
    except Exception as ex:
        print("kokoro synthesis failed, falling back:", str(ex)[:150], flush=True)
        return False


def gen_voice(e, workdir):
    out = os.path.join(workdir, "narration.mp3")
    if _kokoro_voice(e, out):
        return out
    r = subprocess.run(
        ["edge-tts", "--voice", LIB["voice"], "--rate=+4%",
         "--text", e["narration"], "--write-media", out],
        capture_output=True, text=True)
    if r.returncode or not os.path.exists(out):
        raise SystemExit("TTS_FAILED: " + (r.stderr or "")[-200:])
    print("voice: OK (edge-tts fallback)", flush=True)
    return out


def render(e, workdir, clips, audio):
    """Real-footage render: word-weighted beat timing, trims/slowmo, crossfades,
    cinematic grade + grain + vignette, loud narration + ambient bed."""
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio], capture_output=True, text=True).stdout.strip())
    if e.get("kind") == "short":
        if dur > 61:
            raise SystemExit(f"SHORT_TOO_LONG {dur:.0f}s - narration must fit 60s")
        W, H, XF = 1080, 1920, 0.3
    else:
        W, H, XF = 1920, 1080, 0.6
    n = len(clips)
    fps = 25
    wsum = sum(w for _, w in clips)
    fc, inputs = [], []
    offsets = []
    total = 0.0
    for k, (clip, wc) in enumerate(clips):
        di = (dur + XF * (n - 1)) * wc / wsum
        cdur = min(clip["dur"], di * 2)          # cap pre-slow trim
        slow = min(di / cdur, 2.0)               # slowmo cap 2x
        di_eff = cdur * slow
        pad = max(di - di_eff, 0.0)
        offsets.append(total)
        total += di - XF
        fc.append(
            f"[{k}:v]trim=0:{cdur:.3f},setpts=PTS*{slow:.4f},"
            f"tpad=stop_mode=clone:stop_duration={pad:.3f},"
            f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},fps={fps},format=yuv420p[v{k}]")
        inputs += ["-i", os.path.join(FOOTAGE, clip["file"])]
    last = "v0"
    for k in range(1, n):
        fc.append(f"[{last}][v{k}]xfade=transition=fade:duration={XF}:"
                  f"offset={offsets[k]:.3f}[x{k}]")
        last = f"x{k}"
    fc.append(
        f"[{last}]eq=contrast=1.10:saturation=1.14:brightness=0.01,"
        "colorbalance=rs=.02:bs=.05:bm=-.06,vignette=PI/4.5,"
        "noise=alls=4:allf=t+u,unsharp=5:5:0.35[out]")
    # ---- AUDIO: loud narration + ambient bed ----
    bed_end = max(dur - 3.0, 0)
    _CHORDS = [(110.0, 164.81, 220.0), (98.0, 146.83, 196.0),
               (123.47, 185.0, 246.94), (87.31, 130.81, 174.61)]
    f1, f2, f3 = _CHORDS[int(e.get("seed", 42)) % len(_CHORDS)]
    fc.append(
        f"aevalsrc='0.013*sin(2*PI*{f1:.2f}*t)+0.011*sin(2*PI*{f1+0.4:.2f}*t)"
        f"+0.010*sin(2*PI*{f2:.2f}*t)+0.009*sin(2*PI*{f3:.2f}*t)':d={dur:.2f},"
        "tremolo=f=0.1:d=0.55,afade=t=in:d=2.5,"
        f"afade=t=out:st={bed_end:.2f}:d=3[bedp]")
    fc.append(
        f"anoisesrc=color=brown:amplitude=0.012:duration={dur:.2f}:seed=42,"
        "lowpass=f=350,afade=t=in:d=2.5,"
        f"afade=t=out:st={bed_end:.2f}:d=3[bedn]")
    fc.append("[bedp][bedn]amix=inputs=2:duration=longest:normalize=0[bed]")
    fc.append(f"[{n}:a]loudnorm=I=-13:TP=-1.5:LRA=11[nar]")
    fc.append("[nar][bed]amix=inputs=2:duration=first:normalize=0,aresample=48000[aout]")
    out = os.path.join(workdir, "final.mp4")
    tmp = os.path.join(workdir, "_final_tmp.mp4")
    cmd = ["ffmpeg", "-y"] + inputs
    cmd += ["-i", audio, "-filter_complex", ";".join(fc),
            "-map", "[out]", "-map", "[aout]", "-t", f"{dur:.2f}",
            "-c:v", "libx264", "-preset", ("veryfast" if e.get("kind") == "short" else "ultrafast"), "-crf", "21",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", tmp]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("RENDER_FAILED: " + r.stderr[-600:])
    # INTEGRITY: killed/truncated renders must never pass (2026-09-21 shorts bug)
    chk = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", tmp, "-f", "null", "-"],
        capture_output=True, text=True)
    if chk.returncode or "NAL" in chk.stderr or "Error" in chk.stderr:
        try: os.remove(tmp)
        except OSError: pass
        raise SystemExit("RENDER_INCOMPLETE (output truncated/corrupt — retry next run)")
    sz = os.path.getsize(tmp)
    if sz < 1_000_000:
        raise SystemExit(f"RENDER_TOO_SMALL {sz}")
    vd = subprocess.run(
        ["ffmpeg", "-i", tmp, "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    import re as _re
    mean = _re.search(r"mean_volume: ([-0-9.]+) dB", vd)
    peak = _re.search(r"max_volume: ([-0-9.]+) dB", vd)
    if peak and float(peak.group(1)) > -0.5:
        raise SystemExit(f"AUDIO_CLIPPING max={peak.group(1)}dB")
    if mean and float(mean.group(1)) < -35:
        try: os.remove(tmp)
        except OSError: pass
        raise SystemExit(f"AUDIO_TOO_QUIET mean={mean.group(1)}dB")
    print(f"audio check: mean={mean.group(1) if mean else '?'}dB peak={peak.group(1) if peak else '?'}dB", flush=True)
    os.replace(tmp, out)  # atomic: final.mp4 only ever exists complete & verified
    print(f"render: OK {sz//1048576}MB {round(dur)}s", flush=True)
    return out


def make_thumb(e, workdir, clip):
    """Pull a striking frame from the beat-1 clip, overlay the title, save thumb.jpg."""
    src_f = os.path.join(FOOTAGE, clip["file"])
    t = min(clip["dur"] * 0.45, 8)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
                    "-i", src_f, "-frames:v", "1",
                    os.path.join(workdir, "_thumb_raw.jpg")], check=True)
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont
    im = Image.open(os.path.join(workdir, "_thumb_raw.jpg")).convert("RGB")
    vertical = e.get("kind") == "short"
    TW, TH = (1080, 1920) if vertical else (1280, 720)
    im = im.resize((TW, TH), Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.15)
    im = ImageEnhance.Color(im).enhance(1.25)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, TW, TH], outline=None, fill=None)
    # dark gradient band at bottom for text
    band_top = int(TH * 0.46)
    for y in range(TH):
        a = int(200 * max(0, (y - band_top) / (TH - band_top)) ** 1.3)
        d.line([(0, y), (TW, y)], fill=(8, 8, 12, min(a, 200)))
    f_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                               66 if vertical else 78)
    f_med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    # wrap title into up to 4 (vertical) / 3 (wide) lines
    maxw = TW - 76
    nlines = 4 if vertical else 3
    words = e["title"].split()
    lines, cur = [], ""
    for w in words:
        t2 = (cur + " " + w).strip()
        if d.textlength(t2, font=f_big) > maxw:
            lines.append(cur); cur = w
        else:
            cur = t2
    lines.append(cur)
    lines = lines[-nlines:]
    lh = 82 if not vertical else 74
    y0 = TH - 90 - lh * len(lines)
    for li, line in enumerate(lines):
        y = y0 + li * lh
        d.text((38, y), line, font=f_big, fill=(255, 255, 255),
               stroke_width=6, stroke_fill=(0, 0, 0))
    d.rectangle([38, 60, 178, 70], fill=(255, 55, 55))
    d.text((38, 78), "NEXTAI VISION", font=f_med, fill=(255, 255, 255))
    out = os.path.join(workdir, "thumb.jpg")
    im.save(out, quality=90)
    print("thumb: composed from footage", flush=True)
    return out


def set_thumbnail(vid, workdir):
    try:
        f = os.path.join(workdir, "thumb.jpg")
        if not os.path.exists(f):
            print("thumbnail: no thumb.jpg, skip", flush=True)
            return False
        # YouTube only processes 16:9 custom thumbnails reliably (verified 2026-09-22):
        # portrait 9:16 ChatGPT art is converted to a 1280x720 blur-fill composite.
        try:
            from PIL import Image as _Img, ImageFilter as _Flt
            _im = _Img.open(f)
            if _im.height > _im.width:
                _im = _im.convert("RGB")
                _bg = _im.resize((1280, 720)).filter(_Flt.GaussianBlur(40))
                _w = int(_im.width * 720 / _im.height)
                _bg.paste(_im.resize((_w, 720), _Img.LANCZOS), ((1280 - _w) // 2, 0))
                _tmp = os.path.join(workdir, "_thumb_720.jpg")
                _bg.save(_tmp, quality=92)
                if not os.path.exists(os.path.join(workdir, "thumb_9x16_orig.jpg")):
                    import shutil as _sh
                    _sh.copy(f, os.path.join(workdir, "thumb_9x16_orig.jpg"))
                f = _tmp
                print("thumbnail: converted 9:16 -> 1280x720 blur-fill", flush=True)
        except Exception as _ex:
            print("thumbnail: portrait-convert skipped:", str(_ex)[:60], flush=True)
        tok = get_token()
        url = f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}"
        data = open(f, "rb").read()
        req = urllib.request.Request(url, data=data, method="POST", headers={
            "Authorization": f"Bearer {tok['access_token']}",
            "Content-Type": "image/jpeg"})
        urllib.request.urlopen(req, timeout=60)
        print("thumbnail: OK", flush=True)
        return True
    except Exception as ex:
        print("thumbnail: failed (video stays up):", str(ex)[:120], flush=True)
        return False


def upload(e, mp4, publish_at=None):
    if not content_eligible(e):
        raise SystemExit("CONTENT_SCOPE_BLOCKED: upload refused for " + e["id"])
    if not publish_at:
        raise SystemExit("SCHEDULE_REQUIRED: every future upload must use publishAt")
    expected, _ = next_bd_slot(e.get("kind", "long"))
    if publish_at != expected:
        raise SystemExit("SCHEDULE_WINDOW_MISSED: invalid or already-filled publication slot")
    tok = get_token()
    H = {"Authorization": f"Bearer {tok['access_token']}",
         "Content-Type": "application/json"}
    st_meta = {"privacyStatus": "private" if publish_at else "public",
               "selfDeclaredMadeForKids": e.get("madeForKids", True)}
    if publish_at:
        st_meta["publishAt"] = publish_at
    DISC = "This video includes AI-generated visuals and voiceover for educational purposes."
    # SEO description (owner rule 2026-09-21): topic keywords + search line + hashtags
    tags = list(e["tags"])
    for base in {
        "ai_updates": ("AI", "artificial intelligence", "AI tools", "AI updates"),
        "gadget_reviews": ("gadget review", "tech review", "buying guide"),
        "personal_finance": ("personal finance", "money management", "financial education"),
    }.get(e.get("content_pillar"), ()):
        if base.lower() not in [t.lower() for t in tags]:
            tags.append(base)
    kw = ", ".join(tags[:10])
    hashtags = " ".join("#" + t.title().replace(" ", "") for t in tags[:5])
    desc = e["description"].strip()
    if "Related searches" not in desc:
        desc = desc + "\n\nRelated searches: " + kw + "\n\n" + hashtags
    if DISC not in desc:
        desc = (desc + "\n\n" + DISC).strip()
    meta = {"snippet": {
                "title": e["title"], "description": desc,
                "tags": tags, "categoryId": e["categoryId"]},
            "status": st_meta}
    body = json.dumps(meta).encode()
    req = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos"
        "?uploadType=resumable&part=snippet,status",
        data=body, method="POST",
        headers={**H, "Content-Length": str(len(body))})
    try:
        with urllib.request.urlopen(req) as r0:
            r0.read()
            loc = r0.headers["Location"]
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")[:300]
        if e.code in (401, 403):
            raise SystemExit("TOKEN_EXPIRED_OR_DENIED: " + txt)
        raise SystemExit(f"UPLOAD_INIT_FAILED {e.code}: " + txt)
    with open(mp4, "rb") as f:
        data = f.read()
    req2 = urllib.request.Request(loc, data=data, method="PUT",
        headers={"Content-Type": "video/mp4",
                 "Content-Length": str(len(data))})
    try:
        with urllib.request.urlopen(req2) as r2:
            out = json.loads(r2.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"UPLOAD_FAILED {e.code}: " + e.read().decode(errors="replace")[:300])
    vid = out.get("id")
    if not vid:
        raise SystemExit("UPLOAD_NO_ID")
    print(f"upload: OK videoId={vid} scheduledFor={publish_at or 'now-public'}", flush=True)
    return vid


def publish_existing(e, workdir):
    """Upload an already-rendered final.mp4 from a previous run (no re-render)."""
    res_f = os.path.join(workdir, "result.json")
    result = json.load(open(res_f)) if os.path.exists(res_f) else {"id": e["id"]}
    mp4 = os.path.join(workdir, "final.mp4")
    if not os.path.exists(mp4):
        raise SystemExit("PUBLISH_NO_MP4: " + workdir)
    publish_at, _slot = next_bd_slot(e.get("kind", "long"))
    vid = upload(e, mp4, publish_at)
    if e.get("kind") == "long" and not os.path.exists(os.path.join(workdir, "thumb.jpg")):
        clips = pick_footage(e, workdir)
        make_thumb(e, workdir, clips[0][0])
    set_thumbnail(vid, workdir)
    result.update({"status": "scheduled" if publish_at else "published",
                   "videoId": vid, "file": mp4,
                   "scheduledFor": publish_at,
                   "url": f"https://www.youtube.com/watch?v={vid}"})
    st = load_state()
    st["done"][e["id"]] = {"date": result.get("date", today_str()), "videoId": vid}
    note_published(e, vid, e.get("kind", "long"), publish_at)
    save_state(st)
    json.dump(result, open(res_f, "w"), indent=1)
    print("RESULT " + json.dumps(result), flush=True)


def today_str():
    return time.strftime("%Y-%m-%d")


def main():
    if any(a in sys.argv for a in ("--pinned", "--comments", "--reply")):
        comment_cli()
        return
    if "--setthumb" in sys.argv:
        workdir = sys.argv[sys.argv.index("--setthumb") + 1]
        res_f = os.path.join(workdir, "result.json")
        result = json.load(open(res_f))
        vid = result.get("videoId")
        if not vid:
            raise SystemExit("SETTHUMB_NO_VIDEOID: publish the video first")
        if not os.path.exists(os.path.join(workdir, "thumb.jpg")):
            raise SystemExit("SETTHUMB_NO_THUMB: put the new image at " + os.path.join(workdir, "thumb.jpg"))
        if set_thumbnail(vid, workdir):
            print(f"thumbnail: updated for {vid}", flush=True)
        else:
            print("thumbnail: NOT updated (see error above)", flush=True)
        return
    if "--publish" in sys.argv:
        workdir = sys.argv[sys.argv.index("--publish") + 1]
        eid = re.sub(r"_\d{4}-\d{2}-\d{2}$", "", os.path.basename(workdir))
        e = pick_entry(eid)
        print(f"=== Publish existing render: {e['title']}", flush=True)
        publish_existing(e, workdir)
        return
    eid = None
    if "--id" in sys.argv:
        eid = sys.argv[sys.argv.index("--id") + 1]
    kind = "short" if "--short" in sys.argv else "long"
    e = pick_entry(eid, kind)
    today = time.strftime("%Y-%m-%d")
    workdir = os.path.join(RUNS, f"{e['id']}_{today}")
    os.makedirs(workdir, exist_ok=True)
    next_bd_slot(kind)  # validate scheduling window before expensive rendering
    print(f"=== Content Factory ({kind}): {e['title']}", flush=True)
    clips = pick_footage(e, workdir)
    audio = gen_voice(e, workdir)
    mp4 = render(e, workdir, clips, audio)
    policy = json.load(open(os.path.join(BASE, "content_policy.json")))
    chatgpt_only = policy.get("production_style", {}).get("thumbnail_generator") == "ChatGPT ONLY, existing single account"
    if chatgpt_only:
        print("thumbnail: ChatGPT-only policy; deferring generation and upload to ChatGPT session", flush=True)
    else:
        make_thumb(e, workdir, clips[0][0])
    result = {"id": e["id"], "date": today, "status": "rendered", "file": mp4}
    try:
        publish_at, slot_local = next_bd_slot(kind)
        print(f"scheduled slot (BD): {slot_local}", flush=True)
        vid = upload(e, mp4, publish_at)
        if chatgpt_only:
            print("thumbnail: not applied; awaiting required ChatGPT-generated image", flush=True)
        else:
            set_thumbnail(vid, workdir)
        result.update({"status": "scheduled" if publish_at else "published",
                       "videoId": vid,
                       "scheduledFor": publish_at,
                       "url": f"https://www.youtube.com/watch?v={vid}"})
        st = load_state()
        st["done"][e["id"]] = {"date": today, "videoId": vid}
        save_state(st)
        note_published(e, vid, kind, publish_at)
    except SystemExit as ex:
        if "TOKEN" in str(ex):
            result.update({"status": "NEEDS_TOKEN",
                           "detail": str(ex)[:200]})
            print(str(ex), flush=True)
        elif "SCHEDULE" in str(ex):
            result.update({"status": "NEEDS_SCHEDULE", "detail": str(ex)[:200]})
            print(str(ex), flush=True)
        else:
            raise
    json.dump(result, open(os.path.join(workdir, "result.json"), "w"), indent=1)
    print("RESULT " + json.dumps(result), flush=True)




# ---------------- COMMENT BOOSTER (owner request 2026-09-20) ----------------
def yt_api(method, path, body=None):
    tok = get_token()
    url = "https://www.googleapis.com/youtube/v3/" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
        headers={"Authorization": f"Bearer {tok['access_token']}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as ex:
        raise SystemExit(f"YT_API_ERROR {ex.code}: " + ex.read().decode(errors="replace")[:300])


def comment_state():
    p = os.path.join(BASE, "comment_state.json")
    return json.load(open(p)) if os.path.exists(p) else {"replied": {}, "pinned": {}}


def save_comment_state(cs):
    json.dump(cs, open(os.path.join(BASE, "comment_state.json"), "w"), indent=1)


def post_comment(vid, text):
    out = yt_api("POST", "commentThreads?part=snippet", {
        "snippet": {"videoId": vid,
                    "topLevelComment": {"snippet": {"textOriginal": text}}}})
    cid = (out.get("snippet", {}).get("topLevelComment", {})
              .get("snippet", {}).get("textDisplay", "?"))
    cid_id = out.get("id")
    print(f"comment: posted id={cid_id} as channel", flush=True)
    # NOTE: YouTube Data API cannot pin a comment (Studio-only). We post it
    # first so it sits at the top of "newest first"; owner can pin in one tap.
    return out.get("id")


def list_comments(vid, n=50):
    out = yt_api("GET", f"commentThreads?part=snippet&order=time&maxResults={min(n,100)}&videoId={vid}")
    items = []
    for it in out.get("items", []):
        s = it["snippet"]["topLevelComment"]["snippet"]
        items.append({"id": it["id"], "author": s.get("authorDisplayName", "?"),
                      "text": s.get("textDisplay", "")[:300],
                      "likes": s.get("likeCount", 0),
                      "at": s.get("publishedAt", ""),
                      "replies": it["snippet"].get("totalReplyCount", 0)})
    print(json.dumps(items, indent=1, ensure_ascii=False), flush=True)
    return items


def reply_comment(parent_id, text):
    out = yt_api("POST", "commentThreads?part=snippet", {
        "snippet": {"parentId": parent_id, "textOriginal": text}})
    print(f"reply: posted to {parent_id}", flush=True)
    return out.get("id")


def note_published(e, vid, kind, scheduled_for=None):
    p = os.path.join(BASE, "published_log.json")
    log = json.load(open(p)) if os.path.exists(p) else []
    log.append({"id": e["id"], "videoId": vid, "title": e["title"], "kind": kind,
                "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S+06:00"),
                "scheduled_for": scheduled_for,
                "url": f"https://www.youtube.com/watch?v={vid}"})
    json.dump(log, open(p, "w"), indent=1, ensure_ascii=False)


def comment_cli():
    if "--pinned" in sys.argv:
        vid = sys.argv[sys.argv.index("--pinned") + 1]
        txt_f = sys.argv[sys.argv.index("--pinned") + 2]
        text = open(txt_f).read().strip() if os.path.exists(txt_f) else txt_f
        cid = post_comment(vid, text)
        if cid:
            cs = comment_state()
            cs["pinned"].setdefault(vid, []).append(cid)
            save_comment_state(cs)
        print("note: API cannot pin; post shows as newest comment (owner can pin in Studio)", flush=True)
    elif "--comments" in sys.argv:
        vid = sys.argv[sys.argv.index("--comments") + 1]
        list_comments(vid)
    elif "--reply" in sys.argv:
        pid = sys.argv[sys.argv.index("--reply") + 1]
        vid = sys.argv[sys.argv.index("--reply") + 2]
        txt_f = sys.argv[sys.argv.index("--reply") + 3]
        text = open(txt_f).read().strip() if os.path.exists(txt_f) else txt_f
        reply_comment(pid, text)
        cs = comment_state()
        cs.setdefault("replied", {})[pid] = vid
        save_comment_state(cs)


if __name__ == "__main__":
    main()
