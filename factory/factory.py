#!/usr/bin/env python3
"""Content Factory — fully automated nightly video pipeline.
Usage:
  python3 factory.py --next           # produce the next unused library entry
  python3 factory.py --id twinkle_star  # produce a specific entry
Zero-cost stack: Pollinations (images) + Edge-TTS (voice) + ffmpeg (render) + YouTube resumable upload.
"""
import base64
import re as _re
import json, os, re, sys, time, subprocess, urllib.parse, urllib.request
import datetime as _dt
from zoneinfo import ZoneInfo


UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
# Owner directive 2026-10-07: rotate multiple Gemini keys (separate projects =
# separate image quotas). GEMINI_API_KEY may hold a comma-separated key list;
# extra keys may also live in GEMINI_API_KEY_2 .. _9.
_raw_keys = [k.strip() for k in os.environ.get("GEMINI_API_KEY", "").split(",") if k.strip()]
for _i in range(2, 10):
    _extra = os.environ.get(f"GEMINI_API_KEY_{_i}", "")
    _raw_keys += [k.strip() for k in _extra.split(",") if k.strip()]
GEMINI_KEYS = list(dict.fromkeys(_raw_keys))
GEMINI_KEY = GEMINI_KEYS[0] if GEMINI_KEYS else ""
GEMINI_MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_MODELS", "gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-3.5-flash,gemini-flash-latest,gemini-3.8-flash").split(",") if m.strip()]
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "").strip()
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
    lo = cfg.get("lead_hours_min_short", 1) if kind == "short" else cfg["lead_hours_min"]
    hi = cfg.get("lead_hours_max_short", 20) if kind == "short" else cfg["lead_hours_max"]
    # OWNER RULE 2026-10-06 09:19: ONE Long every 2 days (quality over daily
    # quantity); Shorts are daily cuts of that Long. Min gap enforced here.
    gap_days = cfg.get("long_min_gap_days", 2) if kind == "long" else 0
    last_long = None
    if kind == "long" and os.path.exists(log_path):
        for row in json.load(open(log_path)):
            if row.get("kind") == "long" and row.get("scheduled_for"):
                d = _dt.datetime.fromisoformat(row["scheduled_for"].replace("Z", "+00:00"))
                if last_long is None or d > last_long:
                    last_long = d
    for day in range(4):
        for hhmm in sorted(cfg["slots"][kind]):
            hh, mm = map(int, hhmm.split(":"))
            candidate = (now + _dt.timedelta(days=day)).replace(hour=hh, minute=mm, second=0, microsecond=0)
            if kind == "long" and hhmm == "19:30" and candidate.date().isoformat() < cfg["first_new_evening_long_date"]:
                continue  # Oct 1 existing 18:30 upload is preserved, no extra evening Long.
            if last_long is not None and gap_days:
                if (candidate - last_long).total_seconds() < gap_days * 86400:
                    continue  # 2-day Long cadence: too soon after the last Long.
            gap = (candidate - now).total_seconds() / 3600
            if lo <= gap <= hi and candidate not in reserved:
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


def _gemini_beat_queries(e, beats):
    """One Gemini call: turn every spoken sentence into 2-3 concrete,
    filmable stock-footage search phrases. Abstract nouns are translated
    into real on-screen subjects so footage matches the words."""
    if not GEMINI_KEY or not GEMINI_MODELS:
        return None
    lines = "\n".join(f"{i}: {t}" for i, (t, _) in enumerate(beats, 1))
    prompt = (
        "A documentary narration has sentences numbered below. "
        "For EACH sentence, invent 2-3 short stock-video search phrases (2-4 words each) "
        "describing concrete, filmable visuals that EXACTLY match what that sentence says. "
        "OWNER RULE 2026-10-08 (footage must match the narration): phrases must name real "
        "physical footage that EXISTS in stock-video libraries: objects, places, people, "
        "actions (e.g. 'server room lights', 'robot arm factory', 'person typing laptop'). "
        "NEVER use brand or product names (ChatGPT, Claude, OpenAI, Gemini, DeepSeek...) and "
        "NEVER abstract ideas (future, intelligence, innovation, power) — stock libraries do "
        "not have those, so the clip would not match the words. If the sentence is about an "
        "AI brand or model, describe the related physical scene instead (data center, laptop "
        "screen, computer chip, office desk). "
        "Phrases must differ between sentences so footage never repeats; "
        "keep it professional and family-safe. For sentences 1-2 (the cold-open hook), pick the most "
        "dramatic, high-energy, visually striking real footage subjects available. "
        f"Video title: {e['title']}. Sentences:\n{lines}\n\n"
        "Return JSON only: {\"queries\": [[\"phrase one\", \"phrase two\"], ...]} "
        "with exactly one array per sentence, in order.")
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.8, "responseMimeType": "application/json"},
    }).encode()
    for rnd in range(4):
        for model in GEMINI_MODELS:
          for ki, key in enumerate(GEMINI_KEYS):
            try:
                req = urllib.request.Request(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    data=body, headers={"Content-Type": "application/json",
                                        "x-goog-api-key": key})
                with urllib.request.urlopen(req, timeout=60) as r:
                    out = json.load(r)
                txt = out["candidates"][0]["content"]["parts"][0]["text"]
                q = json.loads(txt).get("queries")
                if isinstance(q, list) and len(q) == len(beats):
                    return [[x for x in row if isinstance(x, str) and x.strip()][:3] or None for row in q]
            except Exception as ex:
                msg = str(ex)[:80]
                if "429" in msg and ki + 1 < len(GEMINI_KEYS):
                    print(f"  gemini {model}: 429 on key#{ki + 1}; rotating to key#{ki + 2}", flush=True)
                    continue
                print(f"  gemini {model} key#{ki + 1} round {rnd}: {msg}", flush=True)
                time.sleep(3 * (rnd + 1))
                break
    return None


def pick_footage(e, workdir):
    """Owner rule (2026-10-05): EVERY spoken sentence gets its OWN freshly
    downloaded clip matching what that sentence says. Pixabay API fetch per
    beat; the old shared local pool is a fallback ONLY when a fetch fails.
    Zero clip repeats inside one video, and a persistent ledger avoids
    reusing the same Pixabay video id across videos."""

    # category -> English search phrase for Pixabay (visual meaning of the beat)
    CAT2Q = {
        "ai": "artificial intelligence technology", "network": "neural network abstract",
        "code": "programming code screen", "chip": "computer chip circuit macro",
        "datacenter": "server room data center", "robot": "robot technology",
        "dna": "dna helix animation", "microscope": "microscope laboratory",
        "scientist": "scientist laboratory research", "pills": "medicine pills pharmacy",
        "doctor": "doctor hospital", "heart": "heart medical monitor",
        "space": "space stars universe", "planet": "planet earth space",
        "city": "city aerial timelapse", "car": "car driving road",
        "ocean": "ocean waves aerial", "walk": "person walking street",
        "laser": "laser light science", "nanotech": "molecular 3d animation",
        "protein": "protein 3d animation", "bacteria": "bacteria microscope",
        "injection": "syringe injection medical", "patient": "hospital patient care",
        "boardgame": "board game", "socialmedia": "social media phone screen",
        "go": "abstract technology background",
    }

    ledger_path = os.path.join(FOOTAGE, "_pixabay_used.json")
    try:
        global_used = set(json.load(open(ledger_path)))
    except Exception:
        global_used = set()
    fresh_dir = os.path.join(workdir, "fresh_footage")
    os.makedirs(fresh_dir, exist_ok=True)

    idx = load_footage()
    beats = derive_beats(e)
    beat_queries = _gemini_beat_queries(e, beats)
    if beat_queries:
        print("gemini: per-sentence visual queries generated", flush=True)
    else:
        print("gemini unavailable; using category fallback phrases", flush=True)
    clips, used_files = [], set()
    used_ids = set()

    def pixabay_search(query, beat_i):
        """Search pixabay and return relevance-scored candidates (no download).
        OWNER FIX 2026-10-08: footage must MATCH the narration — every
        candidate is scored by how many query words appear in its tags."""
        url = ("https://pixabay.com/api/videos/?key=" + PIXABAY_KEY +
               "&q=" + urllib.parse.quote(query) + "&per_page=15&video_type=film")
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            data = json.load(urllib.request.urlopen(req, timeout=30))
        except Exception as ex:
            print(f"  pixabay fetch failed for {query!r}: {ex}", flush=True)
            return []
        cands = [h for h in data.get("hits", [])
                 if h["id"] not in used_ids and h["id"] not in global_used
                 and h.get("videos", {}).get("medium", {}).get("url")
                 and h.get("duration", 0) >= 3]
        # quality gate: prefer full-HD clips when the search offers any
        hd = [h for h in cands if h.get("videos", {}).get("large", {}).get("width", 0) >= 1920]
        if hd:
            cands = hd
        qtok = {w for w in re.split(r"[^a-z0-9]+", query.lower()) if len(w) >= 3}

        def _rel(h):
            _tg = h.get("tags", "")
            if not isinstance(_tg, str):  # pixabay returns tags as a comma string
                _tg = " ".join(_tg)
            blob = _tg.lower() + " " + (h.get("pageURL", "") or "").lower()
            return len(qtok & {w for w in re.split(r"[^a-z0-9]+", blob) if len(w) >= 3})
        for h in cands:
            h["rel"] = _rel(h)
        # most relevant first (views/downloads break ties)
        cands.sort(key=lambda h: -(h["rel"] * 1_000_000 + h.get("views", 0) + h.get("downloads", 0)))
        return cands

    def pixabay_download(hit, query, beat_i):
        vs = hit["videos"]
        v = vs.get("large") or vs.get("medium")
        out = os.path.join(fresh_dir, f"beat{beat_i}.mp4")
        try:
            vreq = urllib.request.Request(v["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(vreq, timeout=180) as r, open(out, "wb") as f:
                while True:
                    chunk = r.read(1 << 22)
                    if not chunk:
                        break
                    f.write(chunk)
        except Exception as ex:
            print(f"  pixabay download failed for {query!r}: {ex}", flush=True)
            return None
        used_ids.add(hit["id"])
        global_used.add(hit["id"])
        cdur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", out],
            capture_output=True, text=True).stdout.strip() or 0)
        return {"file": out, "url": v["url"], "id": hit["id"], "q": query, "dur": cdur, "rel": hit["rel"]}

    def pool_clip(cats, beat_i):
        for c in cats:
            pool = idx.get(c) or []
            if not pool:
                continue
            offset = sum(ord(ch) for ch in f"{e['id']}:{beat_i}:{c}") % len(pool)
            ordered = pool[offset:] + pool[:offset]
            for cand in ordered:
                key = cand.get("file") or cand.get("url")
                if key and key not in used_files:
                    return cand, c
        return None, None

    for beat_i, (txt, tags) in enumerate(beats, 1):
        declared = [c for c in tags if c in idx and idx[c]]
        inferred = [c for c in cats_for_text(txt) if c in idx and idx[c]]
        cats = []
        for c in declared + inferred:
            if c not in cats:
                cats.append(c)
        queries = []
        if beat_queries and beat_queries[beat_i - 1]:
            queries = beat_queries[beat_i - 1]
        for c in cats:  # fallback if gemini missed this beat
            q = CAT2Q.get(c)
            if q and q not in queries:
                queries.append(q)
        if not queries:
            queries = ["abstract technology background"]

        clip = None
        if PIXABAY_KEY:
            searched = []  # (rel_of_best, query, candidates)
            for q in queries[:3]:
                cands = pixabay_search(q, beat_i)
                searched.append((cands[0]["rel"] if cands else -1, q, cands))
                if cands and cands[0]["rel"] >= 2:
                    break  # strong match — no need to try more queries
            # best query = highest relevance, earlier query wins ties
            bq, bc = None, None
            for rel_best, q, cands in searched:
                if cands and (bc is None or rel_best > bc[0]["rel"]):
                    bq, bc = q, cands
            if bc:
                # deterministic rotation among the most-relevant hits
                top = bc[:3]
                off = sum(ord(c) for c in f"{e['id']}:{beat_i}:{bq}") % len(top)
                clip = pixabay_download(top[off], bq, beat_i)
                if clip and clip["rel"] == 0:
                    print(f"  warn: weak footage match beat={beat_i} q={bq!r}", flush=True)
        src = "pixabay-fresh"
        if not clip:  # fetch failed/quota -> local pool fallback for this beat
            clip, chosen = pool_clip(cats, beat_i)
            src = f"pool-fallback[{chosen}]" if clip else None
        if not clip:
            raise SystemExit(
                f"FOOTAGE_MATCH_MISSING beat={beat_i}: no fresh or pooled clip for: {txt[:120]}")
        used_files.add(clip.get("file") or clip.get("url"))
        clips.append((clip, len(txt.split())))
        print(f"beat: {beat_i} <- {clip.get('q') or clip['file']} [{src}] ({len(txt.split())}w)", flush=True)

    if PIXABAY_KEY and used_ids:
        json.dump(sorted(global_used)[-5000:], open(ledger_path, "w"))
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
                # owner rule 2026-10-06: dramatic, varied pauses so delivery
                # never sounds monotonous - extra beat after the cold-open hook
                pause = 0.45
                if i == 0:
                    pause += 0.45
                if txt.endswith("?"):
                    pause += 0.35
                elif txt.endswith("..."):
                    pause += 0.30
                elif txt.endswith("!"):
                    pause += 0.15
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
        ["edge-tts", "--voice", LIB.get("voice", "en-US-ChristopherNeural"), "--rate=+4%",
         "--text", e["narration"], "--write-media", out],
        capture_output=True, text=True)
    if r.returncode or not os.path.exists(out):
        raise SystemExit("TTS_FAILED: " + (r.stderr or "")[-200:])
    print("voice: OK (edge-tts fallback)", flush=True)
    return out


def render(e, workdir, clips, audio):
    """Real-footage render: word-weighted beat timing, trims/slowmo, crossfades,
    cinematic grade + grain + vignette, loud narration + ambient bed."""
    # MONETIZATION GUARD (owner rule 2026-10-06): stock footage + AI voice alone
    # can read as "reused content" to YouTube reviewers, so every beat also
    # burns in a short on-screen key phrase (original editing added value).
    _cands = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"]
    FONT = next((f for f in _cands if os.path.exists(f)), None)
    if not FONT:
        raise SystemExit("CAPTION_FONT_MISSING - no bold ttf found on runner")

    def _cap_phrase(t):
        words = [w for w in re.sub(r"[^A-Za-z0-9 ]", " ", t).split() if len(w) > 1]
        return " ".join(words[:4]).upper()[:26].strip()

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio], capture_output=True, text=True).stdout.strip())
    if e.get("kind") == "short":
        if dur > 61:
            raise SystemExit(f"SHORT_TOO_LONG {dur:.0f}s - narration must fit 60s")
        W, H, XF = 1080, 1920, 0.3
    else:
        W, H, XF = 1920, 1080, 0.6
    # VISUAL HOOK (owner rule 2026-10-06): in the first ~20 seconds the framing
    # must change every 2-3 seconds so long-video retention holds. Each of the
    # first 3 beats is split into two visually-distinct segments: second half
    # gets a zoom-punch + shifted framing, giving a hard cut inside every beat.
    segs = []
    _btexts = [b.get("t", "") for b in e.get("beats", [])]
    for k, (clip, wc) in enumerate(clips):
        _bt = _btexts[k] if k < len(_btexts) else ""
        if e.get("kind") != "short" and k < 3:
            segs.append({"clip": clip, "wc": wc / 2.0, "intro": 0, "bt": _bt})
            segs.append({"clip": clip, "wc": wc / 2.0, "intro": 1, "bt": _bt})
        else:
            segs.append({"clip": clip, "wc": wc, "intro": None, "bt": _bt})
    n = len(segs)
    fps = 25
    wsum = sum(sg["wc"] for sg in segs)
    fc, inputs = [], []
    offsets = []
    total = 0.0
    for k, sg in enumerate(segs):
        clip, wc = sg["clip"], sg["wc"]
        di = (dur + XF * (n - 1)) * wc / wsum
        if sg["intro"] is None:
            cdur = min(clip["dur"], di * 2)      # cap pre-slow trim
            trim = f"trim=0:{cdur:.3f}"
        else:
            cdur = max(min(clip["dur"] / 2.0, di * 2), 0.4)
            if sg["intro"] == 0:
                trim = f"trim=0:{cdur:.3f}"
            else:  # second half of the clip, so the cut shows new motion
                st = min(cdur, max(clip["dur"] - cdur, 0.1))
                trim = f"trim={st:.3f}:{min(clip['dur'], st + cdur):.3f}"
        slow = min(di / cdur, 2.0)               # slowmo cap 2x
        di_eff = cdur * slow
        pad = max(di - di_eff, 0.0)
        offsets.append(total)
        total += di - XF
        if sg["intro"] == 1:                     # zoom-punch + shifted crop
            frame = (f"scale={int(W * 1.15)}:{int(H * 1.15)}:"
                     f"force_original_aspect_ratio=increase,"
                     f"crop={W}:{H}:(iw-ow)*0.72:(ih-oh)/2,")
        else:
            frame = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},")
        _phrase = _cap_phrase(sg.get("bt", ""))
        _cap = ""
        if _phrase:
            _cf = os.path.join(workdir, f"cap{k}.txt")
            with open(_cf, "w") as fh:
                fh.write(_phrase)
            _fs = W // 32 if e.get("kind") != "short" else W // 18
            _cap = (f",drawtext=fontfile={FONT}:textfile={_cf}"
                    f":fontsize={_fs}:fontcolor=white"
                    ":shadowcolor=black@0.75:shadowx=2:shadowy=2"
                    ":box=1:boxcolor=black@0.42:boxborderw=16"
                    f":x=(w-text_w)/2:y=h-text_h-{int(H * 0.09)}"
                    f":alpha='if(lt(t,0.3),t/0.3,if(gt(t,{di:.3f}-0.3),"
                    f"max(({di:.3f}-t)/0.3,0),1))'")
        fc.append(
            f"[{k}:v]{trim},setpts=PTS*{slow:.4f},"
            f"tpad=stop_mode=clone:stop_duration={pad:.3f},"
            + frame + f"fps={fps},format=yuv420p" + _cap + f"[v{k}]")
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


THUMB_AI_STYLE = (
    "clean tech-explainer like professional AI news channels, EXTREME high contrast, "
    "ONE big glowing focal object dead center, huge bold 3D ALL-CAPS text of the hook "
    "phrase - only 3-4 short words, letters thick and big enough to read on a small "
    "phone screen, no small text anywhere, dark navy background with bright teal and "
    "orange accent lighting, cinematic, 16:9")
THUMB_AI_MODELS = ["gemini-2.5-flash-image", "gemini-2.0-flash-exp-image-generation"]


def make_thumb_ai(e, workdir):
    """Generate thumbnail.jpg with the free Gemini image model. Returns path or None.

    Owner directive 2026-10-07: rotate a POOL of Gemini keys (each from its own
    Google Cloud project, so each has its own free image quota). The moment a
    key 429s (quota exhausted), the next key takes over instantly; only when
    every key is exhausted does the PIL fallback kick in.
    """
    if not GEMINI_KEYS:
        return None
    prompt = (
        f"Create a 16:9 YouTube thumbnail image for a video titled: \"{e['title']}\". "
        f"Style: {THUMB_AI_STYLE}. The big text on the image must be a short hook phrase "
        "taken from the title (2-4 words ONLY, ALL-CAPS, correctly spelled). No real logos, no real people's "
        "faces, no watermark, no extra text besides the hook phrase. Return only the image.")

    def _save_image(out, tag):
        from PIL import Image
        for part in out["candidates"][0]["content"]["parts"]:
            d = part.get("inlineData") or part.get("inline_data")
            if not d:
                continue
            img = base64.b64decode(d["data"])
            tmp = os.path.join(workdir, "_thumb_ai.png")
            open(tmp, "wb").write(img)
            im = Image.open(tmp).convert("RGB")
            # normalize any aspect ratio to 1280x720 (crop-then-cover)
            tw, th = 1280, 720
            sc = max(tw / im.width, th / im.height)
            im = im.resize((round(im.width * sc), round(im.height * sc)), Image.LANCZOS)
            x = (im.width - tw) // 2
            y = (im.height - th) // 2
            im = im.crop((x, y, x + tw, y + th))
            f = os.path.join(workdir, "thumb.jpg")
            im.save(f, quality=88)
            if os.path.getsize(f) > 2 * 1024 * 1024:
                im.save(f, quality=72)
            print(f"thumb: AI-generated OK ({tag})", flush=True)
            return f
        return None

    def _is_quota_err(msg):
        return ("429" in msg or "RESOURCE_EXHAUSTED" in msg or " 403" in msg
                or "PERMISSION_DENIED" in msg)

    def _attempt(model, key):
        mods = ["TEXT", "IMAGE"] if "preview" in model else ["IMAGE"]
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                           "generationConfig": {"responseModalities": mods}}).encode()
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=body, headers={"Content-Type": "application/json",
                                "x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=180) as r:
            out = json.load(r)
        return _save_image(out, f"{model}, key#{GEMINI_KEYS.index(key)+1}")

    # first pass: every (model, key) combination; on a quota error rotate keys
    # immediately, on other errors move to the next model
    for model in THUMB_AI_MODELS:
        for ki, key in enumerate(GEMINI_KEYS):
            try:
                f = _attempt(model, key)
                if f:
                    return f
                print(f"thumb-ai {model} key{ki+1}/{len(GEMINI_KEYS)}: no image in response", flush=True)
                break
            except Exception as ex:
                msg = str(ex)[:90]
                print(f"thumb-ai {model} key{ki+1}/{len(GEMINI_KEYS)}: {msg}", flush=True)
                if _is_quota_err(msg):
                    continue  # quota hit -> next key takes over instantly
                break  # non-quota error -> next model
    # second pass with backoff: image-model free quota is rate-limited and 429s
    # are usually transient; wait and sweep all keys/models once more
    for wait in (45, 90):
        time.sleep(wait)
        for model in THUMB_AI_MODELS:
            for ki, key in enumerate(GEMINI_KEYS):
                try:
                    f = _attempt(model, key)
                    if f:
                        return f
                except Exception as ex:
                    print(f"thumb-ai retry {model} key{ki+1}: {str(ex)[:90]}", flush=True)
    return None



def _hook_phrase(title):
    """Extract a 2-4 word ALL-CAPS punch phrase from the title (thumbnail text)."""
    import re
    words = re.findall(r"[A-Za-z0-9']+", title)
    stop = {"the", "a", "an", "of", "in", "on", "is", "are", "this", "that", "just",
            "its", "it", "to", "for", "with", "and", "after", "now", "new", "has",
            "have", "was", "by", "at", "from", "will", "why", "how", "what"}
    keep = [w for w in words if w.lower() not in stop]
    hook_words = {"shocking", "warning", "banned", "solved", "scientists",
                  "impossible", "never", "secret", "truth"}
    if not any(w.lower() in hook_words for w in keep):
        for w in words:
            if w.lower() in hook_words:
                keep.append(w)
                break
    phrase = " ".join(keep[:4]).upper()
    return phrase or title.upper()[:28]


def make_thumb(e, workdir, clip):
    """Cinematic PIL fallback thumbnail (owner 2026-10-07): pick the most striking
    frame from the beat-1 clip, grade it, overlay a BIG 2-4 word hook phrase.
    Fully free, no AI quota needed."""
    import subprocess
    src_f = os.path.join(FOOTAGE, clip["file"])
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageStat

    # 1) grab candidate frames and pick the most striking (bright + colorful)
    cand = []
    for frac in (0.15, 0.30, 0.45, 0.60, 0.75, 0.90):
        t = clip["dur"] * frac
        fp = os.path.join(workdir, f"_thumb_c{len(cand)}.jpg")
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
                            "-i", src_f, "-frames:v", "1", fp], check=False)
        if r.returncode == 0 and os.path.exists(fp):
            cand.append(fp)
    if not cand:
        return None
    best, best_score = None, -1.0
    for fp in cand:
        im = Image.open(fp).convert("RGB").resize((160, 90))
        stat = ImageStat.Stat(im)
        bright = sum(stat.mean) / 3.0
        sat = sum(stat.stddev) / 3.0
        score = bright * 0.6 + sat * 1.2
        if score > best_score:
            best, best_score = fp, score
    im = Image.open(best).convert("RGB")

    vertical = e.get("kind") == "short"
    TW, TH = (1080, 1920) if vertical else (1280, 720)
    im = im.resize((TW, TH), Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.18)
    im = ImageEnhance.Color(im).enhance(1.32)
    im = ImageEnhance.Brightness(im).enhance(1.06)

    # subtle cinematic vignette
    d = ImageDraw.Draw(im, "RGBA")
    for i in range(90):
        a = int(2.2 * i)
        d.rectangle([i * 4, i * 4, TW - i * 4, TH - i * 4],
                    outline=(0, 0, 0, a), width=4)

    # dark gradient band bottom for text legibility
    band_top = int(TH * (0.42 if vertical else 0.52))
    for y in range(band_top, TH):
        a = int(210 * ((y - band_top) / (TH - band_top)) ** 1.2)
        d.line([(0, y), (TW, y)], fill=(8, 8, 12, a))

    # 2) BIG hook phrase (2-4 words), auto-fit up to 2 lines
    phrase = _hook_phrase(e["title"])
    fpath = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    maxw = TW - 96
    f_big = None
    for size in range(150, 54, -6):
        f_try = ImageFont.truetype(fpath, size)
        probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        w = probe.textlength(phrase, font=f_try)
        if w <= maxw:
            f_big = f_try
            break
        # try two lines
        ws = phrase.split()
        mid = len(ws) // 2
        for split in (mid, mid - 1, mid + 1):
            if 0 < split < len(ws):
                l1, l2 = " ".join(ws[:split]), " ".join(ws[split:])
                if (probe.textlength(l1, font=f_try) <= maxw
                        and probe.textlength(l2, font=f_try) <= maxw):
                    phrase = l1 + "\n" + l2
                    f_big = f_try
                    break
        if f_big:
            break
    if f_big is None:
        f_big = ImageFont.truetype(fpath, 60)
    tlines = phrase.split("\n")
    lh = int(f_big.size * 1.12)
    y0 = TH - 74 - lh * len(tlines)
    for li, line in enumerate(tlines):
        y = y0 + li * lh
        d.text((48, y), line, font=f_big, fill=(255, 255, 255),
               stroke_width=10, stroke_fill=(0, 0, 0))

    # brand bar + label
    f_med = ImageFont.truetype(fpath, 34)
    d.rectangle([48, 56, 216, 68], fill=(255, 55, 55))
    d.text((48, 78), "NEXTAI VISION", font=f_med, fill=(255, 255, 255),
           stroke_width=3, stroke_fill=(0, 0, 0))

    out = os.path.join(workdir, "thumb.jpg")
    im.convert("RGB").save(out, quality=90)
    for fp in cand:
        try:
            os.remove(fp)
        except OSError:
            pass
    print(f"thumb: cinematic PIL fallback OK (hook: {phrase!r})", flush=True)
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


def upload(e, mp4, publish_at=None, playlist_link=None):
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
    if playlist_link:
        desc = desc + "\n\nMore deep dives: " + playlist_link
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
        if not make_thumb_ai(e, workdir):
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


# ---------- owner channel curation (2026-10-06 review) ----------

ABOUT_TEXT = (
    "Your daily window into the future of artificial intelligence. NextAI Vision 4 "
    "decodes the biggest moves in AI: new model launches and updates from OpenAI/ChatGPT, "
    "Anthropic/Claude, Google Gemini, Grok/xAI, DeepSeek and Qwen, plus AI science, "
    "robotics and deep-dive tech analysis. New explainers every day: what launched, "
    "why it matters, and what it changes for you.\n\n"
    "Topics: AI news, ChatGPT, OpenAI, Claude, Anthropic, Gemini, Google AI, Grok, xAI, "
    "DeepSeek, Qwen, artificial intelligence, machine learning, LLM, AI models, robotics, "
    "AI science, tech analysis, AI leaks, future tech, AI updates today.")

PLAYLIST_DEFS = [
    ("OpenAI & ChatGPT Breakthroughs",
     ["chatgpt", "openai", "gpt", "sam altman"],
     "OpenAI and ChatGPT breakthroughs, launches and updates - explained."),
    ("Claude & Anthropic Updates",
     ["claude", "anthropic"],
     "Claude and Anthropic model updates, warnings and launches - explained."),
    ("Gemini & Google AI Ecosystem",
     ["gemini", "google", "deepmind"],
     "Gemini, Google AI Studio and DeepMind updates - explained."),
    ("AI Controversy & Tech Leaks",
     ["leak", "leaks", "leaked", "ban", "bans", "banned", "warning", "warnings",
     "controversy", "controversies", "secret", "shock", "shocks", "shocked",
     "shocking", "dispute", "disputes", "ipo", "panic"],
     "AI controversies, leaked documents, bans and shocking warnings."),
    ("AI Science & Robotics",
     ["robot", "scientist", "science", "nobel", "lab", "doctor", "health",
      "heart", "planet", "nasa", "voice", "clone", "breathing", "walk"],
     "AI science breakthroughs, health-AI and robotics - explained."),
]


def _yt(kind_method, params, body=None):
    tok = get_token()
    url = ("https://www.googleapis.com/youtube/v3/" + kind_method + "?"
          + urllib.parse.urlencode(params))
    # FIX 2026-10-06: v3 .update endpoints (videos.update, channels.update)
    # reject POST with an empty 404; .insert endpoints require POST.
    if body is not None:
        method = "PUT" if kind_method in ("videos", "channels") else "POST"
    else:
        method = "GET"
    req = urllib.request.Request(url, method=method,
                                 headers={"Authorization": "Bearer " + tok["access_token"],
                                          "Content-Type": "application/json"})
    if body is not None:
        req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as ex:
        raise RuntimeError(f"YT_{ex.code}: " + ex.read().decode(errors="replace")[:200])


def update_channel_about():
    """Rewrite the channel About/description to the AI-tech theme (owner 2026-10-06)."""
    me = _yt("channels", {"part": "brandingSettings", "mine": "true"})
    items = me.get("items", [])
    if not items:
        raise RuntimeError("YT_NO_CHANNEL")
    cid = items[0]["id"]
    ch = items[0]["brandingSettings"]["channel"]
    # channels.update does NOT accept part=snippet; the About text lives in
    # brandingSettings.channel.description (owner About 2026-10-06, verified live).
    body = {"id": cid, "brandingSettings": {"channel": {
        "title": ch.get("title", "NextAI Vision 4"),
        "description": ABOUT_TEXT,
        "keywords": "AI news, ChatGPT, OpenAI, Claude, Anthropic, Gemini, "
                    "Google AI, Grok, DeepSeek, Qwen, artificial intelligence, "
                    "machine learning, LLM, AI models, robotics, AI science, "
                    "tech analysis, AI leaks, future tech, AI updates",
    }}}
    _yt("channels", {"part": "brandingSettings"}, body)
    print("channel about: UPDATED (AI/tech keywords + tagline)", flush=True)
    return True


_BENGALI_RE = _re.compile(r"[\u0980-\u09FF]")
_OLD_ERA_RE = _re.compile(
    r"cartoon|funny|village|moral story|emotional|grandma|grandpa|"
    r"animal|#foryou|#trending|short story|shorts story", _re.I)

def playlist_for_title(title):
    """Strict topic matcher: whole-word English keyword hit only.
    Old-era Bangla/cartoon uploads must NEVER be filed (learned 2026-10-06:
    substring match put 100+ cartoon shorts inside the AI playlists)."""
    if _BENGALI_RE.search(title) or _OLD_ERA_RE.search(title):
        return None
    t = title.lower()
    for name, kws, _d in PLAYLIST_DEFS:
        for k in kws:
            if _re.search(r"\b" + _re.escape(k) + r"\b", t):
                return name
    return None


def ensure_playlists():
    """Create the topic playlists once, cache their ids in state.json."""
    st = load_state()
    pls = st.get("playlists", {})
    for name, _kws, desc in PLAYLIST_DEFS:
        if name not in pls:
            out = _yt("playlists", {"part": "snippet,status"},
                      {"snippet": {"title": name, "description": desc},
                       "status": {"privacyStatus": "public"}})
            pid = out.get("id")
            if not pid:
                raise RuntimeError("PLAYLIST_CREATE_FAILED: " + name)
            pls[name] = pid
            print(f"playlist created: {name} ({pid})", flush=True)
    st["playlists"] = pls
    save_state(st)
    return pls


def add_to_playlist(vid, title):
    """File an uploaded Long into its matching topic playlist (guarded, non-fatal)."""
    try:
        name = playlist_for_title(title)
        if not name:
            return None
        pls = ensure_playlists()
        pid = pls.get(name)
        if not pid:
            return None
        # dup guard (2026-10-06: re-filing created duplicates in live playlists)
        try:
            cur = _yt("playlistItems", {"part": "snippet", "playlistId": pid,
                                        "videoId": vid, "maxResults": "1"})
            if cur.get("items"):
                return None
        except Exception:
            pass
        _yt("playlistItems", {"part": "snippet"},
            {"snippet": {"playlistId": pid,
                         "resourceId": {"kind": "youtube#video", "videoId": vid}}})
        print(f"playlist: {title[:40]} -> {name}", flush=True)
        return f"https://www.youtube.com/playlist?list={pid}"
    except Exception as ex:
        print("playlist add skipped: " + str(ex)[:120], flush=True)
        return None


def make_short_from_long(mp4, workdir, secs=42, start=0):
    """OWNER RULE 2026-10-06 (revised 09:19): cut the Long's strongest ~40s into a
    vertical 9:16 Short. start=0 = hook zone (1st Short), start=45 = second
    segment (2nd Short of the 2-day Long cycle). Returns the short mp4 path."""
    out = os.path.join(workdir, f"short_{start}.mp4")
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-t", str(secs), "-i", mp4,
         "-vf", "crop='ih*9/16':ih,scale=1080:1920,setsar=1",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", out], capture_output=True, text=True)
    if r.returncode or not os.path.exists(out):
        raise RuntimeError("SHORT_CUT_FAILED: " + (r.stderr or "")[-200:])
    print(f"short cut: OK {secs}s vertical 1080x1920", flush=True)
    return out


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
    if not make_thumb_ai(e, workdir):
        print("thumb: AI unavailable; using footage-frame fallback", flush=True)
        make_thumb(e, workdir, clips[0][0])
    result = {"id": e["id"], "date": today, "status": "rendered", "file": mp4}
    try:
        publish_at, slot_local = next_bd_slot(kind)
        print(f"scheduled slot (BD): {slot_local}", flush=True)
        vid = upload(e, mp4, publish_at)
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
