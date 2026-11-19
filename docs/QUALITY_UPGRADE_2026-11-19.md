# Quality upgrade — 2026-11-19 (owner delegation via Muse)

Owner's instruction (Bengali, 2026-11-19): the automated videos are not
good enough; make them the way a professional human editor would, matching
the reference channel **@airevolutionx**, keep the system fully automatic
(topic -> script -> footage -> voice -> render -> scheduled upload), and
fix everything without needing further instructions.

## What the reference channel actually does (measured 2026-11-19)

Studied @airevolutionx's current uploads (18K-136K views on the last
10 days of Longs, same news cycle as ours - e.g. their GPT-6.2 Astra
video vs our "OpenAI Just Released GPT-6.2 for Law"):

- Titles run **55-70 characters**, front-loaded: searchable subject +
  tension/conflict in the first ~40 chars, claim completed after
  ("OpenAI Just Embarrassed Itself With New GPT 6.2 Astra...",
  "Google Just Gives the World Its Most Powerful AI Model Ever: Carbon").
- The angle is the **conflict**, not the announcement: winner vs loser,
  promise vs backlash, breakthrough vs danger.
- Descriptions open with a summary + twist, then a "What You'll See"
  list where claims carry a **SOURCE** link.
- Cinematic documentary pacing: a distinct, exactly-matching clip per
  sentence, real timed captions, per-scene visual treatment.

## Root cause found in our system

The Cinematic Engine (`factory/cine/` - storyboard, real ASS captions,
per-scene motion/grade, mastered audio with ducking, 14-check QC) was
built and tested but **never enabled**: `factory.yml` did not set
`ENABLE_CINEMATIC_EDITOR`, so every production video still used the old
`factory.render()` (one flat grade, one 0.6s crossfade everywhere,
4-word burned key phrases instead of subtitles, no storyboard).
Also: published reports contained **no QC score**, and the verified
sources collected for each story never appeared in the YouTube
description.

## Changes made

1. `.github/workflows/factory.yml` - `ENABLE_CINEMATIC_EDITOR: "true"`
   on the production step. Fallback safety is in `render_film()`: the
   cinematic cut is accepted only if its own QC passes; any failure or
   crash falls back to `factory.render()`. Rollback = set it to "false".
2. `actions/runner.py` - `render_film()` records which renderer produced
   the cut in `e["_renderer"]` (cinematic PASS / fallback + reason).
3. `actions/runner.py` - `write_report()` accepts the QC result and
   every produce report now prints: QC total + breakdown, renderer,
   duration, QC notes. (Before: slot, link and thumbnail prompt only.)
4. `actions/runner.py` - Long title rule changed from MAX 50 chars to
   **55-70 chars, subject + tension in the first 40**, conflict angle
   preferred over neutral announcements; the deterministic title repair
   cap (50 -> 70), its hook-word list, and the QC SEO length check
   (52 -> 72) were aligned. Shorts title rules unchanged.
5. `factory/factory.py` - `upload()` now appends a **Sources:** section
   (up to 3 verified source URLs) to the YouTube description.

## Not changed (owner's standing rules)

- Voice stays Kokoro `af_heart`. No paid APIs / image / voice.
- Shorts stay off; `ENABLE_VERTICAL_COPY` stays off.
- Length stays topic-driven (min 1400 words, no ceiling).
- Schedule, slots and the QC publish gate (>= 85) are untouched.

## Verification

- Full test suite before and after: **71 passed** (local venv, Python
  3.12; suite also green on the owner's CI per 2026-11-19 commits).
- `python3 -m py_compile actions/runner.py factory/factory.py` - OK.
- First scheduled production run after this change is the real-world
  check: its report in `actions/reports/` must show the Quality section
  and which renderer produced the cut. If the cinematic engine ever
  fails its own QC, the report will say so (fallback), and the slot is
  still filled by the old renderer.
