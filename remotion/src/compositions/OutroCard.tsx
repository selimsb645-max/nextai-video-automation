import React from "react";
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Stage } from "../components/Stage";
import { breathe, COLORS, FONTS, SPRING } from "../theme";

/**
 * OutroCard — 2s close. Restrained on purpose: a busy outro reads as an ad.
 * Skill compliance: staggered springs (brand, line, underline) and a breathing mark.
 */
export const OutroCard: React.FC<{ brand?: string; line?: string }> = ({
  brand = "NEXTAI VISION",
  line = "SUBSCRIBE FOR DAILY AI BREAKDOWNS",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const mark = spring({ frame, fps, config: SPRING.smooth });
  const copy = spring({ frame: frame - 8, fps, config: SPRING.smooth });
  const rule = spring({ frame: frame - 16, fps, config: SPRING.bouncy });

  return (
    <Stage light="center">
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              fontFamily: FONTS.display,
              fontSize: 120,
              color: COLORS.ink,
              letterSpacing: 6,
              opacity: mark,
              transform: `scale(${0.96 + mark * 0.04}) translateY(${breathe(frame, fps) * 0.8}px)`,
            }}
          >
            {brand}
          </div>
          <div
            style={{
              fontFamily: FONTS.body,
              fontWeight: 800,
              fontSize: 40,
              letterSpacing: 7,
              color: COLORS.muted,
              marginTop: 26,
              opacity: copy,
              transform: `translateY(${(1 - copy) * 18}px)`,
            }}
          >
            {line}
          </div>
          <div
            style={{
              width: 140 * rule,
              height: 8,
              backgroundColor: COLORS.accent,
              margin: "34px auto 0",
            }}
          />
        </div>
      </AbsoluteFill>
    </Stage>
  );
};
