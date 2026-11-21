import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONTS } from "../theme";

/**
 * IntroCard — the first 2.5s of every video.
 *
 * Design intent: a cold open that reads as a broadcast title, not a template.
 * A red bar sweeps in, the wordmark lands, and the headline rises under a
 * hairline rule. All motion is spring-driven so it settles instead of stopping.
 */
export const IntroCard: React.FC<{
  brand?: string;
  headline?: string;
  kicker?: string;
}> = ({ brand = "NEXTAI VISION", headline = "THE KICK FAILED", kicker = "AI NEWS" }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();

  const bar = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 22 });
  const mark = spring({ frame: frame - 8, fps, config: { damping: 14, mass: 0.7 } });
  const head = spring({ frame: frame - 20, fps, config: { damping: 18 } });
  const rule = interpolate(frame, [26, 44], [0, width * 0.62], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.stage, overflow: "hidden" }}>
      {/* stage light: a single soft red glow keeps the frame from looking flat */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(1200px 620px at 18% 108%, ${COLORS.accentSoft}, transparent 70%)`,
        }}
      />
      <AbsoluteFill style={{ padding: "120px 140px", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
          <div
            style={{
              width: 84 * bar,
              height: 10,
              backgroundColor: COLORS.accent,
              borderRadius: 2,
            }}
          />
          <div
            style={{
              fontFamily: FONTS.body,
              fontSize: 34,
              letterSpacing: 10,
              fontWeight: 800,
              color: COLORS.ink,
              opacity: mark,
              transform: `translateX(${(1 - mark) * -18}px)`,
            }}
          >
            {brand}
          </div>
          <div
            style={{
              fontFamily: FONTS.body,
              fontSize: 26,
              letterSpacing: 6,
              fontWeight: 600,
              color: COLORS.muted,
              opacity: mark * 0.9,
            }}
          >
            {kicker}
          </div>
        </div>

        <div>
          <div
            style={{
              fontFamily: FONTS.display,
              fontSize: 168,
              lineHeight: 0.94,
              color: COLORS.ink,
              textTransform: "uppercase",
              transform: `translateY(${(1 - head) * 46}px)`,
              opacity: head,
            }}
          >
            {headline}
          </div>
          <div style={{ height: 6, width: rule, backgroundColor: COLORS.accent, marginTop: 26 }} />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
