# Attribution

`SKILL.md` in this folder is vendored unmodified from
**haidrrrry/claude-remotion-skill** — "Remotion Motion Graphics" (MIT, © 2025 haidrrrry).
Source: https://github.com/haidrrrry/claude-remotion-skill

Why it is here: it is the only skill pack found that addresses the actual failure mode —
untrained Remotion output looks generic (linear easing, opacity-only fades, simultaneous
entrances, flat backgrounds). The ten non-negotiable rules in SKILL.md are the checklist our
components in `remotion/src/` are reviewed against.

MIT obligations kept: the LICENSE file sits beside the original text, and this notice records
the source. Our own components are NOT copies of its example code; they implement the rules.

Reviewed and rejected on the same day:
- OpenMontageInc/OpenMontage — AGPL-3.0, incompatible with this public repo (already rejected
  once on 2026-11-01 for the same reason).
- Vincentwei1021/video-shotcraft (Apache-2.0) and znyupup/ai-video-editing-skill (MIT) —
  both are vlog/product-video workflows built around human-shot source footage. Our footage
  is stock B-roll with no speech in it, so their cut-on-silence and transcript-driven editing
  core does not apply.
