/**
 * Stage — the five-layer stack every scene sits on.
 *
 * Rule 5 of the vendored skill (skills/remotion-motion-graphics/SKILL.md): a flat solid
 * background is the single loudest tell of a generated video. Bottom to top:
 *
 *   1 background mesh   - two soft radial washes, never one flat colour
 *   2 assets            - footage / images (children)
 *   3 graphics + type   - also children, drawn above the mesh
 *   4 colour grade      - a warm-cool split so the frame has depth
 *   5 grain + vignette  - film texture; kills the plastic digital look
 *
 * The grain is a deterministic noise pattern seeded by frame number, so a re-render of the
 * same frame produces the same pixels (Remotion requires determinism).
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { COLORS } from "../theme";

const Grain: React.FC<{ opacity?: number }> = ({ opacity = 0.055 }) => {
  const frame = useCurrentFrame();
  // A 3x3 tile of pseudo-random dots, shifted each frame. Cheap, and reads as film grain
  // at 1080p because the tile is scaled up with nearest-neighbour sampling.
  const seed = (frame * 37) % 100;
  return (
    <AbsoluteFill
      style={{
        opacity,
        mixBlendMode: "overlay",
        backgroundImage: `url("data:image/svg+xml;utf8,${encodeURIComponent(
          `<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'>
             <filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9'
               numOctaves='2' seed='${seed}'/></filter>
             <rect width='120' height='120' filter='url(#n)'/>
           </svg>`,
        )}")`,
        backgroundSize: "120px 120px",
        pointerEvents: "none",
      }}
    />
  );
};

const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      background:
        "radial-gradient(ellipse 78% 62% at 50% 46%, transparent 42%, rgba(0,0,0,0.55) 100%)",
      pointerEvents: "none",
    }}
  />
);

export const Stage: React.FC<{
  children?: React.ReactNode;
  /** where the key light sits — moves the wash so scenes do not look stamped from a template */
  light?: "left" | "right" | "center";
  grain?: number;
}> = ({ children, light = "left", grain = 0.055 }) => {
  const at =
    light === "right" ? "82% 12%" : light === "center" ? "50% 8%" : "14% 92%";
  const at2 = light === "right" ? "18% 96%" : light === "center" ? "50% 96%" : "86% 8%";
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.stage }}>
      {/* 1 background mesh */}
      <AbsoluteFill
        style={{
          background:
            `radial-gradient(1150px 720px at ${at}, rgba(255,45,45,0.20), transparent 68%),` +
            `radial-gradient(900px 620px at ${at2}, rgba(64,110,255,0.16), transparent 72%),` +
            `linear-gradient(160deg, ${COLORS.stageLift} 0%, ${COLORS.stage} 62%)`,
        }}
      />
      {/* 2 + 3 assets and type */}
      {children}
      {/* 4 colour grade: cool shadows, warm highlights */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(255,180,120,0.05) 0%, rgba(0,0,0,0) 40%, rgba(30,60,140,0.10) 100%)",
          mixBlendMode: "soft-light",
        }}
      />
      {/* 5 grain + vignette */}
      <Grain opacity={grain} />
      <Vignette />
    </AbsoluteFill>
  );
};
