"""Tests for the cinematic editor (factory/cine/*).

These run in GitHub Actions on a CPU runner with no GPU and no network keys, so
every test either uses ffmpeg-generated media or the pure-python parts.
"""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
FACTORY = os.path.join(os.path.dirname(HERE), "factory")
if FACTORY not in sys.path:
    sys.path.insert(0, FACTORY)

from cine import storyboard as SB          # noqa: E402
from cine import captions as CAP          # noqa: E402
from cine import motion as MO             # noqa: E402
from cine import audio as AU              # noqa: E402
from cine import qc as QC                 # noqa: E402
from cine import visual_match as VM       # noqa: E402
from cine import editor as ED             # noqa: E402


def ff(args):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y"] + args,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]
    return r


@pytest.fixture
def narration(tmp_path):
    """A 12 s 'narration' with two real pauses (speech stand-in + silence)."""
    p = str(tmp_path / "nar.mp3")
    ff(["-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100:duration=5",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=0.8", "-f", "lavfi",
        "-i", "sine=frequency=240:sample_rate=44100:duration=4",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=0.7",
        "-f", "lavfi", "-i", "sine=frequency=260:sample_rate=44100:duration=3",
        "-filter_complex", "[0:a][1:a][2:a][3:a][4:a]concat=n=5:v=0:a=1[out]",
        "-map", "[out]", p])
    return p


def test_storyboard_has_every_required_field():
    sb = SB.build(ED.SAMPLE, duration=47.0)
    assert sb["scene_count"] >= 4
    need = ("scene_id", "narration_text", "start_time", "end_time",
            "visual_description", "search_query", "visual_type",
            "transition", "motion_style")
    for sc in sb["scenes"]:
        for k in need:
            assert k in sc and sc[k] not in (None, ""), k
    assert not SB.validate(sb)
    durs = [s["duration"] for s in sb["scenes"]]
    assert len(set(round(d, 1) for d in durs)) > 1, "durations must be dynamic"
    assert abs(sum(durs) - 47.0) < 0.5


def test_storyboard_snaps_to_real_pauses(narration):
    dur = SB.audio_duration(narration)
    sb = SB.build(ED.SAMPLE, narration_path=narration, duration=dur)
    assert "silence_snapped" in sb["timing_source"]
    assert not SB.validate(sb)


def test_storyboard_detects_broken_timeline():
    sb = SB.build(ED.SAMPLE, duration=40.0)
    sb["scenes"][1]["start_time"] += 3.0          # inject a gap
    errs = SB.validate(sb)
    assert any("gap" in e or "overlap" in e for e in errs)


def test_motion_styles_are_distinct():
    exprs = {s: MO.motion_expr(s, 6.0, 25) for s in
             ("zoom_in", "zoom_out", "pan_left", "pan_right", "push_in_slow")}
    zs = {tuple(sorted(v.items())) for v in exprs.values()}
    assert len(zs) == len(exprs), "every motion style must differ"
    assert "zoompan" in MO.scene_filter({"scene_id": 1, "motion_style": "zoom_in"},
                                        6.0, 1920, 1080, 25)


def test_captions_estimated_and_word_timed(tmp_path):
    sb = SB.build(ED.SAMPLE, duration=30.0)
    est = CAP.build(sb, str(tmp_path / "est.ass"), W=1280, H=720)
    assert est["cues"] > 3 and est["timing_source"].startswith("estimated")
    v = CAP.validate(str(tmp_path / "est.ass"), 30.0)
    assert v["ok"], v["errors"]

    wt = {sb["scenes"][0]["scene_id"]: [
        ("word one", sb["scenes"][0]["start_time"],
         sb["scenes"][0]["start_time"] + 1.0)]}
    w = CAP.build(sb, str(tmp_path / "wt.ass"), W=1280, H=720, word_timings=wt)
    # only one scene had measured timings, so the file must say so, honestly
    assert w["timing_source"] == "mixed_word_and_estimated"
    one = {"narration_duration": 4.0, "scenes": [{**sb["scenes"][0],
           "start_time": 0.0, "end_time": 4.0}]}
    w2 = CAP.build(one, str(tmp_path / "wt2.ass"), W=1280, H=720,
                   word_timings={sb["scenes"][0]["scene_id"]: [
                       ("all measured", 0.0, 4.0)]})
    assert w2["timing_source"] == "word"


def test_caption_text_is_escaped_and_highlighted(tmp_path):
    sb = {"narration_duration": 6.0, "scenes": [{
        "scene_id": 1, "narration_text": "Genie 4 costs $40 {weird} now",
        "start_time": 0.0, "end_time": 6.0, "keywords": ["Genie", "$40"]}]}
    CAP.build(sb, str(tmp_path / "x.ass"), W=1280, H=720)
    body = open(str(tmp_path / "x.ass"), encoding="utf-8").read()
    assert "{weird}" not in body and "(weird)" in body      # ASS override escaped
    assert "\\c&H" in body                                   # accent applied


def test_audio_bed_ducking_and_loudness(tmp_path, narration):
    bed = AU.make_bed(str(tmp_path / "bed.wav"), 12.0)
    nar = AU.prepare_narration(narration, str(tmp_path / "nar.wav"))
    mixp = AU.mix(nar, bed, str(tmp_path / "mix.m4a"))
    m = AU.measure(mixp)
    assert m["duration"] > 11
    assert m["lufs"] is not None and -20 <= m["lufs"] <= -8
    assert (m["true_peak_db"] or -99) < 0


def test_visual_card_and_queries(tmp_path):
    sc = {"scene_id": 3, "keywords": ["robot", "arm", "laboratory"],
          "search_query": "robot arm", "visual_type": "real_world_footage"}
    qs = VM._queries_for(sc)
    assert len(qs) == len(set(qs)) and 1 <= len(qs) <= 3
    p = VM.make_card(sc, str(tmp_path / "card.png"), w=640, h=360)
    assert os.path.getsize(p) > 10_000


def test_editor_is_gated_by_the_flag(monkeypatch):
    monkeypatch.setenv("ENABLE_CINEMATIC_EDITOR", "false")
    assert not ED.enabled()
    with pytest.raises(SystemExit):
        ED.build(ED.SAMPLE, "unused_dir", narration_path="/nonexistent.mp3")
    monkeypatch.setenv("ENABLE_CINEMATIC_EDITOR", "true")
    assert ED.enabled()


def test_qc_passes_good_clip_and_catches_black(tmp_path):
    good = str(tmp_path / "good.mp4")
    ff(["-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=6",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=6",
        "-vf", "format=yuv420p", "-c:v", "libx264", "-c:a", "aac",
        "-shortest", good])
    rep = QC.check(good, expected_w=320, expected_h=180, expected_fps=25)
    assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
    assert "not_provable" in rep

    black = str(tmp_path / "black.mp4")
    ff(["-f", "lavfi", "-i", "color=c=black:s=320x180:rate=25:duration=6",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=6",
        "-vf", "format=yuv420p", "-c:v", "libx264", "-c:a", "aac",
        "-shortest", black])
    rep2 = QC.check(black, expected_w=320, expected_h=180)
    assert not rep2["ok"]
    assert any(c["check"] == "black_frames" and not c["ok"] for c in rep2["checks"])


def test_end_to_end_micro_film(tmp_path, narration):
    """A real render: 3 scenes, real ffmpeg, ALWAYS a QC report at the end."""
    entry = {
        "title": "Cinematic engine micro test",
        "kind": "long",
        "narration": ("The machine learned in one afternoon what took a decade. "
                      "Engineers say the cost fell by ninety percent. "
                      "That changes which ideas are worth building."),
        "beats": [{"t": "The machine learned in one afternoon what took a decade."},
                  {"t": "Engineers say the cost fell by ninety percent."},
                  {"t": "That changes which ideas are worth building."}],
    }
    os.environ["RENDER_QUALITY"] = "draft"
    rep = ED.build(entry, str(tmp_path / "out"), narration_path=narration,
                   W=640, H=360, fps=25, force=True)
    assert os.path.exists(rep["output"])
    assert rep["qc"]["checks"], "QC must always produce a report"
    assert rep["qc"]["duration_s"] > 8
    assert rep["stages"]["captions"]["cues"] > 0
    assert os.path.exists(str(tmp_path / "out" / "storyboard.json"))
    assert os.path.exists(str(tmp_path / "out" / "qc_report.json"))
    sb = json.load(open(str(tmp_path / "out" / "storyboard.json")))
    # short trailing beats may merge into the previous scene; the timeline must
    # still cover the whole narration with no gap
    assert 2 <= sb["scene_count"] <= 3
    assert not SB.validate(sb)
