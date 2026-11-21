import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONTS } from "../theme";

/**
 * KineticCaptions — word-by-word caption bar for narration.
 *
 * The owner's editing rule (video-studio): max 4 words a line and the longest
 * word in red. This implements that rule as a reusable Remotion component so
 * every video gets the same treatment instead of hand-tuned drawtext.
 */
const splitIntoLines = (words: string[], perLine: number): string[][] => {
  const lines: string[][] = [];
  for (let i = 0; i < words.length; i += perLine) lines.push(words.slice(i, i + perLine));
  return lines;
};

const longestIndex = (words: string[]): number => {
  let best = 0;
  words.forEach((w, i) => {
    if (w.replace(/[^A-Za-z0-9]/g, "").length > words[best].replace(/[^A-Za-z0-9]/g, "").length) best = i;
  });
  return best;
};

export const KineticCaptions: React.FC<{
  text?: string;
  perLine?: number;
}> = ({
  text = "Agility Robotics just secured four hundred sixty five million dollars in new funding",
  perLine = 4,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const words = text.split(/\s+/).filter(Boolean);
  const lines = splitIntoLines(words, perLine);
  // each line owns an equal slice of the composition
  const perLineFrames = Math.floor(durationInFrames / lines.length);
  const activeLine = Math.min(lines.length - 1, Math.floor(frame / perLineFrames));
  const lineFrame = frame - activeLine * perLineFrames;
  const hot = longestIndex(lines[activeLine] || []);

  const enter = interpolate(lineFrame, [0, 6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const exit = interpolate(lineFrame, [perLineFrames - 5, perLineFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = Math.min(enter, exit);

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.stage }}>
      <AbsoluteFill
        style={{
          justifyContent: "flex-end",
          alignItems: "center",
          paddingBottom: 150,
        }}
      >
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: "0 22px",
            maxWidth: 1560,
            padding: "26px 44px",
            backgroundColor: "rgba(0,0,0,0.55)",
            borderLeft: `8px solid ${COLORS.accent}`,
            opacity,
            transform: `translateY(${(1 - enter) * 18}px)`,
          }}
        >
          {(lines[activeLine] || []).map((word, i) => (
            <span
              key={`${activeLine}-${i}`}
              style={{
                fontFamily: FONTS.body,
                fontWeight: 800,
                fontSize: 78,
                lineHeight: 1.15,
                color: i === hot ? COLORS.accent : COLORS.ink,
                textTransform: "uppercase",
                letterSpacing: 1,
              }}
            >
              {word}
            </span>
          ))}
        </div>
        {/* progress hairline: shows the viewer how much of the line is left */}
        <div style={{ width: 1560, height: 4, backgroundColor: COLORS.rule, marginTop: 18 }}>
          <div
            style={{
              width: `${(lineFrame / perLineFrames) * 100}%`,
              height: "100%",
              backgroundColor: COLORS.accent,
            }}
          />
        </div>
      </AbsoluteFill>
      <div
        style={{
          position: "absolute",
          top: 90,
          left: 110,
          fontFamily: FONTS.body,
          fontSize: 26,
          letterSpacing: 8,
          fontWeight: 800,
          color: COLORS.muted,
          opacity: 0.9,
        }}
      >
        NEXTAI VISION
        <span style={{ color: COLORS.accent }}> ·</span> {fps}fps
      </div>
    </AbsoluteFill>
  );
};
