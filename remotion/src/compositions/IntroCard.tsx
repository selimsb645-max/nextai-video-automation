import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Stage } from "../components/Stage";
import { breathe, COLORS, EASE, FONTS, SPRING } from "../theme";

/**
 * IntroCard — broadcast-style title, 2.5s.
 *
 * Skill compliance: springs on every entrance, three properties move together
 * (opacity + translate + scale), elements stagger 6 frames apart, the rule exits faster
 * than it entered, and the wordmark breathes while it holds.
 */
export const IntroCard: React.FC<{
  brand?: string;
  headline?: string;
  kicker?: string;
}> = ({ brand = "NEXTAI VISION", headline = "THE KICK FAILED", kicker = "AI NEWS" }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();

  const bar = spring({ frame, fps, config: SPRING.snappy });
  const mark = spring({ frame: frame - 6, fps, config: SPRING.smooth });
  const tag = spring({ frame: frame - 12, fps, config: SPRING.smooth });
  const head = spring({ frame: frame - 20, fps, config: SPRING.snappy });

  const rule = interpolate(frame, [26, 46], [0, width * 0.62], {
    easing: EASE.out,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <Stage light="left">
      <AbsoluteFill style={{ padding: "120px 140px", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
          <div
            style={{
              width: 84 * bar,
              height: 10,
              backgroundColor: COLORS.accent,
              borderRadius: 2,
              transform: `scaleX(${0.4 + bar * 0.6})`,
              transformOrigin: "left center",
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
              transform: `translateX(${(1 - mark) * -18}px) scale(${0.97 + mark * 0.03}) translateY(${breathe(frame, fps) * 0.6}px)`,
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
              opacity: tag * 0.92,
              transform: `translateX(${(1 - tag) * -12}px)`,
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
              opacity: head,
              transform: `translateY(${(1 - head) * 46}px) scale(${0.985 + head * 0.015})`,
              letterSpacing: `${(1 - head) * 6}px`,
            }}
          >
            {headline}
          </div>
          <div style={{ height: 6, width: rule, backgroundColor: COLORS.accent, marginTop: 26 }} />
        </div>
      </AbsoluteFill>
    </Stage>
  );
};
