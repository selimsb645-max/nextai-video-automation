# Skills used by this project

| Skill | Source | License | How we use it |
|---|---|---|---|
| remotion-motion-graphics | haidrrrry/claude-remotion-skill | MIT | Vendored in `remotion-motion-graphics/`. Its ten rules are the review checklist for every component in `remotion/src/`. |

## The ten rules (short form, for review)

1. No linear interpolation — every `interpolate()` gets an easing, every entrance a spring.
2. Entrances move 2–3 properties together; a lone fade is forbidden.
3. Stagger everything 3–6 frames.
4. Exits exist and are faster than entrances.
5. Five layers in every scene: mesh → assets → type → grade → grain + vignette.
6. Ken Burns on stills; `OffthreadVideo` for footage.
7. Anything on screen over 2s breathes.
8. All timing derives from `fps`.
9. One theme object; no inline hex or easing.
10. Render, extract frames, look, fix, re-render.

## Compliance status of our components (2026-11-21)

| Component | 1 | 2 | 3 | 4 | 5 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|
| IntroCard | ✓ springs + EASE.out | ✓ opacity+translate+scale | ✓ 6f | ✓ | ✓ Stage | ✓ | ✓ | ✓ |
| DataCard | ✓ EASE.out counter | ✓ | ✓ 8f | ✓ | ✓ Stage | ✓ | ✓ | ✓ |
| KineticCaptions | ✓ EASE.out/in | ✓ | ✓ 4f per word | ✓ | ✓ Stage | n/a | ✓ | ✓ |
| OutroCard | ✓ springs | ✓ | ✓ 8f | ✓ | ✓ Stage | ✓ | ✓ | ✓ |

Rule 6 applies once real footage is composited inside a Stage; the proof reel has no footage yet.
Rule 10 is why every change here ends with a render plus a frame check.

## Rejected, with reasons

- OpenMontageInc/OpenMontage — AGPL-3.0 against a public repo with no LICENSE.
- Vincentwei1021/video-shotcraft (Apache-2.0), znyupup/ai-video-editing-skill (MIT) — vlog
  workflows built around human-shot footage and speech; our source is silent stock B-roll.
