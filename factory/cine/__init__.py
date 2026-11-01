"""Cinematic documentary editing engine for NextAI Vision 4.

Design rules (owner master upgrade 2026-11-01):
  * never replace the working renderer - this package is opt-in through
    ENABLE_CINEMATIC_EDITOR and falls back to factory.render on any failure;
  * free/open-source only: FFmpeg + Pillow + numpy, no paid API, no model
    downloads per run;
  * honest reporting: every stage writes what it actually did, estimated
    timing is labelled as estimated, and failures are recorded, never hidden.

Modules
  storyboard    script/beats -> storyboard.json (scene timing, queries, types)
  visual_match  scene -> licensed asset, with dedupe + manifest + fallbacks
  motion        FFmpeg motion/transition/grade graph builders
  captions      ASS subtitle authoring (word-timed when available)
  audio         narration sync, music bed synthesis, ducking, loudness
  qc            machine-readable QC report + pass/fail gate
  editor        orchestrator (build a film end to end) + CLI
"""

__all__ = ["storyboard", "visual_match", "motion", "captions", "audio", "qc", "editor"]
