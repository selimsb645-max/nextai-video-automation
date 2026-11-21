import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONTS } from "../theme";

/**
 * DataCard — one number, one claim, one source.
 *
 * The factory's current renders burn a caption and move on. This gives a beat
 * the weight a documentary gives a stat: the number counts up, the unit sits
 * beside it, and the source line stays on screen so the claim is checkable.
 */
export const DataCard: React.FC<{
  value?: number;
  suffix?: string;
  label?: string;
  source?: string;
}> = ({ value = 465, suffix = "M", label = "RAISED BY AGILITY ROBOTICS", source = "Source: company filing" }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const pop = spring({ frame, fps, config: { damping: 16, mass: 0.8 } });
  // count up over 1.4s, then hold: the number lands before the label finishes
  const counted = Math.round(interpolate(frame, [6, 48], [0, value], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  }));
  const labelIn = spring({ frame: frame - 24, fps, config: { damping: 200 } });
  const sourceIn = interpolate(frame, [44, 66], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.stage }}>
      <AbsoluteFill
        style={{
          background: `linear-gradient(115deg, ${COLORS.stageLift} 0%, ${COLORS.stage} 58%)`,
        }}
      />
      <AbsoluteFill
        style={{
          padding: "150px 150px",
          justifyContent: "center",
          borderLeft: `12px solid ${COLORS.accent}`,
          margin: "90px 0 90px 120px",
          width: "fit-content",
          paddingRight: 90,
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-end", gap: 18 }}>
          <div
            style={{
              fontFamily: FONTS.display,
              fontSize: 300,
              lineHeight: 0.86,
              color: COLORS.ink,
              transform: `scale(${0.94 + pop * 0.06})`,
              transformOrigin: "left bottom",
            }}
          >
            {counted}
          </div>
          <div
            style={{
              fontFamily: FONTS.display,
              fontSize: 132,
              lineHeight: 1,
              color: COLORS.accent,
              paddingBottom: 34,
            }}
          >
            {suffix}
          </div>
        </div>

        <div
          style={{
            fontFamily: FONTS.body,
            fontWeight: 800,
            fontSize: 46,
            letterSpacing: 4,
            color: COLORS.ink,
            marginTop: 28,
            maxWidth: 1100,
            opacity: labelIn,
            transform: `translateY(${(1 - labelIn) * 22}px)`,
          }}
        >
          {label}
        </div>

        <div
          style={{
            fontFamily: FONTS.body,
            fontSize: 26,
            color: COLORS.muted,
            marginTop: 22,
            opacity: sourceIn,
            borderTop: `1px solid ${COLORS.rule}`,
            paddingTop: 16,
            width: 900,
          }}
        >
          {source}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
