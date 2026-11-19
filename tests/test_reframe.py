"""factory/reframe.py — ffmpeg ছাড়া কিছুই দরকার নেই, তাই টেস্ট হালকা।"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from factory import reframe  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg নেই")


@pytest.fixture(scope="module")
def landscape(tmp_path_factory):
    p = tmp_path_factory.mktemp("vid") / "in.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25:duration=3",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(p), "-loglevel", "error"],
        check=True)
    return p


def test_crop_makes_1080x1920_and_keeps_audio(landscape, tmp_path):
    out = tmp_path / "v.mp4"
    r = reframe.to_vertical(landscape, out, mode="crop")
    assert r["ok"], r["error"]
    info = reframe.probe(out)
    assert (info["width"], info["height"]) == (1080, 1920)
    assert info["has_audio"]


def test_pad_keeps_the_whole_frame(landscape, tmp_path):
    out = tmp_path / "p.mp4"
    r = reframe.to_vertical(landscape, out, mode="pad")
    assert r["ok"], r["error"]
    assert reframe.probe(out)["height"] == 1920


def test_missing_input_is_reported_not_raised(tmp_path):
    r = reframe.to_vertical(tmp_path / "nope.mp4", tmp_path / "o.mp4")
    assert r["ok"] is False and "missing input" in r["error"]


def test_is_vertical(landscape, tmp_path):
    assert reframe.is_vertical(str(landscape)) is False
    out = tmp_path / "v.mp4"
    reframe.to_vertical(landscape, out, mode="crop")
    assert reframe.is_vertical(str(out)) is True
