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

import numpy as np  # noqa: E402
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
    assert len(r["variants"]) >= 3, "at least three concepts must be produced"
    names = [v["concept"] for v in r["variants"] if v.get("path")]
    assert len(set(names)) == len(names), "concepts must be distinct"
    # owner 2026-11-01: the @airevolutionx alert concept is the house style
    assert "D_alert" in names, "house-style alert concept missing"
    assert r["selected"], "a winner must be selected"
    assert os.path.exists(r["thumb_jpg"]), "thumb.jpg (upload guard name) must exist"
    paths = [v["path"] for v in r["variants"] if v.get("path")]
    assert len(set(paths)) == len(paths) >= 3
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
    assert set(r["scores"]) == {"A_cinematic", "B_news", "C_curiosity", "D_alert"}
    # owner 2026-11-01: the alert concept is the mandated house style, so the
    # winner is the highest scorer normally but D_alert wins when it clears 45
    scores = {v["concept"]: v["score"] for v in r["variants"] if v.get("path")}
    if scores.get("D_alert", 0) >= 45.0:
        assert r["selected"].endswith("thumb_D_alert.jpg")
    else:
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


# ── Task 1b: house-style closeness (measured from @airevolutionx) ───────
def test_poster_matches_reference_profile(media):
    """Owner 2026-11-01: 'no similarity at all' - so closeness is now measured.

    Targets came from 8 real @airevolutionx thumbnails: luma ~55, saturation
    ~0.46, luma std ~70, bright text pixels ~5%, near-black ~67%.
    """
    import thumb_alert as TA
    from PIL import Image
    frame = thumb_variants._grab_frames(media["clip"], media["dir"])
    assert frame, "need at least one frame for the style test"
    base = Image.open(frame[0]).convert("RGB")
    im = TA.concept_poster(base, "OPENAI JUST CROSSED THE LINE", "AI NEWS", None)
    prof = TA.style_profile(im)
    assert prof["luma"] < 90, f"too bright for the house style: {prof}"
    assert prof["sat"] > 0.28, f"saturation below the reference range: {prof}"
    assert prof["white"] >= 2.0, f"hook text too small: {prof}"
    assert TA.style_distance(prof) <= 2.8, f"off-reference look: {prof}"
    assert im.size == (1280, 720)


# ── Task 1c: announcement-slide studio (owner annotated reference) ───────
def test_studio_three_compositions(media):
    """Owner 2026-11-01: the four annotated reference thumbs are the target -
    brand wordmark + INTRODUCING + big product name + descriptor on a stage."""
    import thumb_studio as TS
    from PIL import Image
    assert TS.parse_story("Google Just Introduced Gemini 4 With "
                          "Synthetic Reality", "Gemini")["brand"] == "Google"
    story = TS.parse_story("OpenAI Just Launched GPT-6 With Real Memory", "OpenAI")
    assert story["product"] and story["descriptor"]
    assert story["product"] != story["descriptor"]
    frames = thumb_variants._grab_frames(media["clip"], media["dir"])
    base = TS.stage(Image.open(frames[0]).convert("RGB")) if frames else TS.stage()
    outs = TS.render_all(base, story, None, media["dir"])
    assert len(outs) >= 3, "announcement compositions expected"
    names = [n for n, _, _ in outs]
    assert len(set(names)) == len(names) >= 3
    assert {"bell", "hero", "stack"} <= set(names)
    arrs = []
    for n, p, im in outs:
        assert os.path.exists(p) and im.size == (1280, 720)
        prof = TS._profile(im)
        assert prof["luma"] < 85, f"{n} too bright for a stage poster: {prof}"
        assert prof["white"] > 1.0, f"{n} has no legible type: {prof}"
        arrs.append(np.asarray(Image.open(p).convert("RGB").resize((160, 90))).astype(int))
    for i in range(len(arrs) - 1):
        assert abs(arrs[i] - arrs[i + 1]).mean() > 12, "compositions look alike"


def test_studio_build_saves_both_names(media):
    import thumb_studio as TS
    e = {"title": "NVIDIA Just Made Every Other Chip Obsolete", "subject": "NVIDIA"}
    p = TS.build(e, media["dir"], media["clip"] if isinstance(media["clip"], dict) else None)
    assert p and os.path.exists(p)
    for name in ("thumb.jpg", "thumbnail.jpg"):
        assert os.path.exists(os.path.join(media["dir"], name))
        assert os.path.getsize(os.path.join(media["dir"], name)) < 1_900_000
    assert os.path.exists(os.path.join(media["dir"], "thumb_choice.json"))


# ── thumbnail PROMPTS (owner 2026-11-01: Solas writes prompts, not images) ──
def test_thumb_prompt_shape():
    import thumb_prompt as TP
    p = TP.build("Google Just Introduced Gemini 4 With Synthetic Reality")
    for key in ("image_prompt", "text_overlay", "text_spec", "all_in_one", "negative"):
        assert p[key], f"missing {key}"
    assert "1280x720" in p["image_prompt"]
    assert "LEFT THIRD" in p["image_prompt"]          # type area reserved
    assert "no text" in p["image_prompt"].lower()      # image stays text-free
    assert len(p["text_overlay"].split()) <= 4
    assert p["text_overlay"].isupper()
    # subject inference picks a filmable object, never a brand name
    assert TP.build("NVIDIA Hits $4 Trillion").get("subject_key") in TP.SUBJECTS


def test_thumb_prompt_for_each_subject():
    import thumb_prompt as TP
    seen = {}
    for title in ("A humanoid robot learns to cook", "New AI chip breaks the rules",
                  "Driverless car crosses the city", "Your job in two years",
                  "Satellite spots something in orbit", "Data centre burns water"):
        p = TP.build(title)
        assert p["subject_key"] in TP.SUBJECTS
        seen[p["subject_key"]] = seen.get(p["subject_key"], 0) + 1
        assert p["image_prompt"].startswith("YouTube thumbnail")


def test_thumb_prompt_latest_and_message(tmp_path, monkeypatch):
    import thumb_prompt as TP
    log = [{"id": "a", "videoId": "V1", "title": "OpenAI Just Warned About Something",
            "kind": "long", "uploaded_at": "2026-11-01", "url": "https://x/V1"}]
    monkeypatch.setattr(TP, "LOG", str(tmp_path / "log.json"))
    (tmp_path / "log.json").write_text(json.dumps(log))
    e = TP.latest("2026-11-01", "long")
    assert e and e["videoId"] == "V1"
    assert TP.latest("2026-10-31") is None
    msg = TP.format_message(e, TP.build(e["title"]))
    assert "V1" in msg and "প্রম্পট" in msg


# ── A-to-Z prompt + reference mirror (owner 2026-11-01) ─────────────────────
def test_full_prompt_is_complete():
    import thumb_prompt as TP
    f = TP.build_full("Google's New Genie 4 Is the Beginning of Synthetic Reality")
    p = f["full_prompt"]
    for must in ("16:9", "1280x720", "SCENE", "SUBJECT", "TYPE", "Layout",
                 "NEVER include", f['headline'], f['kicker'], f['accent_word']):
        assert must in p, must
    assert "watermark" in p.lower()
    # a prompt that asks for type must not forbid text
    assert "no text" not in p.lower()
    assert "no text" in f["image_prompt"].lower()      # the fallback does
    assert 1 <= len(f["headline"].split()) <= 3
    assert len(f["steps"]) >= 3


def test_hooks_pick_the_named_thing():
    import thumb_prompt as TP
    cases = {"Google's New Genie 4 Is the Beginning of Synthetic Reality": "GENIE 4",
             "Anthropic's Opus 6 Ignites a Terrifying AI Theory": "OPUS 6",
             "Mythos 5 and Google Just Broke Quantum Computing": "MYTHOS 5",
             "This 89K Robot Is Learning to Babysit in a NYC Park": "89K ROBOT"}
    for title, want in cases.items():
        got = TP.short_text(title)
        assert want.split()[0] in got, f"{got} should carry {want}"
    assert "$4" in TP.short_text("NVIDIA Hits $4 Trillion and Nobody Is Ready").upper()


def test_reference_mirror_creates_pending_topics(tmp_path, monkeypatch):
    import reference_mirror as RM
    feed = [{"videoId": "REF1", "title": "It's over... China's New AI Just Caught Up With America's Best",
             "published": "2026-11-01", "url": "https://www.youtube.com/watch?v=REF1"}]
    monkeypatch.setattr(RM, "LIBRARY", str(tmp_path / "library.json"))
    monkeypatch.setattr(RM, "SEEN", str(tmp_path / "seen.json"))
    monkeypatch.setattr(RM, "fetch_feed", lambda limit=15: feed)
    import sys
    monkeypatch.setattr(sys, "argv", ["mirror"])
    assert RM.main() == 0
    lib = json.loads((tmp_path / "library.json").read_text())
    e = lib["entries"][0]
    assert e["status"] == "pending" and e["origin"] == "reference_mirror"
    assert e["reference_video"] == "REF1"
    assert "REF1" in e["verified_sources"][0]
    assert e["demand_evidence"] and "AI Revolution" in e["demand_evidence"]
    assert "it's over" not in e["title"].lower()          # their hype is not our topic
    # a second run must not duplicate it
    assert RM.main() == 0
    assert len(json.loads((tmp_path / "library.json").read_text())["entries"]) == 1


def test_clean_topic_strips_hype_and_dangling_words():
    import reference_mirror as RM
    assert RM.clean_topic("It's over... China's New AI Just Caught Up") == "China's New AI Just Caught Up"
    assert not RM.clean_topic("OpenAI's New GPT-6.1 Terra Is").endswith(" Is")
    assert RM.clean_topic("DeepSeek Fires Again!") == "DeepSeek Fires"
