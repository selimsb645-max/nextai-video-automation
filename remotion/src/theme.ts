/**
 * Shared design tokens for every NextAI Vision graphic.
 *
 * Why these values: the channel's reference (@airevolutionx) uses a dark
 * near-black stage, one hot accent colour, and very heavy condensed type for
 * the numbers/headlines. Everything here is deliberate so a new composition
 * cannot drift off-brand.
 */
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

/** 1920x1080 @ 30fps is what the factory already publishes. */
export const VIDEO = { width: 1920, height: 1080, fps: 30 };
