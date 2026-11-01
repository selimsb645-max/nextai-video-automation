"""Unit/integration tests for the v2 quality upgrade (owner Task 9).

Synthetic media is generated with ffmpeg so the tests run with zero network and
zero API quota. Run: pytest -q tests/  (or python3 tests/test_quality.py)
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "factory"))

import pytest  # noqa: E402

import qc_visual          # noqa: E402
import thumb_variants     # noqa: E402


def _ff(args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, check=True)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    clip = str(d / "clip.mp4")
    _ff(["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=5",
         "-f", "lavfi", "-i", "sine=frequency=420:duration=5",
         "-vf", "hue=h=30:s=1.4", "-shortest", clip])
    good = str(d / "good.mp4")
    _a = str(d / "a.mp4")
    _c = str(d / "c.mp4")
    _ff(["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=3",
         "-f", "lavfi", "-i", "sine=frequency=300:duration=3", "-vf", "hue=h=90", "-shortest", _a])
    _ff(["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=3",
         "-f", "lavfi", "-i", "sine=frequency=520:duration=3", "-vf", "hue=h=200:s=1.3", "-shortest", _c])
    lst = str(d / "l.txt")
    with open(lst, "w") as f:
        f.write(f"file '{_a}'\nfile '{_c}'\n")
    _ff(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", good])
    bad = str(d / "bad.mp4")
    black = str(d / "black.mp4")
    _ff(["-f", "lavfi", "-i", "color=c=black:size=1280x720:rate=25:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=300:duration=2", "-shortest", black])
    lst2 = str(d / "l2.txt")
    with open(lst2, "w") as f:
        f.write(f"file '{_a}'\nfile '{black}'\nfile '{_c}'\n")
    _ff(["-f", "concat", "-safe", "0", "-i", lst2, "-c:v", "libx264",
         "-c:a", "aac", "-pix_fmt", "yuv420p", bad])
    return {"dir": str(d), "clip": clip, "good": good, "bad": bad}


# ── Task 1: three thumbnails ────────────────────────────────────────────
def test_three_distinct_thumbnails(media):
    e = {"title": "Claude Opus 4.5 Just Beat GPT-5.1", "subject": "Claude Opus 4.5",
         "headline": "IT BEAT EVERY BENCHMARK"}
    r = thumb_variants.generate_three(e, media["dir"], media["clip"], ["computer chip"])
    assert len(r["variants"]) == 3, "three concepts must be produced"
    paths = [v["path"] for v in r["variants"]]
    assert len(set(paths)) == 3
    # files exist and are real images of the required size
    from PIL import Image
    for p in paths:
        assert os.path.exists(p) and os.path.getsize(p) > 20000
        assert Image.open(p).size == (1280, 720)
    # compositions must differ: compare downscaled pixels, not just text
    import numpy as np
    arrs = [np.asarray(Image.open(p).convert("L").resize((80, 45))).astype(float)
            for p in paths]
    d_ab = abs(arrs[0] - arrs[1]).mean()
    d_bc = abs(arrs[1] - arrs[2]).mean()
    assert d_ab > 12 and d_bc > 12, f"concepts too similar ({d_ab:.1f}, {d_bc:.1f})"
    # scoring + selection
    assert set(r["scores"]) == {"A_cinematic", "B_news", "C_curiosity"}
    assert r["selected"] == max(r["variants"], key=lambda v: v["score"])["path"]
    assert os.path.exists(os.path.join(media["dir"], "thumbnail.jpg"))
    assert "not a CTR" in r["note"]


# ── Task 2: measurable visual QC ────────────────────────────────────────
def test_visual_qc_flags_black_frames(media):
    e = {"beats": [{"t": "A server room hums with new machines.", "kw": "server room lights"}],
         "_clip_meta": [{"tags": ["server", "room"]}]}
    parts, rep = qc_visual.analyse(e, media["bad"], media["dir"])
    checks = [p["check"] for p in rep["problems"]]
    assert "black_frames" in checks, checks
    assert rep["total"] < 25
    assert os.path.exists(os.path.join(media["dir"], "visual_qc_report.json"))


def test_visual_qc_clean_video_scores_high(media):
    e = {"beats": [{"t": "Robot arms assemble a phone.", "kw": "robot arm factory"},
                   {"t": "The chip is smaller than a fingernail.", "kw": "chip macro"}],
         "_clip_meta": [{"tags": ["robot", "factory"]}, {"tags": ["chip", "macro"]}]}
    parts, rep = qc_visual.analyse(e, media["good"], media["dir"])
    assert "black_frames" not in [p["check"] for p in rep["problems"]]
    assert rep["total"] >= 20, rep["score_parts"]
    assert rep["subjective_checks"], "subjective items must be listed separately, never scored"


def test_relevance_and_repetition_detected(media):
    e = {"beats": [{"t": "Nvidia showed a data centre for one model.", "kw": "server room lights"},
                   {"t": "The robot arm moves faster than a hand.", "kw": "server room lights"}],
         "_clip_meta": [{"tags": ["server"]}, {"tags": ["kitchen"]}]}
    _p, rep = qc_visual.analyse(e, media["good"], media["dir"])
    checks = [p["check"] for p in rep["problems"]]
    assert "repetition" in checks
    assert "scene_relevance" in checks
    ts = [p["t"] for p in rep["problems"] if p["check"] == "scene_relevance"]
    assert all(isinstance(t, (int, float)) for t in ts), "problems need timestamps"


# ── Task 3: footage engine ──────────────────────────────────────────────
def test_footage_similarity_and_dedupe(media):
    import footage_engine as fe
    a = fe.clip_signature(os.path.join(media["dir"], "a.mp4"), media["dir"])
    c = fe.clip_signature(os.path.join(media["dir"], "c.mp4"), media["dir"])
    assert not fe.is_similar(a, c), "different shots must not be called duplicates"
    assert fe.is_similar(a, a), "the same shot must be detected as a duplicate"
    same = [({"file": os.path.join(media["dir"], "a.mp4")}, 8),
            ({"file": os.path.join(media["dir"], "a.mp4")}, 8)]
    kept, replaced = fe.dedupe_pairs(same, media["dir"])
    assert len(kept) == 1 and len(replaced) == 1
    diff = [({"file": os.path.join(media["dir"], "a.mp4")}, 8),
            ({"file": os.path.join(media["dir"], "c.mp4")}, 8)]
    kept2, replaced2 = fe.dedupe_pairs(diff, media["dir"])
    assert len(kept2) == 2 and not replaced2


def test_footage_cache_roundtrip(tmp_path):
    import footage_engine as fe
    fe.CACHE_DIR = str(tmp_path)
    fe.QUERY_INDEX = str(tmp_path / "queries.json")
    rec = {"file": "x.mp4", "source": "pixabay", "license": "Pixabay Content License"}
    fe.cache_store("server room lights", rec)
    assert fe.cache_lookup("server room lights") == rec
    assert fe.license_record({"file": "x.mp4", "source": "pixabay"}, "q")["source"] == "pixabay"


# ── Task 5: analytics never invents numbers ─────────────────────────────
def test_analytics_reports_missing_token_honestly():
    sys.path.insert(0, os.path.join(ROOT, "actions"))
    import analytics_feedback as af
    old = sys.argv
    sys.argv = ["analytics_feedback.py"]
    try:
        rc = af.main()
    finally:
        sys.argv = old
    assert rc == 2          # no token -> explicit failure, no file written
    assert not os.path.exists(os.path.join(ROOT, "factory", "analytics_lessons.json"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ── Task 9: selftest must never upload ──────────────────────────────────
def test_selftest_mode_returns_before_any_upload():
    src = open(os.path.join(ROOT, "actions", "runner.py"), encoding="utf-8").read()
    sel = src.index("if args.selftest:", src.index("SELFTEST PASS") - 3000)
    upload = src.index("vid = factory.upload(e, mp4, publish_at, playlist_link=_lnk)")
    # the selftest branch must be reached and return before the upload call
    assert sel < upload, "selftest branch must come before the upload"
    branch = src[sel:upload]
    assert "return" in branch, "the selftest branch must return, never fall through to upload"
    assert "factory.upload(" not in branch, "selftest must not call upload"


def test_qc_threshold_is_enforced_before_upload():
    src = open(os.path.join(ROOT, "actions", "runner.py"), encoding="utf-8").read()
    gate = src.index("_qc_total, _qc_sc, _qc_notes = quality_gate(")
    upload = src.index("vid = factory.upload(e, mp4, publish_at, playlist_link=_lnk)")
    assert gate < upload, "the QC gate must run before upload"
    assert "QC BLOCKED" in src[gate:upload]
    assert "raise SystemExit(3)" in src[gate:upload]


def test_thumbnail_also_written_as_thumb_jpg(tmp_path=None):
    """The upload path (factory.set_thumbnail) reads workdir/thumb.jpg - the
    generator must produce it or the custom thumbnail is silently skipped."""
    import tempfile, sys
    sys.path.insert(0, os.path.join(ROOT, "factory"))
    import thumb_variants as tv
    d = tempfile.mkdtemp()
    clip = os.path.join(d, "c.mp4")
    _ff(["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=3", clip])
    e = {"title": "Gemini 3 Beats GPT-5", "subject": "Gemini 3", "headline": "IT BEAT GPT-5"}
    r = tv.generate_three(e, d, clip, ["server room"], hooks=["IT BEAT GPT-5", "GOOGLE WON", "WHY NOW"])
    assert r.get("final") and os.path.exists(os.path.join(d, "thumb.jpg"))
    assert os.path.getsize(os.path.join(d, "thumb.jpg")) < 2_000_000


# ── Kokoro voice chain (owner 2026-11-01) ───────────────────────────────
def test_narration_filter_chain_is_broadcast_grade():
    sys.path.insert(0, os.path.join(ROOT, "factory"))
    import factory as F
    ch = F.narration_filters()
    for must in ("highpass", "equalizer", "acompressor", "loudnorm=I=-16",
                 "aresample=48000"):
        assert must in ch, f"missing {must} in the voice chain"
    # loudnorm must leave headroom for the music bed, not hit the final -13
    assert "I=-13" not in ch


def test_post_processing_hits_target_loudness_and_rate(tmp_path):
    import subprocess, re
    sys.path.insert(0, os.path.join(ROOT, "factory"))
    import factory as F
    src = tmp_path / "in.wav"
    _ff(["-f", "lavfi", "-i", "sine=f=220:d=4", "-f", "lavfi", "-i",
         "anoisesrc=color=brown:amplitude=0.02:d=4", "-filter_complex",
         "[0][1]amix=inputs=2:duration=shortest,volume=0.3", str(src)])
    out = tmp_path / "out.mp3"
    assert F._post_narration(str(src), str(out)) is True
    r = subprocess.run(["ffmpeg", "-i", str(out), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    lufs = re.findall(r"I:\s*(-?\d+\.\d+)\s*LUFS", r.stderr)
    assert lufs and -18.5 <= float(lufs[-1]) <= -14.0, f"loudness off: {lufs}"
    assert "48000 Hz" in r.stderr or "48000" in r.stderr
