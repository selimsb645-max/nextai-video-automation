/**
 * Single source of truth for every graphic (skill rule 9: never inline a hex or an easing).
 *
 * The easings and spring presets come from the vendored motion-graphics skill — linear
 * interpolation is forbidden because it is the clearest tell of a generated video.
 */
import { Easing } from "remotion";

export const COLORS = {
  stage: "#08090C",
  stageLift: "#101319",
  ink: "#FFFFFF",
  muted: "#9AA4B2",
  accent: "#FF2D2D",
  accentSoft: "rgba(255,45,45,0.16)",
  rule: "rgba(255,255,255,0.10)",
};

export const FONTS = {
  display: '"Anton", "Impact", "Arial Narrow", sans-serif',
  body: '"Inter", "DejaVu Sans", Arial, sans-serif',
};

export const EASE = {
  out: Easing.bezier(0.16, 1, 0.3, 1),      // entrances
  inOut: Easing.bezier(0.83, 0, 0.17, 1),   // moves, Ken Burns
  in: Easing.bezier(0.7, 0, 0.84, 0),       // exits only
};

export const SPRING = {
  snappy: { damping: 14, stiffness: 160, mass: 0.6 },
  smooth: { damping: 20, stiffness: 90, mass: 1 },
  bouncy: { damping: 11, stiffness: 170, mass: 0.7 },
};

/** 1920x1080 @ 30fps is what the factory already publishes. */
export const VIDEO = { width: 1920, height: 1080, fps: 30 };

/** Rule 7: anything on screen longer than 2s breathes. Returns a tiny offset. */
export const breathe = (frame: number, fps: number, amount = 1.6) =>
  Math.sin((frame / fps) * Math.PI) * amount;
