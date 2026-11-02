"""Phase 9 + 10 - orchestrator, safe integration, CLI.

ENABLE_CINEMATIC_EDITOR gates production use:
  * "false" (default): factory.render keeps producing the published film. This
    engine is only reachable through the test workflow / CLI.
  * "true": the pipeline may use it, but every stage still falls back to the old
    renderer on failure, and the QC gate must pass before anything is published.

Nothing here uploads, schedules, changes credentials or touches YouTube.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import traceback

try:                                  # package import (python -m cine.editor)
    from . import storyboard as SB
    from . import visual_match as VM
    from . import motion as MO
    from . import captions as CAP
    from . import audio as AU
    from . import qc as QC
except ImportError:                   # direct script use (factory/cine on path)
    import storyboard as SB
    import visual_match as VM
    import motion as MO
    import captions as CAP
    import audio as AU
    import qc as QC

FACTORY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLAG = "ENABLE_CINEMATIC_EDITOR"


# ── footage matcher selection (Next AI Vision 4) ───────────────────────────
def _matcher():
    """ENABLE_MULTI_SOURCE_FOOTAGE=true swaps in the multi-provider matcher.

    Default (flag unset/false) returns visual_match.match_scene unchanged, so the
    production path is byte-for-byte what it was before the upgrade. The
    multi-provider matcher is itself fail-open per scene: any provider error just
    removes that provider's candidates and the scene falls back to the old
    Pixabay -> Commons -> Archive chain, then to a motion card.
    """
    if os.environ.get("ENABLE_MULTI_SOURCE_FOOTAGE", "false").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from . import multi_source as MS
            return MS.match_scene_multi
        except Exception as ex:                       # pragma: no cover
            print(f"multi-source matcher unavailable, using visual_match: {str(ex)[:120]}")
    return VM.match_scene


SAMPLE = {
    "title": "Google's New Genie 4 Is the Beginning of Synthetic Reality",
    "kind": "long",
    "narration": (
        "Google just opened a door that nobody is ready to close. Genie 4 builds "
        "entire interactive worlds from a single sentence, in real time, on a "
        "phone. The demo showed a robot arm learning a task inside a world that "
        "did not exist ten seconds earlier. Researchers say the model trained on "
        "over two million hours of simulated physics. That is what makes this "
        "different from every world model before it. Gaming studios lost four "
        "percent of their value in a single afternoon. But the people who built "
        "it say the real target is robotics, not games. If a machine can rehearse "
        "reality before it touches reality, the cost of physical mistakes drops "
        "to almost nothing. That is the beginning of synthetic reality."
    ),
    "beats": [
        {"t": "Google just opened a door that nobody is ready to close.", "tags": ["google", "technology"]},
        {"t": "Genie 4 builds entire interactive worlds from a single sentence, in real time, on a phone.", "tags": ["world", "animation"]},
        {"t": "The demo showed a robot arm learning a task inside a world that did not exist ten seconds earlier.", "tags": ["robot arm", "laboratory"]},
        {"t": "Researchers say the model trained on over two million hours of simulated physics.", "tags": ["computer", "data"]},
        {"t": "That is what makes this different from every world model before it.", "tags": ["abstract", "digital"]},
        {"t": "Gaming studios lost four percent of their value in a single afternoon.", "tags": ["stock market", "trading"]},
        {"t": "But the people who built it say the real target is robotics, not games.", "tags": ["robot", "engineer"]},
        {"t": "If a machine can rehearse reality before it touches reality, the cost of physical mistakes drops to almost nothing.", "tags": ["factory", "automation"]},
        {"t": "That is the beginning of synthetic reality.", "tags": ["network", "abstract"]},
    ],
}


def enabled():
    return os.environ.get(FLAG, "false").strip().lower() in ("1", "true", "yes", "on")


def _log_factory(log):
    def f(msg):
        print(msg, flush=True)
        if log:
            log(msg)
    return f


def _gen_narration(entry, workdir, log):
    """Reuse the production Kokoro path; never invent audio."""
    try:
        import factory as F
        print("narration: using production TTS (factory.gen_voice)", flush=True)
        return F.gen_voice(entry, workdir)
    except Exception as e:
        log(f"narration: production TTS unavailable ({str(e)[:90]})")
        return None


def build_baseline(sb, assets, workdir, mixed_audio, W, H, fps, log=print):
    """Render the SAME storyboard and SAME assets the old way: static crop, one
    flat grade, hard cuts, no captions. This is the A/B baseline the new engine
    has to beat, not a strawman of somebody else's renderer."""
    bdir = os.path.join(workdir, "baseline_scenes")
    os.makedirs(bdir, exist_ok=True)
    clips = []
    for sc, asset in zip(sb["scenes"], assets):
        flat = dict(sc, motion_style="static", _grade="neutral_doc")
        out = os.path.join(bdir, f"b{sc['scene_id']:02d}.mp4")
        MO.render_scene(flat, asset, out, max(sc["duration"], 1.2),
                        W=W, H=H, fps=fps, log=lambda *_: None)
        clips.append(out)
    video = MO.concat_hard(clips, os.path.join(workdir, "baseline_video.mp4"), log=log)
    final = os.path.join(workdir, "baseline.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", mixed_audio,
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-shortest",
                        "-movflags", "+faststart", final],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("baseline mux failed: " + (r.stderr or "")[-300:])
    return final


def build(entry, workdir, narration_path=None, music=None, W=1920, H=1080,
          fps=25, accent="cyan", log=None, force=False, compare=False):
    """Render a complete documentary film. Returns a report dict."""
    log = _log_factory(log)
    t0 = time.time()
    os.makedirs(workdir, exist_ok=True)
    report = {"title": entry.get("title"), "kind": entry.get("kind", "long"),
              "stages": {}, "errors": [], "started": time.strftime("%Y-%m-%d %H:%M:%S")}

    if not enabled() and not force:
        raise SystemExit(f"{FLAG}=false — cinematic editor is in test mode. "
                         f"Use --force (or set the flag) to render.")

    # 1 - narration ------------------------------------------------------------
    npath = narration_path or _gen_narration(entry, workdir, log)
    if not npath or not os.path.exists(npath):
        raise SystemExit("cinematic: no narration audio (TTS failed, nothing rendered)")
    ndur = SB.audio_duration(npath)
    report["stages"]["narration"] = {"path": npath, "duration": round(ndur, 2)}
    log(f"narration: {ndur:.1f}s")

    # 2 - storyboard -----------------------------------------------------------
    sb = SB.build(entry, narration_path=npath, duration=ndur, announce=log)
    errs = SB.validate(sb)
    if errs:
        report["errors"] += errs[:6]
        log("storyboard warnings: " + "; ".join(errs[:3]))
    SB.save(sb, os.path.join(workdir, "storyboard.json"))
    report["stages"]["storyboard"] = {"scenes": sb["scene_count"],
                                      "timing_source": sb["timing_source"],
                                      "validation_errors": errs}
    report["storyboard"] = sb

    # 3+4 - visuals and scene renders ------------------------------------------
    man_path = os.path.join(workdir, "asset_manifest.json")
    manifest = VM.load_manifest(man_path)
    used_hashes = [a.get("dhash") for a in manifest.get("history", [])][-40:]
    used_hues = []
    used_ids = set(manifest.get("history_ids", []))
    assets, clips, render_errors = [], [], []
    XF = 0.55                     # transition length, must match the assembly
    n_scenes = len(sb["scenes"])
    for idx, sc in enumerate(sb["scenes"]):
        # every scene but the last gets a tail long enough to be consumed by the
        # transition, so the finished film matches the narration to the frame
        dur = max(sc["duration"], 1.2) + (XF if idx < n_scenes - 1 else 0.0)
        try:
            asset = _matcher()(sc, os.path.join(workdir, "assets"), manifest,
                               used_hashes, used_hues, used_ids)
        except Exception as e:
            asset = {"kind": "image", "path": VM.make_card(
                sc, os.path.join(workdir, "assets", f"s{sc['scene_id']:02d}_card.png")),
                "source": "generated", "asset_id": f"card{sc['scene_id']}",
                "license": "original (generated locally)", "attribution": "",
                "duration": 0.0, "url": "", "query": "n/a", "relevance": 0}
            log(f"  scene {sc['scene_id']}: matcher error ({str(e)[:70]}) -> card")
        # a slow scale drift needs a source at least as long as the scene
        if asset.get("kind") == "video" and (asset.get("duration") or 0) < dur:
            asset["kind"] = "video_short"
        out = os.path.join(workdir, "scenes", f"scene{sc['scene_id']:02d}.mp4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:
            MO.render_scene(sc, asset, out, dur, W=W, H=H, fps=fps, log=log)
        except Exception as e:
            render_errors.append({"scene": sc["scene_id"], "error": str(e)[:180]})
            log(f"  scene {sc['scene_id']}: render failed, card retry")
            card = VM.make_card(sc, os.path.join(workdir, "assets",
                                                 f"s{sc['scene_id']:02d}_card2.png"))
            asset.update({"kind": "image", "path": card, "source": "generated",
                          "asset_id": f"card{sc['scene_id']}"})
            MO.render_scene(sc, asset, out, dur, W=W, H=H, fps=fps, log=log)
        assets.append({**{k: asset.get(k) for k in
                          ("kind", "path", "source", "asset_id", "url", "license",
                           "attribution", "query", "relevance", "provider",
                           "creator", "page", "license_url", "commercial_ok",
                           "attribution_required", "width", "height", "sha256")},
                       "scene_id": sc["scene_id"]})
        clips.append(out)

    total_src = len({a["asset_id"] for a in assets if a["source"] != "generated"})
    log(f"visuals: {len(assets)} scenes, {total_src} distinct sourced assets, "
        f"{sum(1 for a in assets if a['source'] == 'generated')} generated cards")
    report["stages"]["visuals"] = {"scenes": len(assets),
                                   "distinct_sources": total_src,
                                   "generated_cards": sum(1 for a in assets
                                                          if a["source"] == "generated")}
    manifest["assets"] = assets
    manifest.setdefault("history", []).extend(
        [{"asset_id": a["asset_id"], "dhash": None, "source": a["source"]}
         for a in assets if a["source"] != "generated"])
    manifest["history_ids"] = sorted(used_ids)
    VM.save_manifest(manifest, man_path)
    report["assets"] = assets

    # 5 - timeline assembly (video only) ---------------------------------------
    silent_video = os.path.join(workdir, "timeline.mp4")
    MO.assemble(clips, [s["transition"] for s in sb["scenes"]],
                trans_dur=XF, out_path=silent_video, W=W, H=H, fps=fps, log=log)
    report["stages"]["assembly"] = {"path": silent_video,
                                    "duration": round(MO.probe_video(silent_video)[0], 2)}

    # 6 - captions -------------------------------------------------------------
    ass = os.path.join(workdir, "captions.ass")
    cap_meta = CAP.build(sb, ass, W=W, H=H, accent=accent)
    cap_val = CAP.validate(ass, ndur)
    report["stages"]["captions"] = {**cap_meta, "validation": cap_val}
    log(f"captions: {cap_meta['cues']} cues ({cap_meta['timing_source']})"
        + ("" if cap_val["ok"] else f" — {len(cap_val['errors'])} problems"))

    # 7 - audio ----------------------------------------------------------------
    nar_norm = AU.prepare_narration(npath, os.path.join(workdir, "narration_norm.wav"))
    if music and os.path.exists(music):
        bed = music
        log(f"audio: music bed from file {os.path.basename(music)}")
    else:
        bed = AU.make_bed(os.path.join(workdir, "bed.wav"), ndur, gain_db=-27)
        log("audio: original ambient bed synthesised (no copyright risk)")
    mixed = AU.mix(nar_norm, bed, os.path.join(workdir, "mix.m4a"))
    ametrics = AU.measure(mixed)
    report["stages"]["audio"] = {"mix": mixed, "metrics": ametrics}
    log(f"audio: {ametrics.get('lufs')} LUFS, peak {ametrics.get('true_peak_db')} dBTP")

    # 8 - final mux with burned captions ---------------------------------------
    final = os.path.join(workdir, "cinematic.mp4")
    ass_q = ass.replace("\\", "/").replace(":", "\\:").replace("'", "")
    vf = (f"ass='{ass_q}'")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", silent_video,
                        "-i", mixed, "-vf", vf, "-map", "0:v", "-map", "1:a",
                        "-c:v", "libx264", "-preset", MO.quality()["preset"],
                        "-crf", str(MO.quality()["crf"]), "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-shortest",
                        "-movflags", "+faststart", final],
                       capture_output=True, text=True)
    if r.returncode or not os.path.exists(final):
        raise RuntimeError("final mux failed: " + (r.stderr or "")[-400:])
    log(f"mux: {final} ({os.path.getsize(final)//1024//1024} MB)")

    # 9 - QC -------------------------------------------------------------------
    rep = QC.check(final, storyboard=sb, captions_meta=cap_meta,
                   caption_errors=cap_val["errors"], assets=assets,
                   render_errors=render_errors, expected_w=W, expected_h=H,
                   expected_fps=fps)
    QC.save(rep, os.path.join(workdir, "qc_report.json"))
    report["qc"] = rep
    report["stages"]["qc"] = {"ok": rep["ok"], "score": rep["score"]}
    report["output"] = final
    if compare:
        try:
            log("baseline: rendering the same storyboard without the new engine")
            b = build_baseline(sb, assets, workdir, mixed, W, H, fps, log=log)
            brep = QC.check(b, storyboard=sb, assets=assets,
                            render_errors=render_errors, expected_w=W,
                            expected_h=H, expected_fps=fps)
            QC.save(brep, os.path.join(workdir, "qc_report_baseline.json"))
            report["baseline"] = {"output": b, "qc": brep}
            cmp = {"new": {"score": rep["score"], "ok": rep["ok"],
                           "duration": rep["duration_s"],
                           "size_bytes": rep["size_bytes"]},
                   "baseline": {"score": brep["score"], "ok": brep["ok"],
                                "duration": brep["duration_s"],
                                "size_bytes": brep["size_bytes"]},
                   "note": ("both renders use the same storyboard, the same assets "
                            "and the same narration; only the editing changes")}
            with open(os.path.join(workdir, "compare.json"), "w") as f:
                json.dump(cmp, f, indent=1)
            log(f"compare: new QC {rep['score']} vs baseline {brep['score']}")
        except Exception as ex:
            report["errors"].append("baseline compare failed: " + str(ex)[:160])
            log("baseline compare failed: " + str(ex)[:160])
    report["elapsed_s"] = round(time.time() - t0, 1)
    report["flag"] = {FLAG: os.environ.get(FLAG, "false")}
    with open(os.path.join(workdir, "build_report.json"), "w") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    print(QC.summary(rep), flush=True)
    return report


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Cinematic documentary editor")
    ap.add_argument("--entry", help="library entry JSON file")
    ap.add_argument("--sample", action="store_true", help="use the built-in demo script")
    ap.add_argument("--narration", help="existing narration audio (skips TTS)")
    ap.add_argument("--music", help="optional licensed music bed file")
    ap.add_argument("--workdir", default="cine_out")
    ap.add_argument("--accent", default="cyan")
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--force", action="store_true",
                    help="render even when ENABLE_CINEMATIC_EDITOR is false")
    ap.add_argument("--compare", action="store_true",
                    help="also render the baseline (pre-upgrade) cut for A/B")
    ap.add_argument("--check-flag", action="store_true")
    a = ap.parse_args(argv)
    if a.check_flag:
        print(json.dumps({FLAG: os.environ.get(FLAG, "false"), "enabled": enabled()}))
        return 0
    if a.sample:
        entry = SAMPLE
    elif a.entry:
        with open(a.entry) as f:
            entry = json.load(f)
    else:
        ap.error("--entry or --sample is required")
    try:
        rep = build(entry, a.workdir, narration_path=a.narration, music=a.music,
                    W=a.width, H=a.height, fps=a.fps, accent=a.accent,
                    force=a.force, compare=a.compare)
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        return 1
    print(json.dumps({"output": rep["output"], "qc_ok": rep["qc"]["ok"],
                      "qc_score": rep["qc"]["score"],
                      "duration": rep["qc"]["duration_s"],
                      "elapsed_s": rep["elapsed_s"]}, indent=1))
    return 0 if rep["qc"]["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
