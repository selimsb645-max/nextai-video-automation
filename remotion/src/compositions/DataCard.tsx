import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Stage } from "../components/Stage";
import { breathe, COLORS, EASE, FONTS, SPRING } from "../theme";

/**
 * DataCard — one number, one claim, one source.
 *
 * Skill compliance: the counter uses an ease-out curve (never linear), the number, label
 * and source stagger 8 frames apart, the accent bar springs in, and the whole block holds
 * with a breathing drift so it does not look frozen.
 */
export const DataCard: React.FC<{
  value?: number;
  suffix?: string;
  label?: string;
  source?: string;
}> = ({
  value = 465,
  suffix = "M",
  label = "RAISED BY AGILITY ROBOTICS",
  source = "Source: company filing",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const pop = spring({ frame, fps, config: SPRING.snappy });
  const counted = Math.round(
    interpolate(frame, [6, 48], [0, value], {
      easing: EASE.out,
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
  );
  const labelIn = spring({ frame: frame - 14, fps, config: SPRING.smooth });
  const sourceIn = spring({ frame: frame - 22, fps, config: SPRING.smooth });
  const bar = spring({ frame: frame - 4, fps, config: SPRING.bouncy });

  return (
    <Stage light="right">
      <AbsoluteFill style={{ padding: "150px 150px", justifyContent: "center" }}>
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: 18,
            borderLeft: `12px solid ${COLORS.accent}`,
            paddingLeft: 54,
            transform: `translateY(${breathe(frame, fps, 2.2)}px)`,
          }}
        >
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
              opacity: pop,
              transform: `translateY(${(1 - pop) * 16}px)`,
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
            height: 2,
            width: `${bar * 52}%`,
            backgroundColor: COLORS.rule,
            marginTop: 26,
          }}
        />

        <div
          style={{
            fontFamily: FONTS.body,
            fontSize: 26,
            color: COLORS.muted,
            marginTop: 16,
            opacity: sourceIn,
            transform: `translateY(${(1 - sourceIn) * 12}px)`,
            width: 900,
          }}
        >
          {source}
        </div>
      </AbsoluteFill>
    </Stage>
  );
};
