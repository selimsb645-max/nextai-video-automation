#!/usr/bin/env python3
"""NextAI Content Factory — GitHub Actions autonomous runner.

Runs a full production turn on free infrastructure only:
Google News RSS + Gemini free-tier API (topic + script), Pexels free API
(fresh per-video footage, owner rule 2026-10-04; bundled pool as fallback),
local Kokoro TTS (am_michael, emotion-aware), ffmpeg render with quality
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


def _http(url, headers=None, data=None, method=None, timeout=90):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers or {})
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


ENTRY_PROMPT = """You are the topic researcher and script writer for a US-audience English YouTube channel about AI (NextAI Vision). OWNER RULE 2026-10-12: the TOPICS stay the same — videos cover ALL types of AI: ChatGPT/OpenAI, Claude/Anthropic, Gemini/Google AI Studio, Grok/xAI, DeepSeek, Qwen, and EVERY other AI company, platform, tool, model or AI technology; also AI-linked science discoveries and robots. ONLY the PRESENTATION STYLE follows the channel "Farid Talks AI and Tech" (owner reference video 2026-10-12, s8dAwNs14jo): a casual, witty, STORY-DRIVEN AI news commentary told by a human host — NOT a newsreader, NOT a tutorial, NOT a listicle.
From the headlines below pick exactly ONE real, currently-trending topic (last 7 days, US-interest). Allowed pillars, in priority order: (1) AI updates and NEW MODEL LAUNCHES from ChatGPT/OpenAI, Claude/Anthropic, Gemini/Google AI Studio, Grok/xAI, DeepSeek, Qwen — ANY AI update from ANY AI company counts; (2) AI-linked science discoveries; (3) robots and new AI technology. NEVER medical advice, no politics, no tragedy exploitation.
SELECTION RULE: the DEMAND COUNTS below show how many US headlines each topic cluster got in the last 7 days — this is the search-demand evidence. Pick a topic from the cluster with the HIGHEST count that still has one strong, specific story. PREFER stories with NARRATIVE DRAMA: someone built/released something bold, a ban, a feud, a record, an exposure, a plot twist, a big name doing something unexpected (e.g. "a YouTuber built an uncensored AI and OpenAI banned him twice"). Plain feature launches are second choice.
OWNER DATA 2026-10-11: robotics real-test/lab-demo stories and side-by-side AI model comparisons are this channel's best performers — when demand counts are close, pick one of those angles.

SCRIPT FORMAT — an AI news story told by a real host:
- First-person, conversational, contractions everywhere, short punchy sentences, occasional wit. Talk TO one viewer ("you"), react to the story ("Here's the funny part", "Now this is where it gets weird", "And yes, you heard that right").
- Narration: total 780-860 words, split into 22-27 beats.
- Beat 1 (10-14 seconds, cold open): the hook in one breath — the boldest concrete fact or number AND the name at the center of the drama. No greetings, no "in this video".
- Beats 2-3 (fast hook zone, max ~50 words total): what just happened + the single most surprising fact. Then the ROADMAP in one curiosity-framed sentence: "Today we'll look at what X actually is, why Y happened, and what it means for you."
- Beat 4 (channel stamp, ~12 words): one line naming today's real date and the channel, e.g. "It's October 12th, and you're watching NextAI Vision."
- Middle beats (26-38 words each): tell the STORY chronologically — what happened, who said what, how it escalated; then explain the one technical bit simply enough for a beginner; weave in specific numbers, dates and model names wherever the sources give them.
- QUOTES: include at least ONE short real quote from the story as reported in the headlines/snapshots, introduced naturally ("he said, quote, ..."). Cite at least ONE named source or outlet ("according to ...").
- WIT: 1-3 light humorous asides per video — playful, never cruel, never cringe, family-safe.
- PAYOFF: keep the best twist, reveal or resolution for the FINAL THIRD so viewers stay to the end.
- Last two beats: a short ironic callback or "one more thing" twist if the story has one, then END with a comment question tied to the story ("Tell me in the comments: ...") and a quick sign-off ("See you in the next one.").
- OWNER DATA 2026-10-11: average view duration on 5-min longs is only 57s — assume viewers decide in the first 30 seconds; nothing slow, nothing generic, no throat-clearing before the surprise.

HARD RULES:
- Title: MAX 50 CHARACTERS (mobile viewers must read the full message at a glance), must contain "AI" or the platform/company name AND one of these story-drama hook patterns: Banned / Built / Just / Shocking / Warning / Nobody / Truth / Finally / vs.
- TITLE SEARCHABILITY (owner 2026-10-16: 70% of views come from SEARCH, and drama-only titles rank for nothing): the title MUST contain the exact SEARCHABLE SUBJECT NAME a viewer would actually type into YouTube/Google — the model name (e.g. "GPT-5.1", "Claude Opus 4.5", "Gemini 3"), the company name, the robot name, or the law/event name — spelled EXACTLY as in the headlines. GOOD: "Claude Opus 4.5 Just Beat GPT-5.1", "Tesla Optimus Banned Itself". BAD: "AI Agent Hacked a Government. Nobody Told It To" (no searchable subject, nobody searches this).
- TITLE PATTERNS that work (pick the best fit, never the same one twice in a row): "<Name> Built an AI. <Company> Banned Him.", "X Just Happened — Here's Why It Matters", "The Truth About X", "X Banned Y. Here's Why.", "Nobody Expected This From X", "X vs Y: It's Not Even Close".
- TITLE VARIETY: do NOT reuse the same title template (like "AI Warning: ...") that appears in the RECENT TITLES list; at most one title there shares its first two words with yours.
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


CONTINUE_PROMPT = """You are continuing a US-audience YouTube AI news commentary (casual, witty, story-driven host style like "Farid Talks AI"). Write the NEXT {n} beats (each 26-38 words) that CONTINUE the story from where it stops — do not repeat earlier text. Keep the drama escalating toward the final-third payoff. Every beat gets a 2-4 word "kw" stock-footage search phrase. Return ONLY JSON: {{"beats":[{{"t":"<sentence>","kw":"<footage phrase>"}}]}}.

TITLE: {title}
STORY SO FAR (all beats in order):
{sofar}
"""


EXPAND_PROMPT = """You are expanding a US-audience YouTube AI news commentary (casual witty host style). Rewrite EVERY beat below to be 26-38 words each (add concrete detail, numbers, quotes — keep the same meaning, order and tone). Keep exactly the same number of beats and each "kw" phrase. COUNT WORDS per beat: fewer than 30 is invalid. Return ONLY JSON: {{"beats":[{{"t":"...","kw":"..."}}]}}.

TITLE: {title}
BEATS TO EXPAND:
{beats}"""


SHORT_PROMPT = """
You are the script writer for a US-audience English YouTube SHORT (vertical, under 60 seconds) that MUST be about REAL ROBOTS. Style (owner reference 2026-10-11: @androidalians): ONE robot, ONE dramatic STORY told like a mini-movie, poster-style visuals, impossible to scroll past. From the headlines below pick exactly ONE real, currently-trending robot story (last 7 days, US-interest) about ONE SPECIFIC NAMED ROBOT (a specific humanoid, robot dog, drone swarm, or competition robot - use its real model name). NEVER medical advice, no politics, no tragedy exploitation. If no robot headline is trending, pick the most visually dramatic recent robot milestone instead.

STORY STRUCTURE (a mini-movie, NOT a news report):
- Beat 1 (1-2s): cold open ON the most dramatic moment or the shocking NUMBER ("This robot just walked 21 kilometers").
- Middle beats: the STORY of how it happened - escalate beat by beat, present tense, short punchy sentences.
- Final beat: the payoff (the impossible thing achieved) + one short closing question.
- Fun, high-energy storytelling tone. Emotional punctuation. Hold the payoff to the END.

HARD RULES:
- Title: MAX 50 CHARACTERS, must contain "Robot" AND one hook word: Shocking / Warning / Banned / Solved / Impossible / Never.
- headline: 2-5 ALL-CAPS poster words naming the robot or its wow fact (e.g. "ROBOTIC OVERLORDS", "21KM ROBOT"). It gets burned BIG on screen.
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
                                         demand=demand_txt, recent=recent_txt), models=models)
        if not val:
            # model set exhausted (quota/overload) — try the next ladder entry
            # instead of giving up (fixes premature "gemini unavailable").
            log(f"gemini unavailable on {models[0]}+ set; trying next ladder")
            continue
        try:
            # OWNER FIX 2026-10-08: lite models cap ~300 words/call and
            # 3.5-flash is often 503 — expand a short draft by asking for
            # the next beats until the 600-700 word target is reached.
            if kind == "long" and 120 <= len(val["narration"].split()) < 560 \
                    and 8 <= len(val.get("beats", [])) <= 20:
                for _ci in range(3):
                    _w = len(val["narration"].split())
                    _b = len(val["beats"])
                    if _w >= 560 or _b >= 24:
                        break
                    so_far = "\n".join(f"- {b['t']}" for b in val["beats"])
                    val2 = gemini_json(CONTINUE_PROMPT.format(
                        n=min(8, 24 - _b), title=val["title"], sofar=so_far),
                        models=["gemini-flash-lite-latest", "gemini-3.5-flash-lite"])
                    if not val2 or not isinstance(val2.get("beats"), list):
                        break
                    add = [b for b in val2["beats"] if b.get("t")][:min(8, 24 - _b)]
                    if not add:
                        break
                    val["beats"] += add
                    val["narration"] = " ".join(b["t"] for b in val["beats"])
                    log(f"continuation: +{len(add)} beats, now {len(val['narration'].split())} words")
                # still short on words -> expand every beat to 30-38 words
                if len(val["narration"].split()) < 560 and 16 <= len(val["beats"]) <= 24:
                    _bt = "\n".join(f"- {b['t']} |kw: {b.get('kw', '')}"
                                    for b in val["beats"])
                    val3 = gemini_json(EXPAND_PROMPT.format(
                        title=val["title"], beats=_bt),
                        models=["gemini-flash-lite-latest", "gemini-3.5-flash-lite",
                                "gemini-3.5-flash"])
                    if val3 and isinstance(val3.get("beats"), list) \
                            and 16 <= len(val3["beats"]) <= 24 \
                            and all(b.get("t") for b in val3["beats"]):
                        val["beats"] = val3["beats"]
                        val["narration"] = " ".join(b["t"] for b in val["beats"])
                        log(f"expand-beats: now {len(val['narration'].split())} words")
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
                        (560 <= words <= 720 and 16 <= len(beats) <= 24))
            # OWNER 2026-10-16 SEARCHABILITY GUARD: 70% of views come from
            # search; a drama-only title no one searches gets zero reach.
            # The model must emit "subject" (the exact searchable name) and
            # it must appear verbatim in the title AND in the description.
            _subj = " ".join(str(val.get("subject") or "").split()).lower()
            _subj_ok = bool(_subj) and _subj in tl and _subj in str(val.get("description", "")).lower()
            if kind == "short":
                # OWNER 2026-10-07 21:46 BD: standalone shorts are ROBOT
                # videos (casperpks-style); must be robot-focused.
                ok = (_wlen_ok
                      and _subj_ok
                      and len(val["title"]) <= 52
                      and "robot" in (val["title"] + " " + val["narration"]).lower()
                      and any(h in tl for h in HOOKS)
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
                if not any(h in tl for h in HOOKS):
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
    return None, "no valid entry from gemini"


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


def fresh_footage(e, workdir, used):
    """Owner rule 2026-10-04: per-video fresh topic-matched Pexels footage.

    Requires PEXELS_API_KEY; on any failure returns None so the caller falls
    back to the bundled local pool (factory.pick_footage).
    """
    if not PEXELS_KEY:
        log("footage: no PEXELS_API_KEY — using bundled pool (fallback)")
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
        orient = "portrait" if e.get("kind") == "short" else "landscape"
        url = ("https://api.pexels.com/videos/search?query=" +
               urllib.parse.quote(kw) + f"&per_page=15&orientation={orient}&size=medium")
        try:
            res = json.loads(_http(url, headers={"Authorization": PEXELS_KEY}, timeout=30))
            pick = None
            for v in res.get("videos", []):
                vid = v["id"]
                if vid in used["used"] or vid in used_here:
                    continue
                if (v.get("duration") or 0) < 4:
                    continue
                files = [f for f in v.get("video_files", [])
                         if f.get("file_type") == "video/mp4"
                         and (f.get("width") or 0) >= (720 if orient == "portrait" else 1280)
                         and (f.get("height") or 0) >= (1280 if orient == "portrait" else 720)]
                if files:
                    files.sort(key=lambda f: (f.get("width") or 0), reverse=True)
                    pick = (v, files[0])
                    break
            if not pick:
                raise RuntimeError("no unused relevant clip")
            v, f = pick
            dst = os.path.join(FACT, "footage", "fresh", f"{v['id']}.mp4")
            data = _http(f["link"], timeout=180)
            with open(dst, "wb") as fh:
                fh.write(data)
            used_here.add(v["id"])
            used["used"].append(v["id"])
            clips.append({"file": f"fresh/{v['id']}.mp4", "dur": v["duration"]})
            log(f"beat {i}: fresh pexels clip {v['id']} for '{kw}' ({v['duration']}s)")
            time.sleep(0.5)
        except Exception as ex:
            log(f"fresh footage failed beat {i} ({str(ex)[:100]}) — falling back to pool")
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
            try:
                r_e = factory.pick_entry(None, "short")
            except (Exception, SystemExit) as ex:
                r_e = None
                log("robot short library empty: " + str(ex)[:100])
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
**Topic pillar:** {e.get('content_pillar')}  |  **Sources:** {', '.join(e.get('verified_sources', [])[:2])}

## Thumbnail prompt (owner makes it in ChatGPT)
{extra}

## Report (বাংলা)
ভিডিও তৈরি হয়েছে Actions রানার দিয়ে (কোনো Base44 ক্রেডিট খরচ হয়নি)।
থাম্বনেল উপরের প্রম্পট দিয়ে ChatGPT-তে বানিয়ে নিচে।
""")
    return f


THUMB_PROMPT = """Write ONE ready-to-use image-generation prompt (6-8 lines, English) for a 16:9 YouTube thumbnail about: "{title}". Style: clean tech-explainer, high contrast, bold 3D text with the main hook, dark background with teal/orange accents, no real logos, no faces, no watermark. Output only the prompt text."""


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="long", choices=["long", "short"])
    ap.add_argument("--selftest", action="store_true",
                    help="run the full pipeline but never upload")
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

    # 5) Voice + render (Kokoro am_michael, all quality gates inside)
    audio = factory.gen_voice(e, workdir)
    mp4 = factory.render(e, workdir, pairs, audio)

    if args.selftest:
        tf = factory.make_thumb_ai(e, workdir)
        log("selftest thumb-ai: " + ("OK " + tf if tf else "FAILED (fallback would cover)"))
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
    vid = factory.upload(e, mp4, publish_at, playlist_link=_lnk)

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
        if not factory.make_thumb_ai(e, workdir):
            tf_pairs = pairs
            factory.make_thumb(e, workdir, tf_pairs[0][0])
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
        s_e["title"] = e["title"][:95]
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
            s2["title"] = e["title"][:95]
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
