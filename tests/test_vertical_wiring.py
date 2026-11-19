"""The two wiring points: shorts clip fitting and the long-video vertical copy.

Both are switchable, so the tests cover on, off and the failure path. Nothing here
needs network: clips are generated with ffmpeg into a tmp dir.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "factory"))


def _clip(path, w=1280, h=720, dur=2):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=25:duration={dur}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path, "-loglevel", "error"],
        check=True)


def _probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


@pytest.fixture
def clip(tmp_path):
    p = str(tmp_path / "landscape.mp4")
    _clip(p)
    return p


def test_fit_clips_pads_landscape_to_vertical(clip, tmp_path, monkeypatch):
    monkeypatch.setenv("SHORTS_FIT", "pad")
    import trick_shorts as TS

    pairs = [({"t": "one two three"}, {"file": clip, "dur": 2.0})]
    out = TS.fit_clips(pairs, str(tmp_path))
    assert len(out) == 1
    fitted = out[0][1]["file"]
    assert os.path.isabs(fitted) and os.path.exists(fitted)
    assert _probe(fitted) == (1080, 1920)
    # the beat itself must survive untouched
    assert out[0][0]["t"] == "one two three"


def test_fit_clips_off_returns_originals(clip, tmp_path, monkeypatch):
    monkeypatch.setenv("SHORTS_FIT", "off")
    import trick_shorts as TS

    pairs = [({"t": "x"}, {"file": clip, "dur": 2.0})]
    out = TS.fit_clips(pairs, str(tmp_path))
    assert out[0][1]["file"] == clip


def test_fit_clips_survives_a_broken_source(tmp_path, monkeypatch):
    monkeypatch.setenv("SHORTS_FIT", "pad")
    import trick_shorts as TS

    broken = str(tmp_path / "broken.mp4")
    open(broken, "wb").write(b"not a video")
    pairs = [({"t": "x"}, {"file": broken, "dur": 2.0})]
    out = TS.fit_clips(pairs, str(tmp_path))
    assert out[0][1]["file"] == broken   # falls back, never raises


def test_vertical_copy_is_off_by_default(clip, tmp_path, monkeypatch):
    monkeypatch.delenv("ENABLE_VERTICAL_COPY", raising=False)
    sys.path.insert(0, ROOT)
    from actions import runner
    assert runner.vertical_copy(clip, str(tmp_path)) is None


def test_vertical_copy_makes_1080x1920(clip, tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_VERTICAL_COPY", "true")
    sys.path.insert(0, ROOT)
    from actions import runner
    dst = runner.vertical_copy(clip, str(tmp_path))
    assert dst and os.path.exists(dst)
    assert _probe(dst) == (1080, 1920)
