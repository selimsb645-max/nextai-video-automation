import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONTS } from "../theme";

/**
 * OutroCard — 2s close. The subscribe ask is a single line with the channel
 * mark; no animation tricks, because a busy outro reads as an ad.
 */
export const OutroCard: React.FC<{ brand?: string; line?: string }> = ({
  brand = "NEXTAI VISION",
  line = "SUBSCRIBE FOR DAILY AI BREAKDOWNS",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 200 } });
  const dot = interpolate(frame, [10, 30], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.stage, justifyContent: "center", alignItems: "center" }}>
      <AbsoluteFill
        style={{ background: `radial-gradient(900px 500px at 50% 120%, ${COLORS.accentSoft}, transparent 70%)` }}
      />
      <div style={{ textAlign: "center", opacity: s }}>
        <div style={{ fontFamily: FONTS.display, fontSize: 120, color: COLORS.ink, letterSpacing: 6 }}>
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
          }}
        >
          {line}
        </div>
        <div
          style={{
            width: 140 * dot,
            height: 8,
            backgroundColor: COLORS.accent,
            margin: "34px auto 0",
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
