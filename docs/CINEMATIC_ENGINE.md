# Next AI Vision 4 — Cinematic Editing Engine

Status: **implemented, tested, not yet enabled in production.**
Production renderer is untouched until `ENABLE_CINEMATIC_EDITOR=true` is set by you.

## 1. Audit of what already existed (measured, not assumed)

| Area | Where | What it actually does |
|---|---|---|
| Runner | `actions/runner.py` (1471 lines) | topic research, library, footage, voice, render, QC, upload, scheduling |
| Render | `factory.render()` (`factory/factory.py`) | one FFmpeg graph: trim → slow-mo → xfade (0.6 s), grade, grain, vignette, burned 4-word key phrase |
| Voice | `factory.gen_voice()` | Kokoro `af_heart`, per-beat synthesis, broadcast chain, `loudnorm -16 LUFS` |
| Footage | `factory.pick_footage()` | Pixabay per beat + Commons fallback, ledger to avoid reuse across videos |
| Thumbs | `factory.make_thumb()` | FLUX via Cloudflare GPU + Anton typography |
| QC | `factory/qc_visual.py`, `quality_gate()` | blackdetect, freezedetect, dhash/hue dupes, LUFS, 100-point gate |
| CI | `.github/workflows/factory.yml` (+ 4 others) | scheduled longs/shorts, no GPU |

Known bottlenecks found: one flat grade for the whole film, identical crossfade
length everywhere, key-phrase captions instead of real subtitles, no storyboard
artifact (nothing to debug against), no machine-readable QC file, and no way to
render a candidate edit without touching production.

## 2. New architecture (additive, behind a flag)

```
factory/cine/
  storyboard.py    narration -> scenes (id, text, start/end, description,
                   search_query, visual_type, transition, motion_style)
  visual_match.py  Pixabay -> Commons -> Internet Archive, download verified by
                   ffprobe, dHash + hue dedupe, licence manifest, card fallback
  motion.py        per-scene Ken Burns / pan / push, grade rotation, grain,
                   vignette + xfade timeline assembly
  captions.py      ASS subtitles, word timing when available, keyword accent
  audio.py         narration re-normalise, original synthesised bed,
                   sidechain ducking, -14 LUFS master
  qc.py            14 measured checks -> qc_report.json
  editor.py        orchestrator + CLI + baseline/compare mode
```

Hooked into production at one place only:
`actions/runner.py::render_film()` — flag off ⇒ `factory.render()` exactly as
before; flag on ⇒ new engine, and its own QC must pass or the run falls straight
back to `factory.render()`.

## 3. Free setup

1. Nothing to buy. FFmpeg, Pillow, numpy only.
2. Optional: `PIXABAY_API_KEY` (already a repo secret) gives HD footage. Without
   it the engine uses Wikimedia Commons and Internet Archive public-domain film.
3. Run the test harness: Actions → *Cinematic Engine Selftest* → Run workflow.
   Inputs: height (1080/720), quality (standard/draft/high), compare (on/off).
4. To adopt in production, set repository variable/env `ENABLE_CINEMATIC_EDITOR=true`.
   Rollback = set it back to `false` (or delete it). No other change is needed.

## 4. Honest limitations

* Caption word timing is **estimated by character weight** unless the TTS layer
  supplies measured timings; the report always states which one was used.
* Internet Archive sources can be perceptual-quality limited (some prelinger
  items are SD). `source_resolution` in the QC report flags this instead of
  hiding it.
* Wikimedia Commons returns HTTP 429 on shared/CI IPs; the provider cools down
  and the next source takes over. Downloads are never faked.
* Freeze/black detection is automated, but **cinematic taste is not**; the QC
  report says so explicitly.
* Scene count is derived from narration length and real pauses, so a very short
  script can merge into fewer scenes than beats.
