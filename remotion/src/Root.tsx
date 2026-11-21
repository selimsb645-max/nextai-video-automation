import React from "react";
import { Composition, Series } from "remotion";
import { IntroCard } from "./compositions/IntroCard";
import { DataCard } from "./compositions/DataCard";
import { KineticCaptions } from "./compositions/KineticCaptions";
import { OutroCard } from "./compositions/OutroCard";
import { VIDEO } from "./theme";

/**
 * ProofReel — the smallest thing that proves the whole graphics layer works:
 * intro, a stat beat, a caption beat, outro. Once this renders on CI we attach
 * the same components to real video beats in actions/runner.py.
 */
const ProofReel: React.FC = () => (
  <Series>
    <Series.Sequence durationInFrames={75}>
      <IntroCard />
    </Series.Sequence>
    <Series.Sequence durationInFrames={110}>
      <DataCard />
    </Series.Sequence>
    <Series.Sequence durationInFrames={150}>
      <KineticCaptions />
    </Series.Sequence>
    <Series.Sequence durationInFrames={60}>
      <OutroCard />
    </Series.Sequence>
  </Series>
);

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="ProofReel"
      component={ProofReel}
      durationInFrames={75 + 110 + 150 + 60}
      fps={VIDEO.fps}
      width={VIDEO.width}
      height={VIDEO.height}
    />
    <Composition id="IntroCard" component={IntroCard} durationInFrames={75} fps={VIDEO.fps} width={VIDEO.width} height={VIDEO.height} />
    <Composition id="DataCard" component={DataCard} durationInFrames={110} fps={VIDEO.fps} width={VIDEO.width} height={VIDEO.height} />
    <Composition id="KineticCaptions" component={KineticCaptions} durationInFrames={150} fps={VIDEO.fps} width={VIDEO.width} height={VIDEO.height} />
    <Composition id="OutroCard" component={OutroCard} durationInFrames={60} fps={VIDEO.fps} width={VIDEO.width} height={VIDEO.height} />
  </>
);
