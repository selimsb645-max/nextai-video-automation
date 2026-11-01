#!/usr/bin/env python3
"""NextAI Content Factory — GitHub Actions autonomous runner.

Runs a full production turn on free infrastructure only:
Google News RSS + Gemini free-tier API (topic + script), Pexels free API
(fresh per-video footage, owner rule 2026-10-04; bundled pool as fallback),
local Kokoro TTS (af_heart, emotion-aware), ffmpeg render with quality
gates, YouTube Data API v3 private publishAt upload 8-10h ahead.
No Base44 credits involved: keeps videos running when the agent is gone.

Follower design (no duplicate uploads): this runner fires ~40 minutes AFTER
the Base44 agent's own production time. Before producing it checks the
YouTube channel's already-scheduled upcoming uploads; if the target slot is
filled by anyone (Base44 producer or an earlier run) it skips. When the
Base44 producer dies, slots stay empty and this runner fills them.

Usage:
  python3 actions/runner.py --kind long            # normal production turn
  python3 actions/runner.py --kind long --selftest # full pipeline, NO upload
"""
import argparse
import base64
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACT = os.path.join(REPO, "factory")
sys.path.insert(0, FACT)
import factory  # noqa: E402  (loads library.json + content_policy.json at import)

BD = ZoneInfo("Asia/Dhaka")
UTC = _dt.timezone.utc

# Key pool (owner 2026-10-07): GEMINI_API_KEY may hold a comma-separated
# list of keys from separate projects; extra keys in GEMINI_API_KEY_2.._9.
# On a 429 quota hit we rotate to the next key immediately.
_raw_keys = [k.strip() for k in os.environ.get("GEMINI_API_KEY", "").split(",") if k.strip()]
for _i in range(2, 10):
    _extra = os.environ.get(f"GEMINI_API_KEY_{_i}", "")
    _raw_keys += [k.strip() for k in _extra.split(",") if k.strip()]
GEMINI_KEYS = list(dict.fromkeys(_raw_keys))
GEMINI_KEY = GEMINI_KEYS[0] if GEMINI_KEYS else ""
GEMINI_MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_MODELS", "gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-3.5-flash,gemini-flash-latest,gemini-3.8-flash").split(",") if m.strip()]
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "").strip()
YT_TOKEN_JSON = os.environ.get("YT_TOKEN_JSON", "").strip()
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_REPO = os.environ.get("GITHUB_REPOSITORY", "")
GH_BRANCH = os.environ.get("GITHUB_REF_NAME", "") or "main"

HOOKS = ["shocking", "warning", "banned", "solved", "scientists",
         "impossible", "nobel", "doctors", "just happened",
         "never", "survives", "robot",
         # commentary/story hooks (owner 2026-10-12: longs follow the
         # Farid Talks AI news-commentary style)
         "built", "truth", "nobody", "finally", "vs", "exposed",
         # legacy tutorial hooks still allowed occasionally
         "pro", "free", "guide", "hack", "just became", "killed"]
USED_F = os.path.join(FACT, "used_footage.json")
REPORTS = os.path.join(REPO, "actions", "reports")


def log(msg):
    print(msg, flush=True)


_UA = ("NextAI-Factory/1.0 (+https://github.com/selimsb645-max/"
       "nextai-video-automation)")


def _http(url, headers=None, data=None, method=None, timeout=90):
    hdrs = dict(headers or {})
    # Pixabay answers 403 to a bare python-urllib UA (tonight's footage fell
    # back to the bundled pool because every search was rejected), so always
    # identify the client.
    hdrs.setdefault("User-Agent", _UA)
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- YouTube
def restore_token():
    if not YT_TOKEN_JSON:
        raise SystemExit("YT_TOKEN_JSON secret missing")
    f = os.path.join(REPO, "yt-auth", "token_nextai.json")
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "w") as fh:
        fh.write(YT_TOKEN_JSON)
    return f


def _yt(tok, path):
    out = json.loads(_http(
        "https://www.googleapis.com/youtube/v3/" + path,
        headers={"Authorization": "Bearer " + tok["access_token"]}))
    return out


def slot_taken_on_youtube(publish_at):
    """Cross-producer duplicate guard: is the target slot already scheduled?

    Reads the channel's recent uploads (private scheduled videos included for
    the authenticated owner) and checks publishAt values near the target.
    """
    try:
        tok = factory.get_token()
        ch = _yt(tok, "channels?part=contentDetails&mine=true")
        upl = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        pl = _yt(tok, "playlistItems?part=contentDetails&maxResults=15&playlistId=" + upl)
        ids = [it["contentDetails"]["videoId"] for it in pl.get("items", [])]
        if not ids:
            return False
        vs = _yt(tok, "videos?part=status&id=" + ",".join(ids))
        target = _dt.datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
        for v in vs.get("items", []):
            pa = v["status"].get("publishAt")
            if not pa:
                continue
            when = _dt.datetime.fromisoformat(pa.replace("Z", "+00:00"))
            if abs((when - target).total_seconds()) <= 45 * 60:
                log(f"slot {publish_at} already has scheduled video {v['id']} "
                    f"(publishAt {pa}) — skipping, no duplicate")
                return True
    except Exception as ex:
        # Read-only guard: on failure be conservative only for the *upload*
        # stage; the strict repo-log guard in factory.next_bd_slot still runs.
        log("slot check warning (continuing; repo log still guards): " + str(ex)[:160])
    return False


# ---------------------------------------------------------------- research
def news_headlines(kind="long"):
    """Free topic research: Google News RSS, last 7 days, US edition.
    kind="short" -> robot-only feed (owner 2026-10-07 21:46 BD: the
    standalone 18:30 BD Shorts are robot videos, casperpks-style)."""
    robot_queries = [
        "humanoid robot milestone",
        "robot dog OR robotaxi OR robot competition news",
        "Figure OR Tesla Optimus OR Boston Dynamics robot update",
        "robotics breakthrough demonstration",
        "AI robot technology update",
    ]
    queries = robot_queries if kind == "short" else [
        "ChatGPT OR OpenAI AI update",
        "Anthropic Claude AI update",
        "Gemini OR Google AI Studio update",
        "Grok OR xAI AI update",
        "DeepSeek AI model release",
        "Qwen AI model release",
        "new AI model launch",
        "AI science discovery breakthrough",
        "AI robot technology update",
        "artificial intelligence technology news",
    ]
    items = []
    for q in queries:
        url = ("https://news.google.com/rss/search?q=" +
               urllib.parse.quote(q) + "+when:7d&hl=en-US&gl=US&ceid=US:en")
        try:
            xml = _http(url, timeout=30).decode("utf-8", "replace")
        except Exception as ex:
            log(f"rss failed for {q[:30]}: {str(ex)[:80]}")
            continue
        for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
            blk = m.group(1)
            t = re.search(r"<title>(.*?)</title>", blk, re.S)
            l = re.search(r"<link>(.*?)</link>", blk, re.S)
            d = re.search(r"<pubDate>(.*?)</pubDate>", blk, re.S)
            if t and l:
                items.append({"title": re.sub(r"<[^>]+>", "", t.group(1)).strip(),
                              "url": l.group(1).strip(),
                              "date": d.group(1).strip() if d else ""})
        time.sleep(1)
    # newest first, dedup by title
    seen, out = set(), []
    for it in items:
        k = it["title"].lower()[:60]
        if k not in seen:
            seen.add(k)
            out.append(it)
    log(f"research: {len(out)} fresh US headlines (7d)")
    return out[:150]


def demand_counts(items):
    """Free search-demand proxy: how many fresh US headlines (last 7 days)
    mention each AI topic cluster. The video is made on the most-searched one."""
    keys = {
        "ChatGPT/OpenAI": ("chatgpt", "openai", "gpt-", "sam altman"),
        "Claude/Anthropic": ("claude", "anthropic"),
        "Gemini/AI Studio": ("gemini", "ai studio", "deepmind"),
        "Grok/xAI": ("grok", "xai"),
        "DeepSeek": ("deepseek",),
        "Qwen": ("qwen",),
        "AI science": ("science", "discovery", "breakthrough", "physics", "biology", "research"),
        "AI robots": ("robot", "humanoid", "drone"),
        "AI technology": ("chip", "gpu", "nvidia", "semiconductor", "quantum", "smartphone", "gadget"),
    }
    counts = {}
    for name, kws in keys.items():
        counts[name] = sum(1 for it in items
                           if any(k in it["title"].lower() for k in kws))
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def gemini_json(prompt, models=None):
    """Gemini free-tier call returning parsed JSON.

    Retries across models and rounds: transient 503 (model under high
    demand) is the normal failure mode on the free tier, so we back off
    and try again rather than failing the run.
    """
    if not GEMINI_KEY:
        return None
    models = models or GEMINI_MODELS
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"},
    }).encode()
    for rnd in range(4):
        for model in models:
            for ki, key in enumerate(GEMINI_KEYS):
                try:
                    out = json.loads(_http(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                        headers={"Content-Type": "application/json",
                                 "x-goog-api-key": key},
                        data=body))
                    txt = out["candidates"][0]["content"]["parts"][0]["text"]
                    m = re.search(r"\{.*\}", txt, re.S)
                    if m:
                        val = json.loads(m.group(0))
                        log(f"gemini: OK model={model} key#{ki + 1} (round {rnd + 1})")
                        return val
                except urllib.error.HTTPError as ex:
                    if ex.code == 429 and ki + 1 < len(GEMINI_KEYS):
                        log(f"gemini {model}: 429 quota on key#{ki + 1}; rotating to key#{ki + 2}")
                        continue
                    if ex.code in (429, 500, 502, 503, 504):
                        log(f"gemini {model} busy/transient ({ex.code}); retrying")
                        time.sleep(12)
                        break
                    log(f"gemini {model} failed: {str(ex)[:120]}")
                    break
                except Exception as ex:
                    log(f"gemini {model} failed: {str(ex)[:120]}")
                    break
        time.sleep(10)
    return None


# ── OWNER 2026-11-01 v2 (Task 4): start with 8-10 minute test longs (~1300 words)
# and only raise the length once YouTube retention data proves viewers stay.
# 150 wpm: 1600 words ~ 10-11 min, matching the @airevolutionx reference length
# (owner standing rule: 10-16 min). LONG_TARGET_WORDS=2200+ for a longer cut.
LONG_TARGET_WORDS = int(os.environ.get("LONG_TARGET_WORDS", "1600"))
LONG_MAX_BEATS = int(os.environ.get("LONG_MAX_BEATS", "52"))
LONG_MIN_WORDS = int(LONG_TARGET_WORDS * 0.65)
LONG_MAX_WORDS = int(LONG_TARGET_WORDS * 1.15)

ENTRY_PROMPT = """You are the topic researcher and script writer for a US-audience English YouTube channel about AI (NextAI Vision). OWNER RULE 2026-10-12: the TOPICS stay the same — videos cover ALL types of AI: ChatGPT/OpenAI, Claude/Anthropic, Gemini/Google AI Studio, Grok/xAI, DeepSeek, Qwen, and EVERY other AI company, platform, tool, model or AI technology; also AI-linked science discoveries and robots. ONLY the PRESENTATION STYLE follows the channel "AI Revolution" (youtube.com/@airevolutionx, OWNER REFERENCE 2026-11-01, ~576K subs): cinematic DOCUMENTARY-style AI news storytelling — a confident professional English voice-over that explains each breakthrough, and EVERY SENTENCE is illustrated by its own distinctive real footage / cinematic B-roll of exactly what is being said at that moment. Momentum and tension throughout, no filler, no tutorial tone, no listicle.
From the headlines below pick exactly ONE real, currently-trending topic (last 7 days, US-interest). Allowed pillars, in priority order: (1) AI updates and NEW MODEL LAUNCHES from ChatGPT/OpenAI, Claude/Anthropic, Gemini/Google AI Studio, Grok/xAI, DeepSeek, Qwen — ANY AI update from ANY AI company counts; (2) AI-linked science discoveries; (3) robots and new AI technology. NEVER medical advice, no politics, no tragedy exploitation.
SELECTION RULE: the DEMAND COUNTS below show how many US headlines each topic cluster got in the last 7 days — this is the search-demand evidence. Pick a topic from the cluster with the HIGHEST count that still has one strong, specific story. PREFER stories with NARRATIVE DRAMA: someone built/released something bold, a ban, a feud, a record, an exposure, a plot twist, a big name doing something unexpected (e.g. "a YouTuber built an uncensored AI and OpenAI banned him twice"). Plain feature launches are second choice.
OWNER DATA 2026-10-11: robotics real-test/lab-demo stories and side-by-side AI model comparisons are this channel's best performers — when demand counts are close, pick one of those angles.

SCRIPT FORMAT — an AI news story told by a real host:
- First-person, conversational, contractions everywhere, short punchy sentences, occasional wit. Talk TO one viewer ("you"), react to the story ("Here's the funny part", "Now this is where it gets weird", "And yes, you heard that right").
- Narration: total {words} words, split into about {beats} beats (each 26-38 words). This is a 10-16 minute documentary: go deep, never pad or repeat.
- Beat 1 (10-14 seconds, cold open): the hook in one breath — the boldest concrete fact or number AND the name at the center of the drama. No greetings, no "in this video".
- Beats 2-3 (fast hook zone, max ~50 words total): what just happened + the single most surprising fact. Then the ROADMAP in one curiosity-framed sentence: "Today we'll look at what X actually is, why Y happened, and what it means for you."
- Beat 4 (channel stamp, ~12 words): one line naming today's real date and the channel, e.g. "It's October 12th, and you're watching NextAI Vision."
- Middle beats (26-38 words each): tell the STORY chronologically — what happened, who said what, how it escalated; then explain the one technical bit simply enough for a beginner; weave in specific numbers, dates and model names wherever the sources give them.
- QUOTES: include at least ONE short real quote from the story as reported in the headlines/snapshots, introduced naturally ("he said, quote, ..."). Cite at least ONE named source or outlet ("according to ...").
- WIT: 1-3 light humorous asides per video — playful, never cruel, never cringe, family-safe.
- PAYOFF: keep the best twist, reveal or resolution for the FINAL THIRD so viewers stay to the end.
- Last two beats: a short ironic callback or "one more thing" twist if the story has one, then END with a comment question tied to the story ("Tell me in the comments: ...") and a quick sign-off ("See you in the next one.").
- {lessons}
- OWNER DATA 2026-10-11: average view duration on 5-min longs is only 57s — assume viewers decide in the first 30 seconds; nothing slow, nothing generic, no throat-clearing before the surprise.

HARD RULES:
- Title: MAX 50 CHARACTERS (mobile viewers must read the full message at a glance), must contain "AI" or the platform/company name AND one of these story-drama hook patterns: Banned / Built / Just / Shocking / Warning / Nobody / Truth / Finally / vs.
- TITLE SEARCHABILITY (owner 2026-10-16: 70% of views come from SEARCH, and drama-only titles rank for nothing): the title MUST contain the exact SEARCHABLE SUBJECT NAME a viewer would actually type into YouTube/Google — the model name (e.g. "GPT-5.1", "Claude Opus 4.5", "Gemini 3"), the company name, the robot name, or the law/event name — spelled EXACTLY as in the headlines. GOOD: "Claude Opus 4.5 Just Beat GPT-5.1", "Tesla Optimus Banned Itself". BAD: "AI Agent Hacked a Government. Nobody Told It To" (no searchable subject, nobody searches this).
- TITLE PATTERNS that work (pick the best fit, never the same one twice in a row): "<Name> Built an AI. <Company> Banned Him.", "X Just Happened — Here's Why It Matters", "The Truth About X", "X Banned Y. Here's Why.", "Nobody Expected This From X", "X vs Y: It's Not Even Close", "<Company> Just <Dramatic Claim>" (e.g. "Anthropic Just Dropped DUET: The First AI That Thinks Ahead"), "It's Happening... <Consequence>".
- TITLE VARIETY: do NOT reuse the same title template (like "AI Warning: ...") that appears in the RECENT TITLES list; at most one title there shares its first two words with yours.
- FOOTAGE SYNC (OWNER RULE 2026-11-01): the video is narrated sentence by sentence and each sentence is SHOWN. Every beat gets its own DIFFERENT piece of footage that depicts exactly what that sentence says — never a generic clip, never the same clip twice in one video.
- Each beat gets "kw": a 2-4 word stock-footage search phrase naming a CONCRETE filmable object/place/action that matches what the sentence says (e.g. "server room lights", "robot arm factory", "person typing laptop", "computer chip macro"). NEVER brand or product names (ChatGPT, Claude, OpenAI, Gemini, DeepSeek...) and NEVER abstract words (future, intelligence, innovation) — stock libraries do not have them, so the footage would not match the words.
- verified_sources: 1-3 URLs copied EXACTLY from the headline list that support the topic.

DEMAND COUNTS (US headlines, last 7 days):
{demand}

RECENT TITLES (avoid similar phrasing/templates):
{recent}

HEADLINES:
{headlines}

Output STRICT JSON only, no markdown fences:
{{"id":"snake_case_topic_{today}","subject":"exact searchable subject name from the headlines","title":"...","description":"FIRST LINE must contain the subject name plus 1-2 exact phrases people search (e.g. 'Claude Opus 4.5 review', what happened, and why it matters), then 1-2 more sentences with search keywords","tags":["12 short search keywords, FIRST one = the subject name verbatim"],"narration":"full narration text","beats":[{{"t":"beat text","kw":"footage phrase"}}],"verified_sources":["url"],"demand_evidence":"one line: which headline and why now"}}"""


CONTINUE_PROMPT = """You are continuing a US-audience YouTube AI news commentary (cinematic documentary style like "AI Revolution" (@airevolutionx)). Write the NEXT {n} beats (each 26-38 words) that CONTINUE the story from where it stops — do not repeat earlier text. Keep the drama escalating toward the final-third payoff. Every beat gets a 2-4 word "kw" stock-footage search phrase. Return ONLY JSON: {{"beats":[{{"t":"<sentence>","kw":"<footage phrase>"}}]}}.

TITLE: {title}
STORY SO FAR (all beats in order):
{sofar}
"""


EXPAND_PROMPT = """You are expanding a US-audience YouTube AI news commentary (cinematic documentary host style). Rewrite EVERY beat below to be 26-38 words each (add concrete detail, numbers, quotes — keep the same meaning, order and tone). Keep exactly the same number of beats and each "kw" phrase. COUNT WORDS per beat: fewer than 30 is invalid. Return ONLY JSON: {{"beats":[{{"t":"...","kw":"..."}}]}}.

TITLE: {title}
BEATS TO EXPAND:
{beats}"""


SHORT_PROMPT = """
You are the script writer for a US-audience English YouTube SHORT (vertical, under 60 seconds) that MUST be about REAL ROBOTS. Style (owner reference 2026-10-11: @androidalians): ONE robot, ONE dramatic STORY told like a mini-movie, poster-style visuals, impossible to scroll past. From the headlines below pick exactly ONE real, currently-trending robot story (last 7 days, US-interest) about ONE SPECIFIC NAMED ROBOT (a specific humanoid, robot dog, drone swarm, or competition robot - use its real model name). NEVER medical advice, no politics, no tragedy exploitation. If no robot headline is trending, pick the most visually dramatic recent robot milestone instead.

STORY STRUCTURE (a mini-movie, NOT a news report):
- Beat 1 (FIRST 3 SECONDS = the whole game: 2026 Shorts rank on swipe-away rate, target <25% leave): a pattern-interrupt cold open, MAX 10 words, ON the single most shocking NUMBER or event, stated as a claim that creates a question ("Renting a real humanoid robot now costs $40 a day." / "This robot just lost its leg on stage."). NEVER start with "Tesla just..." style vague setups, never a greeting, never context first.
- Middle beats: the STORY of how it happened - escalate beat by beat, present tense, short punchy sentences.
- Final beat: the payoff + ONE short closing question that makes people COMMENT (a two-option question works best: "Real or hype? Comment below."). Narration should loop naturally - the last words should flow back into the first line so replays count as engaged views.
- Fun, high-energy storytelling tone. Emotional punctuation. Hold the payoff to the END.

HARD RULES:
- Title: MAX 50 CHARACTERS. DATA-PROVEN FORMULA (our best Short: "Humanoid Robots Now Rent for $40 a Day" = 140 views vs 2-6 for generic titles): lead with ONE concrete SURPRISING NUMBER or price or comparison, plus the robot/subject word. Good: "Robots Now Rent for $40 a Day", "This Robot Lost a Leg Mid-Kick", "Unitree Boss: 80% of Jobs by 2028". Bad (never write): generic "Shocking Robot ...", "Tesla Robot Shocking 2027 Launch", vague hype with no number or specific event. A hook word (Banned/Never/Impossible/Lost/Cost) is optional - the number or specific event is mandatory.
- headline: 2-4 ALL-CAPS poster words that carry the NUMBER or the shocking event itself (e.g. "$40 A DAY", "LOST A LEG", "80% BY 2028"), not a generic label. It gets burned BIG on screen.
- specs: 2-3 VERY short poster facts about THIS robot, each MAX 14 CHARACTERS, numbers preferred (e.g. ["120 KG", "21 KM", "50 MIN"]).
- narration: 70-120 words total (about 35-50 seconds spoken), story-style.
- beats: 4-7 items, each {{"t":"<one spoken sentence, max 16 words>","kw":"<CONCRETE filmable robot-action scene - keep the SAME robot type in every beat for visual continuity, never brand names, never abstract words>"}}. Every beat gets its own unique footage.
- Example JSON: {{"id":"snake_case_robot_short_{today}","subject":"exact searchable subject (robot name, e.g. Tesla Optimus / Figure 02, or 'humanoid robot')","title":"...","headline":"...","specs":["...","..."],"description":"FIRST LINE must name the robot/subject + what it did (searchable), then 1-2 more sentences, + 'Related searches:' line with 5 tags","tags":["8 short search keywords"],"narration":"short narration text","beats":[{{"t":"beat text","kw":"robot footage phrase"}}],"verified_sources":["url"],"demand_evidence":"one line: which headline and why now"}}
- verified_sources: 1-2 headline URLs that prove the story.
- id: short slug containing the topic and today's date.
Return ONLY the JSON object.

TODAY: {today}
DEMAND COUNTS: {demand}
RECENT TITLES (do not repeat their templates):
{recent}
HEADLINES:
{headlines}
"""


def _grow_to_target(val):
    """Grow a long script to LONG_TARGET_WORDS. Moved out of make_entry
    on 2026-11-01 so the anchored fallback grows a script identically."""
    # OWNER MASTER PROMPT 2026-11-01: a long must reach LONG_TARGET_WORDS
    # (10-16 min). Free lite models cap ~300-400 words per call, so keep
    # asking for the next beats until the target is reached, then expand
    # any beat that is still short.
    if 8 <= len(val.get("beats", [])):
        for _ci in range(14):
            _w = len(val["narration"].split())
            _b = len(val["beats"])
            if _w >= LONG_TARGET_WORDS or _b >= LONG_MAX_BEATS:
                break
            _room = min(10, LONG_MAX_BEATS - _b)
            if _room <= 0:
                break
            so_far = "\n".join(f"- {b['t']}" for b in val["beats"][-12:])
            val2 = gemini_json(CONTINUE_PROMPT.format(
                n=_room, title=val["title"], sofar=so_far),
                models=["gemini-flash-lite-latest", "gemini-3.5-flash-lite"])
            if not val2 or not isinstance(val2.get("beats"), list):
                break
            add = [b for b in val2["beats"] if b.get("t") and b.get("kw")][:_room]
            if not add:
                break
            val["beats"] += add
            val["narration"] = " ".join(b["t"] for b in val["beats"])
            log(f"continuation: +{len(add)} beats, now {len(val['narration'].split())} words")
        # still short -> thicken every beat to 30-38 words.
        # Stop at 90% of the target: expanding a script that already
        # reached it produced a 1945-word script for a 1300-word target.
        for _ei in range(2):
            if len(val["narration"].split()) >= LONG_TARGET_WORDS * 0.9:
                break
            _bt = "\n".join(f"- {b['t']} |kw: {b.get('kw', '')}"
                            for b in val["beats"])
            val3 = gemini_json(EXPAND_PROMPT.format(
                title=val["title"], beats=_bt),
                models=["gemini-flash-lite-latest", "gemini-3.5-flash-lite",
                        "gemini-3.5-flash"])
            if val3 and isinstance(val3.get("beats"), list) \
                    and len(val3["beats"]) == len(val["beats"]) \
                    and all(b.get("t") for b in val3["beats"]):
                val["beats"] = val3["beats"]
                val["narration"] = " ".join(b["t"] for b in val["beats"])
                log(f"expand-beats: now {len(val['narration'].split())} words")
            else:
                break
    return val



ANCHOR_PLATFORMS = [("chatgpt", "ChatGPT"), ("openai", "OpenAI"),
                    ("claude", "Claude"), ("anthropic", "Anthropic"),
                    ("gemini", "Gemini"), ("google", "Google"),
                    ("grok", "Grok"), ("deepseek", "DeepSeek"),
                    ("qwen", "Qwen"), ("meta", "Meta"),
                    ("microsoft", "Microsoft"), ("copilot", "Copilot")]


def _anchor_candidates(heads, limit=4):
    """Rank real headlines usable as a hard anchor for the fallback entry."""
    out = []
    for h in heads:
        t = h.get("title") or ""
        tl = t.lower()
        plat = next((disp for k, disp in ANCHOR_PLATFORMS if k in tl), None)
        score = 3 if plat else 0
        if re.search(r"\d", t):
            score += 2
        if re.search(r"launch|release|ban|banned|record|beats|billion|million|"
                     r"new model|update|price|free|first|cuts|hires", tl):
            score += 2
        if 20 <= len(t) <= 95:
            score += 1
        # prefer headlines that carry a recent date; undated ones still count
        # but rank below dated stories from the same feed
        if score >= 4:
            out.append((score + (1 if str(h.get("date") or "").strip() else 0),
                        h, plat))
    out.sort(key=lambda x: -x[0])
    return [(h, plat) for _s, h, plat in out[:limit]]


def _anchor_entry(kind, h, plat, today, demand_txt, recent_txt):
    """Build a compliant entry around ONE real headline.

    OWNER FIX 2026-11-01: the free lite models kept failing entry validation
    ("sources-not-in-headlines", and three attempts with no reason at all) and
    the 21:00 BD Long was lost three days running. When that happens we no
    longer give up: the topic, the source URL and the searchable subject are
    taken from a real headline, and the model only writes the script. Title and
    description are then repaired deterministically so the searchability and
    citation rules hold by construction.
    """
    subj = plat or " ".join((h.get("title") or "").split()[:3])
    mand = ("MANDATORY TOPIC - use EXACTLY this story, never choose another: "
            + (h.get("title") or "") + "\n"
            + "MANDATORY SOURCE URL - copy it exactly into verified_sources: "
            + h["url"] + "\n"
            + 'MANDATORY SUBJECT - the exact string "' + subj + '" must appear '
            "VERBATIM in the title AND in the first line of the description.\n\n")
    base = SHORT_PROMPT if kind == "short" else ENTRY_PROMPT
    prompt = mand + base.format(headlines="- " + (h.get("title") or "") + " | " + h["url"],
                                today=today, demand=demand_txt, recent=recent_txt,
                                lessons=analytics_lessons(),
                                words=LONG_TARGET_WORDS,
                                beats=max(20, LONG_TARGET_WORDS // 30))
    val = gemini_json(prompt, models=["gemini-3.5-flash", "gemini-flash-latest",
                                      "gemini-flash-lite-latest"])
    if not val or not isinstance(val.get("beats"), list) or not val.get("beats"):
        return None
    if kind == "long":
        val = _grow_to_target(val)
    else:
        val["narration"] = val.get("narration") or " ".join(
            b.get("t", "") for b in val["beats"])
    # deterministic repair: subject in title + description, hook, length limits
    ttl = " ".join(str(val.get("title") or "").split())
    hook = next((w for w in ("Banned", "Built", "Just", "New", "Shocking",
                             "Warning", "Nobody", "Truth", "Finally", "First")
                 if w.lower() in ttl.lower()), None)
    if subj.lower() not in ttl.lower() or len(ttl) > 50 or not hook:
        head = re.sub(r"^[^:]{0,26}:\s*", "", (h.get("title") or ""))
        cand = [subj + ": " + head, subj + " Just Changed Everything",
                subj + " Just Got Banned", subj + " Is Not What You Think"]
        ttl = next((c[:50].strip() for c in cand
                    if subj.lower() in c.lower() and len(c) <= 50
                    and any(w.lower() in c.lower() for w in
                            ("just", "banned", "new", "first", "changed",
                             "not", "built"))), (subj + " AI News")[:50])
    val["title"] = ttl
    val["subject"] = subj
    desc = " ".join(str(val.get("description") or "").split())
    if subj.lower() not in desc[:220].lower():
        val["description"] = (subj + " " + (h.get("title") or "")[:110]
                              + ". " + desc)[:600]
    val["verified_sources"] = [h["url"]]
    val["demand_evidence"] = "anchored to a current verified headline: " \
        + (h.get("title") or "")[:120]
    if kind == "short":
        val.setdefault("headline", ttl.upper()[:24])
        val.setdefault("specs", [])
    words = len(str(val.get("narration", "")).split())
    lo, hi = ((45, 150) if kind == "short"
              else (int(LONG_TARGET_WORDS * 0.6), int(LONG_TARGET_WORDS * 1.2)))
    if not (lo <= words <= hi):
        log(f"anchored entry rejected on length ({words} words)")
        return None
    val["id"] = re.sub(r"[^a-z0-9]+", "_",
                       (val.get("id") or subj + "_" + h["url"].rstrip("/").split("/")[-1]).lower()
                       ).strip("_")[:60]
    log(f"anchored entry ACCEPTED from headline: {(h.get('title') or '')[:60]} "
        f"({words} words, {len(val['beats'])} beats)")
    return val


def make_entry(kind):
    heads = news_headlines(kind)
    if not heads:
        return None, "no headlines fetched"
    today = time.strftime("%Y-%m-%d")
    if kind == "short":
        # OWNER 2026-10-07 21:46 BD: shorts are robot videos; put ROBOT
        # headlines first so the model actually sees trending robot stories.
        _rh = [h for h in heads if re.search(
            r"robot|humanoid|drone swarm|boston dynamics|optimus|cyborg|robotics",
            h["title"], re.I)]
        log(f"robot headlines found: {len(_rh)}")
        _sel = (_rh[:25] + [h for h in heads if h not in _rh][:10])[:35]
    else:
        _sel = heads[:30]
    head_txt = "\n".join(f"- {h['title']} | {h['url']}" for h in _sel)
    demand = demand_counts(heads)
    log("topic demand ranking: " + ", ".join(f"{k}={v}" for k, v in demand.items()))
    demand_txt = "\n".join(f"- {k}: {v} headlines" for k, v in demand.items())
    # recent titles feed (title variety rule, owner review 2026-10-06)
    try:
        _pl = json.load(open(os.path.join(FACT, "published_log.json")))
        _recent = [r.get("title", "") for r in _pl if r.get("kind") == "long" and r.get("title")][-6:]
    except Exception:
        _recent = []
    recent_txt = "\n".join(f"- {t}" for t in _recent) or "(none yet)"
    policy = json.load(open(os.path.join(FACT, "content_policy.json")))
    # full-flash models first: lite models return short scripts and waste attempts
    # OWNER FIX 2026-10-08 05:45 BD: lite models FIRST - free-tier rate table
    # gives lite models ~500 RPD while 3.5-flash/pro now mostly 503/429.
    ladder = [
        ["gemini-flash-lite-latest", "gemini-3.5-flash-lite"],
        ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-lite-latest"],
        ["gemini-3.5-flash", "gemini-flash-latest", "gemini-pro-latest",
         "gemini-flash-lite-latest", "gemini-3.5-flash-lite"],
    ]
    for models in ladder:
        _prompt = SHORT_PROMPT if kind == "short" else ENTRY_PROMPT
        val = gemini_json(_prompt.format(headlines=head_txt, today=today,
                                         demand=demand_txt, recent=recent_txt,
                                         lessons=analytics_lessons(),
                                         words=LONG_TARGET_WORDS,
                                         beats=max(20, LONG_TARGET_WORDS // 30)),
                          models=models)
        if not val:
            # model set exhausted (quota/overload) — try the next ladder entry
            # instead of giving up (fixes premature "gemini unavailable").
            log(f"gemini unavailable on {models[0]}+ set; trying next ladder")
            continue
        try:
            _grow_to_target(val)
            # OWNER 2026-10-11 War Plan: HARD no-repeat guard. Oct 8 and
            # Oct 10 longs got the IDENTICAL title ("ChatGPT Intelligent UI:
            # Full Beginner Guide") even with the recent-titles feed in the
            # prompt — YouTube suppresses repeats. Reject any topic too
            # close to the last 10 published titles, retry via the ladder.
            if val.get("title"):
                try:
                    _pl2 = json.load(open(os.path.join(FACT, "published_log.json")))
                except Exception:
                    _pl2 = []
                _banned = [r.get("title", "") for r in _pl2 if r.get("title")][-10:]
                _dup = next((bt for bt in _banned
                             if bt and _title_overlap(val["title"], bt) >= 0.6), None)
                if _dup:
                    log(f"entry rejected: repeats recent title '{str(_dup)[:44]}'")
                    continue
            words = len(val["narration"].split())
            beats = val["beats"]
            tl = val["title"].lower()
            srcs = {h["url"] for h in heads}
            _wlen_ok = ((70 <= words <= 150 and 4 <= len(beats) <= 8)
                        if kind == "short" else
                        (LONG_MIN_WORDS <= words <= LONG_MAX_WORDS
                         and 30 <= len(beats) <= LONG_MAX_BEATS + 10))
            # OWNER 2026-10-16 SEARCHABILITY GUARD: 70% of views come from
            # search; a drama-only title no one searches gets zero reach.
            # The model must emit "subject" (the exact searchable name) and
            # it must appear verbatim in the title AND in the description.
            _subj = " ".join(str(val.get("subject") or "").split()).lower()
            _desc_l = str(val.get("description", "")).lower()
            if kind == "short":
                # 2026-10-26: shorts accept the subject (or its first word) in
                # the description only - number-first titles ("Robots Now Rent
                # for $40 a Day") are our proven winners and rarely repeat the
                # full model name verbatim.
                _sw = _subj.split()[0] if _subj else ""
                _subj_ok = bool(_subj) and (_subj in _desc_l or (_sw and _sw in _desc_l))
            else:
                _subj_ok = bool(_subj) and _subj in tl and _subj in _desc_l
            if kind == "short":
                # OWNER 2026-10-07 21:46 BD: standalone shorts are ROBOT
                # videos (casperpks-style); must be robot-focused.
                ok = (_wlen_ok
                      and _subj_ok
                      and len(val["title"]) <= 52
                      and "robot" in (val["title"] + " " + val["narration"]).lower()
                      and (any(h in tl for h in HOOKS) or bool(re.search(r"[0-9$%]", val["title"])))
                      and val.get("verified_sources")
                      and any(s in srcs for s in val["verified_sources"][:3]))
            else:
                # OWNER FIX 2026-10-08: at least one exact headline URL
                # (any, not all) — 3.5-flash passes a sloppy second URL
                # sometimes; grounding is kept by the one exact source.
                ok = (_wlen_ok
                      and _subj_ok
                      and len(val["title"]) <= 52
                      and ("ai" in tl or any(p in tl for p in
                            ["chatgpt", "openai", "claude", "gemini", "grok", "deepseek", "qwen"]))
                      and any(h in tl for h in HOOKS)
                      and val.get("verified_sources")
                      and any(s in srcs for s in val["verified_sources"][:3]))
            if not ok:
                _why = []
                if not _wlen_ok:
                    _why.append(f"words={words},beats={len(beats)}")
                if not _subj_ok:
                    _why.append(f"subject-not-searchable ({_subj[:24] if _subj else 'missing'})")
                if len(val["title"]) > 52:
                    _why.append("title>52")
                if kind == "short" and "robot" not in (val["title"] + " " + val["narration"]).lower():
                    _why.append("no-robot")
                if kind == "long" and not ("ai" in tl or any(p in tl for p in ["chatgpt", "openai", "claude", "gemini", "grok", "deepseek", "qwen"])):
                    _why.append("no-ai-keyword")
                # OWNER 2026-11-01: the documentary style uses plain factual
                # titles ("OpenAI's New Model Explained"), so a drama word is no
                # longer mandatory. A number, a year, or an AI/money word counts.
                _title_hook = (any(h in tl for h in HOOKS)
                               or bool(re.search(r"[0-9]", val["title"]))
                               or any(w in tl for w in ("revealed", "new", "changes",
                                                        "future", "inside", "explained",
                                                        "record", "first", "secret",
                                                        "billion", "million", "$")))
                if not _title_hook:
                    _why.append("no-hook-word")
                if not val.get("verified_sources"):
                    _why.append("no-sources")
                elif not all(s in srcs for s in val["verified_sources"][:3]):
                    _why.append("sources-not-in-headlines")
                log("entry validation failed [" + ", ".join(_why) + "]; retry")
                continue
            e = val
            e.update({
                "kind": kind, "categoryId": "28", "madeForKids": False,
                "content_pillar": "ai_updates", "scope_reviewed": True,
                "content_policy_version": policy["version"],
                "seed": int(time.time()) % 1000,
            })
            for b in e["beats"]:
                b.setdefault("tags", [])
            e["id"] = re.sub(r"[^a-z0-9]+", "_", e["id"].lower()).strip("_")[:60]
            e["id"] = re.sub(r"_\d{4}_\d{2}-\d{2}-\d{2}$", "", e["id"])
            e["id"] = re.sub(r"_\d{4}-\d{2}-\d{2}$", "", e["id"])
            e["id"] = re.sub(r"_\d{4}$", "", e["id"])  # model may append its own year
            e["id"] = f"{e['id']}_{today}"
            # OWNER STYLE 2026-10-11 (androidalians poster look): headline +
            # specs get burned on screen by factory.render. The prompt asks
            # for them, but lite models can be sloppy - always derive a
            # fallback so the render never runs without the poster text.
            if kind == "short":
                _hl = " ".join(str(e.get("headline") or "").upper().split())
                if not _hl or len(_hl.split()) > 6:
                    _hl = re.sub(r"[^A-Z0-9 ]", " ", e["title"].upper())
                    _hl = " ".join(w for w in _hl.split()
                                   if w not in ("SHOCKING", "WARNING", "BANNED",
                                                "SOLVED", "IMPOSSIBLE", "NEVER",
                                                "JUST", "GOT", "THE", "THIS"))[:4]
                    _hl = _hl or e["title"].upper()[:24]
                e["headline"] = _hl
                e["specs"] = [re.sub(r"[^A-Z0-9 .:/+-]", "", str(x)).strip()[:14]
                              for x in (e.get("specs") or []) if str(x).strip()][:3]
            return e, None
        except Exception as ex:
            log("entry parse error: " + str(ex)[:120])
    # LAST RESORT (owner fix 2026-11-01): anchor to a real headline instead of
    # ending the run with NO_ELIGIBLE_CONTENT.
    for h, plat in _anchor_candidates(heads):
        try:
            anchored = _anchor_entry(kind, h, plat, today, demand_txt, recent_txt)
        except (Exception, SystemExit) as ex:
            log("anchored attempt failed: " + str(ex)[:140])
            continue
        if anchored:
            anchored.update({"kind": kind, "categoryId": "28",
                             "madeForKids": False,
                             "content_pillar": "ai_updates",
                             "scope_reviewed": True,
                             "content_policy_version": policy["version"],
                             "seed": int(time.time()) % 1000})
            for _b in anchored["beats"]:
                _b.setdefault("tags", [])
            if not factory.content_eligible(anchored):
                log("anchored entry failed the scope gate; trying the next "
                    "headline")
                continue
            return anchored, None
    return None, "no valid entry from gemini (anchored fallbacks also failed)"


def append_library(e):
    p = os.path.join(FACT, "library.json")
    lib = json.load(open(p))
    if not any(x["id"] == e["id"] for x in lib["entries"]):
        lib["entries"].append(e)
        json.dump(lib, open(p, "w"), indent=1, ensure_ascii=False)
        log(f"library: appended {e['id']}")


# ---------------------------------------------------------------- footage
def load_used():
    return json.load(open(USED_F)) if os.path.exists(USED_F) else {"used": []}


def save_used(u):
    json.dump(u, open(USED_F, "w"), indent=1)


PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "").strip()


def _pexels_pick(kw, orient, used, used_here):
    url = ("https://api.pexels.com/videos/search?query=" +
           urllib.parse.quote(kw) + f"&per_page=15&orientation={orient}&size=medium")
    res = json.loads(_http(url, headers={"Authorization": PEXELS_KEY}, timeout=30))
    for v in res.get("videos", []):
        if v["id"] in used["used"] or v["id"] in used_here:
            continue
        if (v.get("duration") or 0) < 4:
            continue
        files = [f for f in v.get("video_files", [])
                 if f.get("file_type") == "video/mp4"
                 and (f.get("width") or 0) >= (720 if orient == "portrait" else 1280)
                 and (f.get("height") or 0) >= (1280 if orient == "portrait" else 720)]
        if files:
            files.sort(key=lambda f: (f.get("width") or 0), reverse=True)
            return v["id"], files[0]["link"], v.get("duration") or 0
    raise RuntimeError("no unused relevant pexels clip")


def _pixabay_pick(kw, orient, used, used_here):
    """Pixabay video search with tag-relevance ranking.

    OWNER FIX 2026-11-01: the repo only holds PIXABAY_API_KEY, while fresh
    footage insisted on PEXELS_API_KEY and therefore fell back to the small
    bundled pool on every run. That is what produced tonight's 316-second
    single shot, the black stretches and the frozen frames (QC 84/100).
    """
    # the videos endpoint has no orientation filter (images only), so the
    # aspect filter is applied locally below
    url = ("https://pixabay.com/api/videos/?key=" + PIXABAY_KEY +
           "&q=" + urllib.parse.quote(kw) + "&per_page=20&video_type=film"
           "&safesearch=true")
    data = json.loads(_http(url, timeout=30))
    qtok = {w for w in re.split(r"[^a-z0-9]+", kw.lower()) if len(w) >= 3}
    cands = []
    for h in data.get("hits", []):
        hid = str(h.get("id"))
        if hid in {str(x) for x in used.get("used", [])} or hid in used_here:
            continue
        if (h.get("duration") or 0) < 4:
            continue
        vs = h.get("videos") or {}
        for name in ("large", "medium", "small"):
            v = vs.get(name) or {}
            w = v.get("width") or 0
            hh = v.get("height") or 0
            if not v.get("url"):
                continue
            if orient == "portrait" and hh >= 1280:
                cands.append((h, v, hid)); break
            if orient != "portrait" and w >= 1280:
                cands.append((h, v, hid)); break
    if not cands:                       # accept medium if nothing HD came back
        for h in data.get("hits", []):
            hid = str(h.get("id"))
            if hid in {str(x) for x in used.get("used", [])} or hid in used_here:
                continue
            v = (h.get("videos") or {}).get("medium") or {}
            if v.get("url") and (h.get("duration") or 0) >= 4:
                cands.append((h, v, hid))
    if not cands:
        raise RuntimeError("no unused relevant pixabay clip")

    def rel(item):
        h = item[0]
        tags = h.get("tags") or ""
        if not isinstance(tags, str):
            tags = " ".join(tags)
        blob = tags.lower() + " " + str(h.get("pageURL") or "").lower()
        return len(qtok & {w for w in re.split(r"[^a-z0-9]+", blob) if len(w) >= 3})

    cands.sort(key=lambda it: -(rel(it) * 1_000_000 + (it[0].get("views") or 0)))
    h, v, hid = cands[0]
    return hid, v["url"], h.get("duration") or 0


def fresh_footage(e, workdir, used):
    """Per-video fresh topic-matched stock footage.

    Pexels when PEXELS_API_KEY is set, otherwise Pixabay (the key this repo
    actually has), otherwise the bundled pool via the caller's fallback.
    """
    orient = "portrait" if e.get("kind") == "short" else "landscape"
    if PEXELS_KEY:
        pick, provider = _pexels_pick, "pexels"
    elif PIXABAY_KEY:
        pick, provider = _pixabay_pick, "pixabay"
    else:
        log("footage: no PEXELS_API_KEY and no PIXABAY_API_KEY — using bundled "
            "pool (fallback)")
        return None
    beats = factory.derive_beats(e)
    clips = []
    used_here = set()
    os.makedirs(os.path.join(FACT, "footage", "fresh"), exist_ok=True)
    for i, (txt, _tags) in enumerate(beats, 1):
        kw = e["beats"][i - 1].get("kw") if e.get("beats") else None
        if not kw:
            words = [w for w in re.findall(r"[a-zA-Z]{4,}", txt.lower())]
            kw = " ".join(words[:3])
        try:
            vid, link, dur = pick(kw, orient, used, used_here)
            dst = os.path.join(FACT, "footage", "fresh", f"{provider}_{vid}.mp4")
            with open(dst, "wb") as fh:
                fh.write(_http(link, timeout=180))
            used_here.add(str(vid))
            used["used"].append(f"{provider}_{vid}")
            clips.append({"file": f"fresh/{provider}_{vid}.mp4", "dur": dur})
            log(f"beat {i}: fresh {provider} clip {vid} for '{kw}' ({dur}s)")
            time.sleep(0.4)
        except Exception as ex:
            log(f"fresh footage failed beat {i} ({str(ex)[:100]}) — falling "
                "back to the bundled pool")
            return None
    save_used(used)
    return [(c, len(t[0].split())) for c, t in zip(clips, beats)]


def pool_footage(e, workdir):
    """Bundled-pool fallback with semantic enrichment for AI-written entries.

    Maps each beat via its fresh-footage keyword phrase AND its text; any beat
    that still maps to no pool category inherits the video's dominant topic
    categories (never a random unrelated clip).
    """
    idx = factory.load_footage()
    e2 = dict(e)
    e2["beats"] = [dict(b) for b in e.get("beats", [])]
    for b in e2["beats"]:
        cats = (factory.cats_for_text(b.get("kw", "")) +
                factory.cats_for_text(b.get("t", "")) +
                [c for c in b.get("tags", []) if c in idx])
        b["tags"] = list(dict.fromkeys(cats))
    from collections import Counter
    dom = [c for c, _ in Counter(
        c for b in e2["beats"] for c in b["tags"]).most_common(6)]
    for b in e2["beats"]:
        if not b["tags"]:
            b["tags"] = dom[:2]
        # depth: let every beat fall back to the video's dominant topic cats
        for c in dom[:6]:
            if c not in b["tags"] and idx.get(c):
                b["tags"].append(c)
    # widen pools with never-before-used Pexels spare clips (free CDN, owner
    # approved source) so deep beats never exhaust a small category
    need = Counter(c for b in e2["beats"] for c in b["tags"][:2])
    deepened = deepen_pools(need, idx)
    try:
        return factory.pick_footage(e2, workdir)
    except SystemExit:
        if not deepened:
            raise
        return factory.pick_footage(e2, workdir)


def deepen_pools(need, idx):
    """Download fresh spare Pexels clips for high-demand categories.

    Returns True if any new clip was added to the local pool. New clips have
    never appeared in another video (spares were never downloaded before).
    """
    import subprocess
    idx_f = os.path.join(FACT, "footage", "index.json")
    spares_f = os.path.join(FACT, "footage", "_pool.json")
    if not os.path.exists(spares_f):
        return False
    spares = json.load(open(spares_f))
    added = False
    for cat, n in need.most_common():
        want = n + 2
        cur = len(idx.get(cat, []))
        if cur >= want or not spares.get(cat):
            continue
        known_ids = {c.get("id") for c in idx.get(cat, [])}
        for s in spares[cat]:
            if cur >= want:
                break
            if str(s.get("id")) in known_ids:
                continue
            fn = f"{cat}_{s['id']}.mp4"
            dst = os.path.join(FACT, "footage", fn)
            try:
                data = _http(s["url"], headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0 Safari/537.36"}, timeout=240)
                if len(data) < 500_000:
                    raise RuntimeError("too small")
                with open(dst, "wb") as fh:
                    fh.write(data)
                dur = float(subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", dst],
                    capture_output=True, text=True).stdout.strip() or "0")
                if dur < 3:
                    os.remove(dst)
                    raise RuntimeError(f"too short {dur:.0f}s")
                idx.setdefault(cat, []).append(
                    {"file": fn, "dur": round(dur, 1), "id": str(s["id"])})
                known_ids.add(str(s["id"]))
                cur += 1
                added = True
                log(f"pool deepened: {fn} ({dur:.0f}s) [{cat}]")
            except Exception as ex:
                log(f"spare download failed {s.get('id')}: {str(ex)[:90]}")
                if os.path.exists(dst):
                    os.remove(dst)
    if added:
        json.dump(idx, open(idx_f, "w"), indent=1)
    return added


# ---------------------------------------------------------------- state push
def commit_file(path_in_repo, local_path, msg):
    if not (GH_TOKEN and GH_REPO):
        log(f"commit skipped (no token): {path_in_repo}")
        return
    api = f"https://api.github.com/repos/{GH_REPO}/contents/{urllib.parse.quote(path_in_repo)}"
    sha = None
    try:
        cur = json.loads(_http(api + f"?ref={GH_BRANCH}",
                               headers={"Authorization": "Bearer " + GH_TOKEN,
                                        "Accept": "application/vnd.github+json"}))
        sha = cur.get("sha")
    except urllib.error.HTTPError as ex:
        if ex.code != 404:
            log(f"commit GET failed {path_in_repo}: {ex}")
            return
    except Exception as ex:
        log(f"commit GET failed {path_in_repo}: {str(ex)[:100]}")
        return
    body = json.dumps({
        "message": msg, "branch": GH_BRANCH,
        "content": base64.b64encode(open(local_path, "rb").read()).decode(),
        **({"sha": sha} if sha else {})}).encode()
    try:
        _http(api, headers={"Authorization": "Bearer " + GH_TOKEN,
                           "Accept": "application/vnd.github+json",
                           "Content-Type": "application/json"},
              data=body, method="PUT")
        log(f"committed: {path_in_repo}")
    except Exception as ex:
        log(f"commit PUT failed {path_in_repo}: {str(ex)[:120]}")


def _recent_short_titles(days=14):
    """Titles of shorts published in the last N days (anti-spam guard 2026-10-23).
    Reads the repo published_log plus any in-run additions so state is never
    trusted stale: 17 identical 'Robot Conducts Orchestra' shorts went live
    2026-10-19..23 because done-state never persisted. Never again the same
    story twice inside a fortnight."""
    import datetime as _dt
    titles = []
    try:
        pl = json.load(open(os.path.join(FACT, "published_log.json")))
        cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
        for it in pl:
            if it.get("kind") != "short":
                continue
            when = str(it.get("uploaded_at") or it.get("scheduled_for") or "")
            try:
                ts = _dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
            except ValueError:
                ts = None
            if ts is None or ts >= cutoff:
                titles.append(it.get("title", ""))
    except Exception:
        pass
    return [t for t in titles if t]


def _pick_unique_short_entry(fresh_e):
    """Return the first non-duplicate short entry: the fresh Gemini entry if
    clean, else the oldest pending library short whose title does NOT overlap
    >=0.6 with any recent short. None => skip production this run (better a
    dark slot than channel-killing spam)."""
    used = _recent_short_titles()
    if fresh_e and all(_title_overlap(fresh_e["title"], t) < 0.6 for t in used):
        return fresh_e
    st = factory.load_state()
    # FIX 2026-10-26: factory.LIB is loaded once at import; re-read from disk so
    # entries appended/committed earlier this run (and pre-seeded topics) are seen.
    try:
        _entries = json.load(open(os.path.join(FACT, "library.json")))["entries"]
    except Exception:
        _entries = factory.LIB["entries"]
    for e in _entries:
        if e.get("kind", "long") != "short" or e["id"] in st["done"]:
            continue
        if not factory.content_eligible(e):
            continue
        if all(_title_overlap(e["title"], t) < 0.6 for t in used):
            return e
    return None


def _title_overlap(t1, t2):
    """Word-overlap score between two titles (owner 2026-10-11 War Plan)."""
    stop = {"the", "a", "an", "of", "in", "on", "is", "are", "this", "that",
            "just", "its", "it", "to", "for", "with", "and", "new", "full",
            "guide", "beginner", "most", "people", "miss", "what", "how", "why"}
    w1 = {w for w in re.findall(r"[a-z0-9']+", str(t1).lower()) if w not in stop and len(w) > 2}
    w2 = {w for w in re.findall(r"[a-z0-9']+", str(t2).lower()) if w not in stop and len(w) > 2}
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / min(len(w1), len(w2))


def _robot_short(commit_extra, today):
    """Standalone robot Short, casperpks-style (owner 2026-10-07). 2026-10-11
    War Plan: also called on no-Long days so the channel is never dark."""
    try:
        r_e, r_err = make_entry("short")
        if not (r_e and factory.content_eligible(r_e)):
            r_e = None
            log("robot short: no fresh topic (" + str(r_err)[:80] + "); trying library")
        # ANTI-SPAM GUARD 2026-10-23: never the same story twice in 14 days
        r_e = _pick_unique_short_entry(r_e)
        if not r_e:
            log("robot short: no unique topic available - skipping upload (anti-spam guard)")
        if r_e:
            append_library(r_e)
            r_wd = os.path.join(factory.BASE, "runs", f"{r_e['id']}_{today}")
            os.makedirs(r_wd, exist_ok=True)
            # OWNER STYLE 2026-10-12: robot Shorts are built from glowing
            # AI illustrations (free AI Horde SDXL); stock footage is the
            # fallback so a slot is never lost.
            r_pairs = None
            try:
                r_pairs = factory.horde_beat_clips(r_e, r_wd)
            except Exception as hex_:
                log("horde clips failed (stock fallback): " + str(hex_)[:120])
            if not r_pairs:
                r_pairs = pool_footage(r_e, r_wd)
            r_audio = factory.gen_voice(r_e, r_wd)
            r_mp4 = factory.render(r_e, r_wd, r_pairs, r_audio)
            r_pub, r_slot = factory.next_bd_slot("short")
            r_vid = factory.upload(r_e, r_mp4, r_pub)
            factory.note_published(r_e, r_vid, "short", r_pub)
            st2 = factory.load_state()
            st2["done"][r_e["id"]] = {"date": today, "videoId": r_vid}
            factory.save_state(st2)
            # PERSISTENCE FIX 2026-10-23: state/published_log were never
            # committed on the robot-short path, so every run re-picked the
            # same pending library entry -> 17 identical shorts. Commit now,
            # before any crash-prone step can skip it.
            for _rel, _loc, _msg in [
                ("factory/state.json", os.path.join(FACT, "state.json"), "state: done " + r_e["id"]),
                ("factory/published_log.json", os.path.join(FACT, "published_log.json"), "state: published " + r_e["id"]),
                ("factory/library.json", os.path.join(FACT, "library.json"), "state: library " + r_e["id"]),
            ]:
                if os.path.exists(_loc):
                    commit_file(_rel, _loc, _msg)
            try:
                if not factory.make_thumb_ai(r_e, r_wd):
                    factory.make_thumb(r_e, r_wd, r_pairs[0][0])
                factory.set_thumbnail(r_vid, r_wd)
            except Exception as ex2:
                log("robot short thumb failed (continuing): " + str(ex2)[:120])
            rf2 = write_report(r_e, r_vid, r_pub, str(r_slot), "produce", "")
            commit_extra.append((os.path.relpath(rf2, REPO), rf2,
                                 "report: " + r_e["id"]))
            log(f"robot short: OK videoId={r_vid} scheduledFor={r_pub} ({r_slot})")
    except (Exception, SystemExit) as ex:
        log("robot short step failed (long already uploaded; continuing): " + str(ex)[:140])

def write_report(e, vid, publish_at, slot_local, mode, extra=""):
    os.makedirs(REPORTS, exist_ok=True)
    f = os.path.join(REPORTS, f"{e['id']}_{time.strftime('%Y%m%d_%H%M')}.md")
    state = ("scheduled (private, publishAt)" if vid
             else ("SELFTEST — rendered locally, NOT uploaded" if mode == "selftest"
                   else "not uploaded (see log)"))
    open(f, "w").write(f"""# {e['title']}

**Status:** {state}
**Slot (Dhaka):** {slot_local or 'n/a'}  |  **Slot (UTC):** {publish_at or 'n/a'}
{"**Video:** https://www.youtube.com/watch?v=" + vid if vid else ""}
**Topic pillar:** {e.get('content_pillar')}  |  **Sources:** {', '.join(str(x)[:60] for x in (e.get('verified_sources') or [])[:2])}

## Thumbnail prompt (owner makes it in ChatGPT)
{extra}

## Report (বাংলা)
ভিডিও তৈরি হয়েছে Actions রানার দিয়ে (কোনো Base44 ক্রেডিট খরচ হয়নি)।
থাম্বনেল উপরের প্রম্পট দিয়ে ChatGPT-তে বানিয়ে নিচে।
""")
    return f


THUMB_PROMPT = """Write ONE ready-to-use image-generation prompt (6-8 lines, English) for a 16:9 YouTube thumbnail about: "{title}". Style: clean tech-explainer, high contrast, bold 3D text with the main hook, dark background with teal/orange accents, no real logos, no faces, no watermark. Output only the prompt text."""


# ---------------------------------------------------------------- main
# ═══════════ QUALITY GATE (owner master prompt 2026-11-01, §11) ═══════════
QC_MIN_SCORE = int(os.environ.get("QC_MIN_SCORE", "85"))


def _mp4_has_audio(mp4):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                              "-show_entries", "stream=codec_type", "-of",
                              "csv=p=0", mp4], capture_output=True, text=True, timeout=60)
        return "audio" in (out.stdout or "")
    except Exception:
        return False


def _mp4_duration(mp4):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "format=duration", "-of", "csv=p=0", mp4],
                             capture_output=True, text=True, timeout=60)
        return float((out.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def analytics_lessons():
    """One-line summary of the measured analytics, injected into the prompt.

    Empty string when nothing has been measured - the prompt then simply says
    nothing about analytics instead of inventing evidence.
    """
    try:
        d = json.load(open(os.path.join(FACT, "analytics_lessons.json")))
    except Exception:
        return ""
    vids = d.get("videos") or []
    if not vids:
        return ""
    def _avg(key):
        vals = [v[key] for v in vids if isinstance(v.get(key), (int, float))]
        return round(sum(vals) / len(vals), 1) if vals else None
    bits = []
    for key, label in (("avg_pct_viewed", "average % viewed"),
                       ("intro_retention_est_pct", "retention at ~30s"),
                       ("ctr_pct", "impressions CTR"),
                       ("avd_s", "average view duration s")):
        val = _avg(key)
        if val is not None:
            bits.append(f"{label} {val}")
    if not bits:
        return ""
    return ("MEASURED PERFORMANCE (YouTube Analytics, " + str(d.get("window_days", 28)) +
            " days, " + str(len(vids)) + " videos): " + ", ".join(bits) +
            ". Use this to decide Hook length and pacing: if 30s retention is low, the first "
            "beat must deliver the surprise faster; do not copy numbers into the narration.")


def _llm_hook_copies(e):
    """Three DIFFERENT thumb-hook texts from the free Gemini text tier.

    Text only: Google removed free image generation, so the pixels come from our
    own footage + PIL, and the LLM writes the copy (2-4 punchy caps words each).
    """
    try:
        prompt = ('Give 3 different YouTube thumbnail hooks for this video, 2-4 ALL-CAPS words each, '
                  'no punctuation, no emoji, each a different angle (result / threat / curiosity). '
                  'Title: "' + str(e.get("title", "")) + '". '
                  'Return ONLY JSON: {"hooks":["...","...","..."]}')
        val = gemini_json(prompt, models=["gemini-flash-lite-latest", "gemini-3.5-flash-lite"])
        hs = [str(h).strip().upper()[:28] for h in (val or {}).get("hooks", []) if str(h).strip()]
        return hs[:3]
    except Exception as ex:
        log("thumb hook copy unavailable (using headline): " + str(ex)[:90])
        return []


def _three_thumbs(e, workdir, pairs):
    """Task 1: three genuinely different concepts, objectively scored, best wins.

    Saves thumb_A_cinematic.jpg / thumb_B_news.jpg / thumb_C_curiosity.jpg plus
    thumbnail.jpg (the selected one) and thumbs_report.json. Returns True when a
    thumbnail.jpg exists. Scores are a quality screen - NOT a CTR guarantee.
    """
    try:
        import thumb_variants
    except Exception as ex:
        log("thumb_variants unavailable: " + str(ex)[:120])
        return False
    try:
        clip = pairs[0][0]
        clip_path = os.path.join(FACT, "footage", clip["file"])
        tags = []
        for c in (pairs[:3] if pairs else []):
            tags += list((c[0] or {}).get("tags") or [])
        e["_clip_meta"] = [dict((c[0] or {}), tags=(c[0] or {}).get("tags") or []) for c in pairs]
        hooks = _llm_hook_copies(e)
        res = thumb_variants.generate_three(e, workdir, clip_path, tags, hooks=hooks)
        log("thumbs: " + json.dumps(res.get("scores", {})) +
            " | selected: " + str(os.path.basename(res.get("selected") or "none")) +
            " | " + str(res.get("note", ""))[:90])
        return bool(res.get("final") and os.path.exists(res["final"]))
    except Exception as ex:
        log("three-thumb step failed: " + str(ex)[:160])
        return False


def quality_gate(e, mp4, kind="long", narration_path=None):
    """100-point pre-publish gate (owner spec v2, Tasks 2/7).

    objective points                    subjective (reported, never scored)
      research / sources            15    cinematic taste, pacing feel
      script structure              15
      visual QC (factory.qc_visual) 25
      voice-over                    10
      editing / duration match      10
      thumbnail                     10
      SEO / metadata                 5
      render integrity              10
    Below QC_MIN_SCORE nothing is uploaded. Scores are never rounded up and a
    failed check is never waived.
    """
    sc, notes, report = {}, [], {}
    beats = e.get("beats") or []
    narr = e.get("narration", "") or ""
    words = len(narr.split())
    tgt = LONG_TARGET_WORDS if kind == "long" else 110

    # ── research accuracy (15)
    srcs = e.get("verified_sources") or []
    if len(srcs) >= 2 and e.get("demand_evidence"):
        sc["research"] = 15
    elif srcs:
        sc["research"] = 9
        notes.append(f"only {len(srcs)} verified source(s)")
    else:
        sc["research"] = 0
        notes.append("no verified sources")

    # ── script structure (15)
    hook_ok = bool(beats) and len(str(beats[0].get("t", "")).split()) <= 45
    quote_ok = ('"' in narr) or ("quote," in narr.lower())
    end_ok = bool(beats) and any(k in str(beats[-1].get("t", "")).lower()
                                 for k in ("comment", "next one", "subscribe"))
    sc["script"] = ((6 if words >= tgt * 0.65 else 0)
                    + (4 if hook_ok else 0)
                    + (2 if quote_ok else 1)
                    + (3 if end_ok else 0))
    if words < tgt * 0.65:
        notes.append(f"narration {words}w is short of the {tgt}w target")
    if not hook_ok:
        notes.append("cold-open hook beat is too long")

    # ── measured visual/audio QC (25) - objective checks only
    try:
        import qc_visual
        _parts, report = qc_visual.analyse(e, mp4, os.path.dirname(mp4) or ".", narration_path)
        sc["visual"] = min(25, int(report.get("total", 0)))
        for prob in report.get("problems", [])[:12]:
            notes.append(f"{prob['check']} @{prob.get('t', 0)}s: {prob['detail'][:70]}")
    except Exception as ex:
        sc["visual"] = 0
        notes.append("visual QC could not run: " + str(ex)[:80])
        report = {}

    # ── voice-over (10): an audio track must exist in the render
    sc["voice"] = 10 if _mp4_has_audio(mp4) else 0
    if not sc["voice"]:
        notes.append("render has no audio track")

    # ── editing (10): duration must match the script (~150 wpm)
    dur = _mp4_duration(mp4)
    expect = max(60.0, words / 2.5)
    if dur <= 0:
        sc["editing"] = 0
        notes.append("render duration unreadable")
    elif 0.6 * expect <= dur <= 1.6 * expect:
        sc["editing"] = 10
    else:
        sc["editing"] = 4
        notes.append(f"render {int(dur)}s vs expected {int(expect)}s")

    # ── thumbnail (10): the selected concept must exist and be a real image
    thumb_ok = False
    try:
        wd = os.path.dirname(mp4) or "."
        for cand in (os.path.join(wd, "thumbnail.jpg"), mp4.rsplit(".", 1)[0] + "_thumb.jpg"):
            if os.path.exists(cand) and os.path.getsize(cand) > 20000:
                thumb_ok = True
                break
    except Exception:
        pass
    sc["thumbnail"] = 10 if thumb_ok else 3
    if not thumb_ok:
        notes.append("thumbnail missing or tiny")

    # ── SEO / metadata (5)
    title = str(e.get("title", ""))
    subj = str(e.get("subject", "")).lower()
    seo = 0
    seo += 2 if 0 < len(title) <= 52 else 0
    seo += 2 if (subj and subj in title.lower()
                 and subj in str(e.get("description", "")).lower()) else 0
    seo += 1 if len(e.get("tags") or []) >= 8 else 0
    sc["seo"] = seo
    if seo < 5:
        notes.append("metadata incomplete (title/subject/tags)")

    # ── render integrity (10): never publish a partial render
    perf = 0
    try:
        size = os.path.getsize(mp4)
        perf += 4 if size > 1_000_000 else 0
        n_dur = _mp4_duration(narration_path) if narration_path else 0
        if n_dur and dur >= 0.9 * n_dur:
            perf += 6
        elif not n_dur:
            perf += 3
        else:
            notes.append(f"render {int(dur)}s is shorter than the narration {int(n_dur)}s")
        if size <= 1_000_000:
            notes.append(f"render only {size} bytes - looks truncated")
    except Exception as ex:
        notes.append("render integrity unreadable: " + str(ex)[:60])
    sc["render"] = perf

    total = sum(sc.values())
    log("QC: " + json.dumps(sc) + f" = {total}/100 (publish >= {QC_MIN_SCORE})")
    for n in notes:
        log("QC note: " + n)
    if report:
        log("QC report: " + os.path.join(os.path.dirname(mp4) or ".", "visual_qc_report.json"))
        log("QC subjective (not scored): " + "; ".join(report.get("subjective_checks", [])))
    return total, sc, notes


def render_film(e, workdir, pairs, audio):
    """SAFE INTEGRATION (owner master upgrade 2026-11-01).

    The cinematic editor is opt-in. With ENABLE_CINEMATIC_EDITOR unset (the
    default) this is byte-for-byte the old behaviour: factory.render(). When the
    flag is on we try the new engine, and we only accept its output if its own
    QC report passes - otherwise we fall straight back to the proven renderer so
    a slot can never be lost to the new code.
    """
    flag = os.environ.get("ENABLE_CINEMATIC_EDITOR", "false").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        return factory.render(e, workdir, pairs, audio)
    try:
        from cine import editor as CINE
        rep = CINE.build(e, os.path.join(workdir, "cine"),
                         narration_path=audio, force=True)
        qc = (rep or {}).get("qc") or {}
        if qc.get("ok") and rep.get("output"):
            log("cinematic editor: QC PASS (score "
                + str(qc.get("score")) + ") - using the new render")
            return rep["output"]
        log("cinematic editor: QC FAIL (score " + str(qc.get("score"))
            + ") - falling back to factory.render")
    except Exception as ex:
        log("cinematic editor crashed, falling back to factory.render: "
            + str(ex)[:180])
    return factory.render(e, workdir, pairs, audio)


def _explicit_slot(kind, iso):
    """OWNER OVERRIDE (2026-11-01): publish to an explicitly named slot when a
    render finished after the automatic 8-10h lead window closed.

    Fail-closed by construction: the slot must be a configured slot time for
    this kind, must be in the future, and must not already be booked in the repo
    log. The cross-producer YouTube check still runs right after, so we never
    double-book a slot another producer already took.
    """
    cfg = json.load(open(os.path.join(FACT, "content_policy.json")))["schedules"]
    bd = ZoneInfo(cfg["timezone"])
    raw = str(iso).strip().replace("Z", "+00:00")
    try:
        when = _dt.datetime.fromisoformat(raw)
    except ValueError:
        raise SystemExit("PUBLISH_AT_INVALID: " + str(iso))
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    when = when.astimezone(_dt.timezone.utc)
    local = when.astimezone(bd)
    legal = cfg.get("slots", {}).get(kind) or []
    if local.strftime("%H:%M") not in legal:
        raise SystemExit("PUBLISH_AT_NOT_A_SLOT: "
                         + local.strftime("%H:%M") + " not in " + str(legal))
    if when <= _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=5):
        raise SystemExit("PUBLISH_AT_IN_THE_PAST: " + str(iso))
    log_path = os.path.join(FACT, "published_log.json")
    if os.path.exists(log_path):
        for row in json.load(open(log_path)):
            if row.get("kind") != kind or not row.get("scheduled_for"):
                continue
            d = _dt.datetime.fromisoformat(row["scheduled_for"].replace("Z", "+00:00"))
            if abs((d - when).total_seconds()) < 300:
                raise SystemExit("PUBLISH_AT_ALREADY_BOOKED: " + row["scheduled_for"])
    log("OWNER OVERRIDE slot " + local.strftime("%Y-%m-%d %H:%M") + " " + str(bd.key)
        + " (explicit --publish-at; automatic lead window bypassed on owner request)")
    return when.strftime("%Y-%m-%dT%H:%M:%SZ"), local


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="long", choices=["long", "short"])
    ap.add_argument("--selftest", action="store_true",
                    help="run the full pipeline but never upload")
    ap.add_argument("--publish-at", default="",
                    help="OWNER OVERRIDE: explicit slot, ISO8601 UTC (e.g. "
                         "2026-11-01T15:00:00Z). Validated against the configured "
                         "slot times and the repo log; never double-books.")
    ap.add_argument("--curate", action="store_true",
                    help="channel About rewrite + topic playlists + file existing videos (no upload)")
    args = ap.parse_args()
    kind = args.kind

    restore_token()

    # 0) One-off channel curation (owner review 2026-10-06): About text,
    #    topic playlists, file every published Long into its playlist.
    if args.curate:
        factory.update_channel_about()
        pls = factory.ensure_playlists()
        log(f"playlists ready: {len(pls)}")
        # NOTE: search.list mine=true returns WATCH-HISTORY junk, not our
        # uploads (verified live 2026-10-06) - always use the uploads playlist.
        ch = factory._yt("channels", {"part": "contentDetails", "mine": "true"})
        uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        n = 0
        page = ""
        while True:
            q = {"part": "snippet", "playlistId": uploads, "maxResults": "50"}
            if page:
                q["pageToken"] = page
            res = factory._yt("playlistItems", q)
            for it in res.get("items", []):
                vid = it["snippet"].get("resourceId", {}).get("videoId")
                ttl = it["snippet"].get("title", "")
                if vid:
                    factory.add_to_playlist(vid, ttl)
                    n += 1
            page = res.get("nextPageToken")
            if not page:
                break
        log(f"curate done: about updated, {n} videos filed into playlists")
        return

    # 1) Which slot are we producing for? (fail-closed window check, repo log)
    if args.selftest:
        # offline full-pipeline test: find a synthetic valid window, never upload
        publish_at, slot_local = None, None
        base = _dt.datetime.now(BD)
        # 2-day Long cadence means the next bookable window can be up to
        # ~2.5 days out; 800 x 5min = ~66h covers it (300 x 5min was too short
        # right after a Long published, causing SELFTEST: no synthetic slot).
        for off in range(0, 800):
            fake = (base + _dt.timedelta(minutes=5 * off)).astimezone(UTC)
            try:
                publish_at, slot_local = factory.next_bd_slot(kind, now=fake)
                break
            except SystemExit:
                continue
        if not publish_at:
            raise SystemExit("SELFTEST: no synthetic slot found")
        log(f"selftest: synthetic target slot {slot_local} (upload will NOT happen)")
    else:
        try:
            if (getattr(args, "publish_at", "") or "").strip():
                publish_at, slot_local = _explicit_slot(kind, args.publish_at)
            else:
                publish_at, slot_local = factory.next_bd_slot(kind)
        except SystemExit:
            # OWNER 2026-10-11 War Plan: a no-Long day is NOT a dead day —
            # the channel published NOTHING on off-days, which kills algo
            # momentum. Produce the standalone robot Short for the next
            # Short slot, then exit (hook-cut needs the Long, so it only
            # happens on Long days).
            log("no Long slot due (2-day cadence) - producing robot Short, then exiting")
            try:
                _robot_short([], time.strftime("%Y-%m-%d"))
            except (Exception, SystemExit) as ex:
                log("robot short step failed: " + str(ex)[:140])
            return

    # 2) Cross-producer duplicate guard (YouTube scheduled uploads)
    if not args.selftest and slot_taken_on_youtube(publish_at):
        log("SLOT_ALREADY_FILLED — another producer filled this slot; exiting cleanly.")
        return

    # 3) Topic + script (Gemini free tier; fallback: pending library entries)
    e, err = make_entry(kind)
    if e:
        if not factory.content_eligible(e):
            raise SystemExit("CONTENT_SCOPE_BLOCKED: " + e["id"])
        append_library(e)
    else:
        log(f"fresh topic unavailable ({err}); trying pending library entries")
        try:
            e = factory.pick_entry(None, kind)
        except SystemExit as ex:
            log("NO ELIGIBLE CONTENT — add topics or fix the Gemini key: " + str(ex)[:200])
            raise
    log(f"=== Actions Factory ({kind}): {e['title']}")

    today = time.strftime("%Y-%m-%d")
    workdir = os.path.join(factory.BASE, "runs", f"{e['id']}_{today}")
    os.makedirs(workdir, exist_ok=True)

    # 4) Footage: fresh per-video Pexels, bundled pool fallback
    used = load_used()
    pairs = fresh_footage(e, workdir, used)
    if pairs is None:
        pairs = pool_footage(e, workdir)

    # Task 3: never ship the same shot twice in one video, and keep a licence
    # record for everything that ends up on screen.
    try:
        import footage_engine
        _kept, _dup = footage_engine.dedupe_pairs(pairs, workdir)
        if _dup:
            log("footage: dropped " + str(len(_dup)) + " near-duplicate clip(s): "
                + json.dumps([d["file"] for d in _dup])[:200])
            pairs = _kept if len(_kept) >= max(3, len(pairs) - 2) else pairs
        e["_licenses"] = [footage_engine.license_record((c[0] or {}), str((c[0] or {}).get("query", "")))
                          for c in pairs]
    except Exception as ex:
        log("footage engine step failed (continuing with raw pairs): " + str(ex)[:140])
    # let the visual QC read the same clip metadata the render used
    try:
        e["_clip_meta"] = [dict((c[0] or {}), tags=(c[0] or {}).get("tags") or []) for c in pairs]
    except Exception:
        e["_clip_meta"] = []

    # 5) Voice + render (Kokoro af_heart, all quality gates inside)
    audio = factory.gen_voice(e, workdir)
    _ck = os.path.join(workdir, ".render_meta.json")
    _want = hashlib.sha1((json.dumps([str(b.get("t", "")) for b in e.get("beats", [])])
                          + json.dumps([c[0].get("file") for c in pairs])).encode()).hexdigest()
    mp4 = os.path.join(workdir, "final.mp4")
    _reused = False
    if os.path.exists(_ck) and os.path.exists(mp4) and os.path.getsize(mp4) > 500000:
        try:
            if json.load(open(_ck)).get("hash") == _want:
                _reused = True
                log("render checkpoint: inputs unchanged - reusing the existing render")
        except Exception:
            pass
    if not _reused:
        mp4 = render_film(e, workdir, pairs, audio)
        try:
            json.dump({"hash": _want, "duration": _mp4_duration(mp4),
                       "clips": len(pairs), "at": time.time()},
                      open(_ck, "w"), indent=1)
        except Exception:
            pass

    if args.selftest:
        _sel_thumbs = _three_thumbs(e, workdir, pairs)
        log("selftest three-thumb: " + ("OK" if _sel_thumbs else "FAILED (AI fallback would cover)"))
        log("selftest thumb files: " + ", ".join(sorted(
            f for f in os.listdir(workdir) if f.startswith("thumb_"))))
        thumb = gemini_json(THUMB_PROMPT.format(title=e["title"]))
        rf = write_report(e, None, None, None, "selftest",
                          (thumb or {}).get("prompt", "n/a") if isinstance(thumb, dict) else str(thumb or "n/a"))
        factory.make_short_from_long(mp4, workdir)
        try:
            import shutil
            shutil.copy(mp4, os.path.join(REPORTS, "selftest_final.mp4"))
        except Exception as ex:
            log("selftest video attach failed: " + str(ex)[:100])
        log("SELFTEST PASS: research -> topic -> footage -> voice -> render + short-cut all OK; "
            "no upload performed. Render: " + mp4)
        return

    # 6) Upload: private + publishAt (strict slot re-check inside factory.upload)
    try:
        _pls = factory.ensure_playlists()
        _nm = factory.playlist_for_title(e["title"])
        _lnk = f"https://www.youtube.com/playlist?list={_pls[_nm]}" if _nm and _nm in _pls else None
    except Exception as ex:
        _lnk = None
        log("playlist link unavailable for description: " + str(ex)[:100])
    # Thumbnail FIRST: the QC gate scores the thumbnail (10 pts) and used to
    # block a video over a file that was only generated after the upload.
    try:
        if not _three_thumbs(e, workdir, pairs):
            if not factory.make_thumb_ai(e, workdir):
                factory.make_thumb(e, workdir, pairs[0][0])
    except Exception as ex:
        log("pre-upload thumbnail failed (continuing): " + str(ex)[:140])
    _qc_total, _qc_sc, _qc_notes = quality_gate(e, mp4, kind, narration_path=audio)
    if _qc_total < QC_MIN_SCORE:
        # Never publish a failed video (owner master prompt §11).
        log(f"QC BLOCKED upload: {_qc_total}/100 < {QC_MIN_SCORE} for {e['id']} "
            f"({'; '.join(_qc_notes)})")
        raise SystemExit(3)
    vid = factory.upload(e, mp4, publish_at, playlist_link=_lnk,
                         allow_override=bool(args.publish_at))

    # 7) Record state (same ledgers the Base44 producer uses)
    st = factory.load_state()
    st["done"][e["id"]] = {"date": today, "videoId": vid}
    factory.save_state(st)
    factory.note_published(e, vid, kind, publish_at)

    # 7a2) File the Long into its topic playlist (owner review 2026-10-06);
    # guarded - upload already succeeded.
    try:
        factory.add_to_playlist(vid, e["title"])
    except Exception as ex:
        log("playlist step failed (continuing): " + str(ex)[:140])

    # 7b) Auto-thumbnail: Gemini image model (footage-frame fallback), applied via API.
    # Guarded: upload already succeeded, so a thumbnail failure must never
    # kill the run or lose the scheduled slot.
    try:
        if not (os.path.exists(os.path.join(workdir, "thumbnail.jpg"))
                or os.path.exists(os.path.join(workdir, "thumb.jpg"))):
            if not _three_thumbs(e, workdir, pairs):
                if not factory.make_thumb_ai(e, workdir):
                    factory.make_thumb(e, workdir, pairs[0][0])
        factory.set_thumbnail(vid, workdir)
    except Exception as ex:
        log("thumbnail step failed (video already uploaded; continuing): " + str(ex)[:140])

    # DAILY cadence (owner 2026-10-07 21:46 BD): 2 Shorts/day.
    # (a) 18:30 BD slot = STANDALONE robot Short, casperpks-style no-skip
    #     robot entertainment (own topic/script/footage, vertical render).
    # (b) 02:30 BD slot = hook-cut of today's Long (unchanged).
    # Booking order matters: the standalone Short books FIRST so it takes
    # the evening 18:30 slot; the hook-cut takes the next 02:30.
    commit_extra = []
    if not args.selftest:
        _robot_short(commit_extra, today)


    # (b) hook-cut Short for the next 02:30 BD slot
    try:
        smp4 = factory.make_short_from_long(mp4, workdir, secs=42, start=0)
        s_e = dict(e)
        s_e["kind"] = "short"
        s_e["id"] = e["id"] + "_short1"
        # ANTI-DUPLICATE-TITLE 2026-10-27: a hook-cut must never repeat the
        # parent's exact title (YouTube reads identical titles as spam - the
        # 17-clone incident). Give it its own angle suffix.
        s_e["title"] = (e["title"][:72] + " — 30 Seconds That Changed It")
        # OWNER 2026-10-11 funnel plan: every hook-cut Short links its Long
        # (the automatable version of the "Related Video" feature, which is
        # Studio-only) so Shorts viewers can jump to the full video.
        s_e["description"] = (e["description"].strip()
                               + f"\n\nFull video: https://youtu.be/{vid}"
                               + "\n\n#Shorts")
        s_pub, s_slot = factory.next_bd_slot("short")
        s_vid = factory.upload(s_e, smp4, s_pub)
        factory.note_published(s_e, s_vid, "short", s_pub)
        st3 = factory.load_state()
        st3["done"][s_e["id"]] = {"date": today, "videoId": s_vid}
        factory.save_state(st3)
        # 2026-10-10 FIX: hook-cut shorts had NO thumbnail step (longs and robot
        # shorts did) — every hook-cut went public with a bare frame. Same
        # flow as the robot short now: PIL v3 landscape thumb + thumbnails.set.
        try:
            if not factory.make_thumb_ai(s_e, workdir):
                factory.make_thumb(s_e, workdir, tf_pairs[0][0])
            factory.set_thumbnail(s_vid, workdir)
        except Exception as ex2:
            log("hook-cut short thumb failed (continuing): " + str(ex2)[:120])
        log(f"hook-cut short: OK videoId={s_vid} scheduledFor={s_pub} ({s_slot})")

        # (c) OWNER 2026-10-11 funnel plan: a SECOND cut from the payoff zone
        # (~55-60% in, the best trick/result beat). Evening update 2026-10-11:
        # owner wants exactly 2 Shorts/day - book only if a slot is still free.
        import subprocess
        try:
            _r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", mp4], capture_output=True, text=True)
            _dur = float(_r.stdout.strip())
        except Exception:
            _dur = 0.0
        s2_pub = None
        if _dur > 120:
            try:
                s2_pub, s2_slot = factory.next_bd_slot("short")
            except SystemExit:
                s2_pub = None
                log("hook-cut-2: no free Short slot (2/day plan) - skipped")
        if s2_pub:
            _start = max(0, min(int(_dur * 0.55), int(_dur) - 45))
            s2_mp4 = factory.make_short_from_long(mp4, workdir, secs=42, start=_start)
            s2 = dict(e)
            s2["kind"] = "short"
            s2["id"] = e["id"] + "_short2"
            s2["title"] = (e["title"][:72] + " — The Part Nobody Shows")
            s2["description"] = (e["description"].strip()
                                 + f"\n\nFull video: https://youtu.be/{vid}"
                                 + "\n\n#Shorts")
            s2_vid = factory.upload(s2, s2_mp4, s2_pub)
            factory.note_published(s2, s2_vid, "short", s2_pub)
            st4 = factory.load_state()
            st4["done"][s2["id"]] = {"date": today, "videoId": s2_vid}
            factory.save_state(st4)
            try:
                if not factory.make_thumb_ai(s2, workdir):
                    factory.make_thumb(s2, workdir, tf_pairs[0][0])
                factory.set_thumbnail(s2_vid, workdir)
            except Exception as ex2:
                log("hook-cut-2 thumb failed (continuing): " + str(ex2)[:120])
            log(f"hook-cut-2 short: OK videoId={s2_vid} scheduledFor={s2_pub} ({s2_slot})")
    except (Exception, SystemExit) as ex:
        log("hook-cut short step failed (long already uploaded; continuing): " + str(ex)[:140])

    # 8) Thumbnail prompt + Bengali report, committed back to the repo
    thumb = gemini_json(THUMB_PROMPT.format(title=e["title"]))
    thumb_txt = (thumb or {}).get("prompt", "n/a") if isinstance(thumb, dict) else str(thumb or "n/a")
    rf = write_report(e, vid, publish_at, slot_local, "produce", thumb_txt)
    log(f"scheduled slot (Dhaka): {slot_local}")
    for rel, loc, msg in [
        ("factory/library.json", os.path.join(FACT, "library.json"), "state: library entry " + e["id"]),
        ("factory/state.json", os.path.join(FACT, "state.json"), "state: done " + e["id"]),
        ("factory/published_log.json", os.path.join(FACT, "published_log.json"), "state: published " + e["id"]),
        ("factory/used_footage.json", USED_F, "state: footage ledger"),
        (os.path.relpath(rf, REPO), rf, "report: " + e["id"]),
    ]:
        if os.path.exists(loc):
            commit_file(rel, loc, msg)
    for rel, loc, msg in commit_extra:
        if os.path.exists(loc):
            commit_file(rel, loc, msg)
    log("RESULT " + json.dumps({
        "id": e["id"], "status": "scheduled", "videoId": vid,
        "scheduledFor": publish_at,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "slot_dhaka": str(slot_local)}))


if __name__ == "__main__":
    main()
