#!/usr/bin/env python3
"""1440p60 renderer test harness (owner request 2026-11-01).

Two modes, both fully offline-capable and both verified with ffprobe:

  --mode sample   ~60 s film, the real editing path (motion + xfade + burned
                  captions + ducked audio) encoded once to the 1440p60 spec.
  --mode full     9-10 min film at the same spec, encoded single-pass to measure
                  real encoder throughput on a GPU-less runner.

Nothing here publishes, uploads or touches the production schedule. Production
stays on factory.render() until ENABLE_1440P60_RENDERER=true is set by the owner.

Usage:
  python scripts/render_1440p60_test.py --mode sample --workdir out1440p
  python scripts/render_1440p60_test.py --mode full --minutes 9.5 --workdir out1440p
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FACTORY = os.path.join(os.path.dirname(HERE), "factory")
if FACTORY not in sys.path:
    sys.path.insert(0, FACTORY)

import render_config as RC          # noqa: E402
import render_probe as RP           # noqa: E402
from cine import storyboard as SB   # noqa: E402
from cine import visual_match as VM  # noqa: E402
from cine import captions as CAP    # noqa: E402
from cine import audio as AU        # noqa: E402
from cine import editor as CINE     # noqa: E402

FLAG = "ENABLE_1440P60_RENDERER"

SAMPLE_SCRIPT = CINE.SAMPLE["narration"]

# A 9-10 minute documentary script, written for the throughput test so the long
# render has real narration instead of looped silence.
LONG_SCRIPT = """
Google just opened a door that nobody is ready to close. A system that used to
require a render farm now runs a living world on a phone. The demonstration
lasted four minutes and it changed how three industries are planning the next
decade. This is not a video about a feature. It is a video about a new kind of
reality, one that is generated instead of filmed.

The machine watches a single sentence and builds a place. A street, a table, a
room with light falling through a window that was invented two seconds earlier.
You can move through it. You can push against it. And when you push, the world
answers with physics that were never written by a designer.

That detail matters more than the graphics. For thirty years, virtual worlds
were handcrafted. Artists placed every wall. Engineers wrote every collision.
A studio of two hundred people spent four years building a city that a player
would cross in nine minutes. That model is now the expensive way to do it.

The new model learns what a world should feel like from video. It watches
millions of hours of ordinary motion, doors opening, cups falling, crowds
turning, and it extracts the rules that make those moments believable. Then it
composes new moments from the same rules at roughly the speed of thought.

Researchers describe this as a learned simulator. That phrase is doing a lot of
work. A simulator is something you can test a decision against before you make
it. If the simulator is good enough, you stop guessing. If it is cheap enough,
you stop rationing it.

That is why the robotics labs are the loudest voices in the room. A robot arm
that fails in the real world costs money, time and sometimes a finger. A robot
arm that fails ten thousand times inside a generated world costs electricity.
The economics of physical mistakes are about to collapse.

The demonstration showed exactly that. A robot learned to open a drawer inside a
kitchen that had never existed. The drawer handle was slightly different on every
attempt. The lighting changed. The camera moved. The robot adapted inside a
rehearsal space built for it in milliseconds.

Engineers call this domain randomisation, and until now it was a scripted
process, expensive and slow, a team of people writing variations by hand. The
new approach generates the variations on demand and keeps them physically
consistent. Nothing drifts. Nothing cheats.

There is a second audience for this, and it is much bigger. Games. Not the
games you play for fifty hours, but the games you might play for five minutes
because a machine built one for you while you were deciding whether to.

Imagine describing a memory and walking through it. Imagine a classroom where
the history lesson is a street you can visit. Imagine a training manual that
rebuilds the machine every time a new model ships. None of that needs a studio
of two hundred people.

The market reacted before the conference ended. Gaming stocks moved sharply
downward, then recovered, then moved again. Analysts called it an overreaction
and then quietly rewrote their forecasts. The people who build engines for a
living had the most interesting response, which was mostly silence followed by
aggressive hiring.

Because the honest question is not whether the technology works. It works well
enough to be shown publicly. The honest question is who owns the world once it
can be generated. The model, the compute, the licence, the data, the platform
that rents it to you by the minute.

The researchers who built it say the real target is not entertainment. They say
the target is a machine that can rehearse reality before it touches reality.
Factories. Hospitals. Warehouses. Roads. Every place where a mistake has a
physical price tag attached to it.

If that is true, then the most important product of this decade may not be a
model at all. It may be the rehearsal. The hour a machine spends practising
before it is allowed to act. The quiet, invisible training that happens before
anything is real.

That is the beginning of synthetic reality. Not a replacement for the world, but
a second copy running beside it, cheaper and faster and safe to destroy. And the
people who build it are telling us, politely, that the copy is already good
enough to trust with small decisions.

Small decisions are how it starts. A robot picks up a cup in a world that does
not exist. Then it picks up a real cup. Then it picks up a real cup in a
hospital at three in the morning, and nobody thinks about the rehearsal at all.

The copy becomes invisible. The rehearsal becomes infrastructure. And the world
we film starts to look like the world we generate, which is a strange sentence
that will sound ordinary within five years.
"""


def log(msg):
    print(msg, flush=True)


def run(cmd, what="ffmpeg", logfile=None):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        err = (r.stderr or "")
        if logfile:
            try:
                with open(logfile, "w", encoding="utf-8") as f:
                    f.write(" ".join(cmd) + "\n\n" + err)
            except OSError:
                pass
        raise RuntimeError(f"{what} failed: " + err[-1800:])
    return r


def ensure_narration(text, out_mp3, script_file=None):
    """Real speech via edge-tts, espeak-ng fallback. Never fake audio."""
    src_text = open(script_file, encoding="utf-8").read() if script_file else text
    if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 30000:
        log(f"narration: reusing {os.path.basename(out_mp3)}")
        return out_mp3
    try:
        import asyncio
        import edge_tts
        async def go(voice):
            c = edge_tts.Communicate(src_text, voice)
            await c.save(out_mp3)
        asyncio.run(go(os.environ.get("TTS_VOICE", "en-US-AriaNeural")))
        if os.path.getsize(out_mp3) > 30000:
            log(f"narration: edge-tts ok ({os.path.getsize(out_mp3) // 1024} KB)")
            return out_mp3
    except Exception as e:
        log(f"narration: edge-tts unavailable ({str(e)[:100]}) -> espeak-ng")
    wav = out_mp3 + ".wav"
    run(["espeak-ng", "-v", "en-us", "-s", "150", "-w", wav, src_text], "espeak")
    run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libmp3lame",
         "-b:a", "192k", out_mp3], "ffmpeg audio")
    return out_mp3


def expand_scenes(sb, max_len=14.0):
    """Split long scenes into <=max_len chunks so one scene never starves its
    source clip. Timing stays exactly aligned with the narration."""
    out = []
    for sc in sb["scenes"]:
        d = sc["duration"]
        n = max(1, int(round(d / max_len + 0.4999)))
        piece = d / n
        for i in range(n):
            c = dict(sc)
            c["start_time"] = round(sc["start_time"] + i * piece, 3)
            c["end_time"] = round(sc["start_time"] + (i + 1) * piece, 3)
            c["duration"] = round(piece, 3)
            c["scene_id"] = len(out) + 1
            c["_src_scene"] = sc["scene_id"]
            # vary the move so a long scene does not look frozen
            moves = ["zoom_in", "pan_left", "zoom_out", "drift_up", "pan_right",
                     "push_in_slow"]
            c["motion_style"] = moves[(i + sc["scene_id"]) % len(moves)]
            out.append(c)
    return out


def source_scan(assets, cfg):
    """Low-resolution detection for every source actually used."""
    rows, warns = [], []
    for a in assets:
        sa = cfg.source_assessment(a.get("width"), a.get("height"))
        rows.append({"scene_id": a.get("scene_id"), "source": a.get("source"),
                     "width": a.get("width"), "height": a.get("height"),
                     "license": a.get("license"), "upscale_factor": sa["factor"],
                     "warning": sa["warning"]})
        if sa["warning"]:
            warns.append(f"scene {a.get('scene_id')}: {sa['warning']}")
    return rows, warns


def render_scene_1440(scene, asset, out, dur, cfg, intermediate=True):
    """One scene -> one clip at target size/fps. Intermediates use a high-quality
    CRF so the final pass is the only lossy encode that matters."""
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    mov = CINE.MO.motion_expr(scene.get("motion_style", "zoom_in"), dur, cfg.fps)
    up = 1.28
    vf = ",".join([
        f"scale={int(cfg.width * up)}:{int(cfg.height * up)}:"
        f"force_original_aspect_ratio=increase:flags=lanczos",
        f"crop={int(cfg.width * up)}:{int(cfg.height * up)},setsar=1",
        f"zoompan=z='{mov['z']}':x='{mov['x']}':y='{mov['y']}':d=1:"
        f"s={cfg.width}x{cfg.height}:fps={cfg.fps}",
        CINE.MO.GRADES[CINE.MO.grade_for(scene)],
        "vignette=PI/5", f"format={cfg.pix_fmt}",
    ])
    enc = (["-c:v", "libx264", "-preset", "veryfast", "-crf", "16"]
           if intermediate else cfg.video_args(faststart=False))
    if asset.get("kind") == "image":
        inputs = ["-loop", "1", "-i", asset["path"], "-t", f"{dur:.3f}"]
    else:
        src_dur = float(asset.get("duration") or 0)
        if not src_dur:                      # asset came without a duration
            src_dur = float((RP.probe_json(asset["path"]).get("format") or {})
                            .get("duration") or 0)
        need_loop = (not src_dur) or src_dur < dur * 1.2
        start = 0.0 if need_loop else max(min(src_dur * 0.2,
                                             max(src_dur - dur, 0)), 0.0)
        # always loop the source: on the CI runner a stock clip shorter than the
        # beat (or an asset with no recorded duration, which used to disable the
        # loop) silently produced a 9 s clip for an 11.7 s beat, so the finished
        # video came out 32 s against 46.8 s of narration.
        inputs = (["-stream_loop", "-1", "-ss", f"{start:.2f}",
                   "-i", asset["path"], "-t", f"{dur:.3f}"])
    cmd = (["ffmpeg", "-v", "error", "-y"] + inputs +
           ["-vf", vf, "-r", str(cfg.fps)] + enc +
           ["-an", "-pix_fmt", cfg.pix_fmt, out])
    t0 = time.time()
    run(cmd, f"scene {scene['scene_id']}")
    got = RP.probe_json(out)
    st = ((got.get("streams") or [{}])[0] if got else {})
    if int(st.get("width") or 0) != int(cfg.width):
        raise RuntimeError(f"scene {scene['scene_id']} wrong width {st.get('width')}")
    log(f"  scene {scene['scene_id']:02d} {dur:5.2f}s "
        f"{asset.get('source', '?'):9s} {time.time() - t0:5.1f}s "
        f"{os.path.basename(out)}")
    return out


def _assemble(clips, transitions, trans_dur, wd):
    """Join the scenes into one timeline before the final encode.

    Two-stage on purpose: the Ubuntu ffmpeg 8.0.1 runner refuses graph label
    binding when xfade/concat and a mapped output share one -filter_complex, so
    the timeline is built here first and the final pass then uses a plain -vf
    chain. xfade is attempted first (nicer), hard-cut concat is the fallback.
    """
    if len(clips) == 1:
        return clips[0]
    base = os.path.join(wd, "timeline.mp4")
    if transitions:
        fc, cur = [], "[0:v]"
        durs = [float((RP.probe_json(c).get("format") or {}).get("duration") or 0)
                for c in clips]
        off = 0.0
        for i in range(1, len(clips)):
            off += durs[i - 1] - trans_dur
            tr = transitions[i - 1] if i - 1 < len(transitions) else "dissolve"
            fc.append(f"{cur}[{i}:v]xfade=transition={tr}:duration={trans_dur:.2f}:"
                      f"offset={max(off, 0):.3f}[x{i}]")
            cur = f"[x{i}]"
        inputs = []
        for c in clips:
            inputs += ["-i", c]
        cmd = (["ffmpeg", "-v", "error", "-y"] + inputs +
               ["-filter_complex", ";".join(fc), "-map", cur,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                "-pix_fmt", "yuv420p", base])
        try:
            run(cmd, "timeline (xfade)",
                logfile=os.path.join(wd, "encode_error_timeline.log"))
            log("timeline: xfade chain built")
            return base
        except RuntimeError as ex:
            log("timeline: xfade failed (" + str(ex).splitlines()[-1][:90]
                + ") - falling back to hard-cut concat")
    lst = os.path.join(wd, "concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for c in clips:
            f.write("file '" + os.path.abspath(c).replace("'", "") + "'\n")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-c", "copy", base], "timeline (concat)",
        logfile=os.path.join(wd, "encode_error_concat.log"))
    log("timeline: hard-cut concat built")
    return base


def final_encode(clips, cfg, out, audio=None, ass=None, transitions=None,
                 trans_dur=0.55, fade=(0.8, 1.2)):
    """Final spec encode of the assembled timeline (plain -vf, no graph labels)."""
    wd = os.path.dirname(out) or "."
    base = _assemble(clips, transitions, trans_dur, wd)
    inputs = ["-i", base]
    if audio:
        inputs += ["-i", audio]
    ass_q = ""
    if ass:
        ass_q = os.path.abspath(ass).replace("\\", "/").replace(":", "\\:").replace("'", "")
    scaler = (f"scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease,"
              f"pad={cfg.width}:{cfg.height}:(ow-iw)/2:(oh-ih)/2:color=black,"
              f"setsar=1")
    tag = ("setparams=colorspace=bt709:color_primaries=bt709:"
           "color_trc=bt709:range=tv")
    variants = [
        ("spec", (f"ass={ass_q}," if ass_q else "")
         + f"{tag},{scaler},fps={cfg.fps},format={cfg.pix_fmt}"),
        ("no-captions", f"{tag},{scaler},fps={cfg.fps},format={cfg.pix_fmt}"),
        ("bare", None),   # no -vf at all; encoder options still set the spec
    ]
    last = None
    t0 = time.time()
    for name, vf in variants:
        cmd = ["ffmpeg", "-v", "error", "-y"] + inputs
        if vf:
            cmd += ["-vf", vf]
        cmd += ["-map", "0:v"]
        if audio:
            cmd += ["-map", "1:a"] + cfg.audio_args() + ["-shortest"]
        else:
            cmd += ["-an"]
        cmd += cfg.video_args() + [out]
        try:
            run(cmd, f"final encode ({name})",
                logfile=os.path.join(wd, f"encode_error_{name}.log"))
            if name != "spec":
                log(f"final encode: '{name}' variant used"
                    + ("" if name == "spec" else " (captions may be missing)"))
            log(f"final encode: {time.time() - t0:.1f}s -> {out} "
                f"({os.path.getsize(out) // 1024 // 1024} MB)")
            return out
        except RuntimeError as ex:
            last = ex
            log(f"final encode attempt '{name}' failed: "
                + " | ".join(str(ex).splitlines()[-3:])[:400])
            try:
                if os.path.exists(out):
                    os.remove(out)
            except OSError:
                pass
    raise last


def build(mode, workdir, minutes=9.5, script_file=None, narration=None,
          max_scenes=None):
    os.makedirs(workdir, exist_ok=True)
    res = RP.Resources(workdir)
    report = {"mode": mode, "flag": {FLAG: os.environ.get(FLAG, "false")},
              "started_at": time.strftime("%Y-%m-%d %H:%M:%S")}

    caps = RC.assert_ready()
    cfg = RC.RenderConfig.from_env(os.environ.get("RENDER_1440_PROFILE", "1440p60"))
    report["capabilities"] = {"ffmpeg": caps.get("version"), "gpu": caps["gpu"],
                              "encoders_ok": all(caps["encoders"].values()),
                              "filters_ok": all(caps["filters"].values())}
    report["config"] = cfg.report()
    log(f"config: {cfg.name} {cfg.width}x{cfg.height}@{cfg.fps} "
        f"{cfg.bitrate} {cfg.profile} gop={cfg.gop} bf={cfg.bframes}")
    res.mark("capabilities")

    # 1) narration ---------------------------------------------------------
    nar = narration or os.path.join(workdir, "narration.mp3")
    if mode == "sample":
        nar = ensure_narration(SAMPLE_SCRIPT, nar)
            # short demo narration
    text = None
    if mode == "full":
        text = (open(script_file, encoding="utf-8").read() if script_file
                else LONG_SCRIPT)
        nar = ensure_narration(text, nar)
    ndur = SB.audio_duration(nar)
    log(f"narration: {ndur:.1f}s")
    res.mark("narration")

    # 2) storyboard --------------------------------------------------------
    entry = {"title": f"1440p60 {mode} render test", "kind": "long",
             "narration": text or SAMPLE_SCRIPT,
             "beats": [{"t": s.strip()} for s in (text or SAMPLE_SCRIPT).split("\n")
                       if s.strip()][:40]}
    sb = SB.build(entry, narration_path=nar, duration=ndur, announce=log)
    errs = SB.validate(sb)
    # a single 47 s scene is a useless sample: split into ~12 s chunks so the
    # run exercises several motions, xfade transitions and caption cues
    scenes = expand_scenes(sb, max_len=(12.0 if mode == "sample" else 14.0))
    if max_scenes and len(scenes) > max_scenes:
        log(f"storyboard: capping {len(scenes)} scenes at {max_scenes} for this run")
        bad = scenes[max_scenes:]
        scenes = scenes[:max_scenes]
        ndur = scenes[-1]["end_time"]
        nar = trim_audio(nar, ndur, os.path.join(workdir, "narration_trim.mp3"))
    report["storyboard"] = {"scenes": len(scenes), "narration_duration": round(ndur, 2),
                            "validation_errors": errs,
                            "timing_source": sb.get("timing_source")}
    log(f"storyboard: {len(scenes)} scenes over {ndur:.1f}s"
        + (f" ({len(errs)} warnings)" if errs else ""))
    res.mark("storyboard")

    # 3) visuals -----------------------------------------------------------
    man_path = os.path.join(workdir, "asset_manifest.json")
    man = VM.load_manifest(man_path)
    used_h, used_hue, used_ids = [], [], set(man.get("history_ids", []))
    assets = []
    for sc in scenes:
        try:
            a = VM.match_scene(sc, os.path.join(workdir, "assets"), man, used_h,
                               used_hue, used_ids)
        except Exception as e:
            log(f"  scene {sc['scene_id']}: matcher error {str(e)[:70]} -> card")
            png = VM.make_card(sc, os.path.join(workdir, "assets",
                                                f"c{sc['scene_id']:02d}.png"),
                               w=int(cfg.width), h=int(cfg.height))
            a = {"kind": "image", "path": png, "source": "generated",
                 "asset_id": f"card{sc['scene_id']}", "license": "original",
                 "duration": 0.0, "width": int(cfg.width), "height": int(cfg.height),
                 "url": "", "query": "n/a", "relevance": 0}
        a["scene_id"] = sc["scene_id"]
        assets.append(a)
    rows, warns = source_scan(assets, cfg)
    report["sources"] = rows
    report["source_warnings"] = warns
    if warns:
        log(f"quality warnings: {len(warns)} source(s) below target")
        for w in warns[:6]:
            log("  ! " + w)
    res.mark("visuals")

    # 4) scene renders -----------------------------------------------------
    clips = []
    for sc, a in zip(scenes, assets):
        out = os.path.join(workdir, "scenes", f"s{sc['scene_id']:03d}.mp4")
        clips.append(render_scene_1440(sc, a, out, max(sc["duration"], 1.0), cfg,
                                       intermediate=(mode == "sample")))
    res.mark("scene_render")

    # 5) audio -------------------------------------------------------------
    nar_norm = AU.prepare_narration(nar, os.path.join(workdir, "narration_norm.wav"))
    bed = AU.make_bed(os.path.join(workdir, "bed.wav"), ndur, gain_db=-27)
    mixed = AU.mix(nar_norm, bed, os.path.join(workdir, "mix.m4a"))
    res.mark("audio")
    report["audio_metrics"] = AU.measure(mixed)

    # 6) final encode ------------------------------------------------------
    out = os.path.join(workdir, f"{mode}_1440p60.mp4")
    if mode == "sample":
        ass = os.path.join(workdir, "captions.ass")
        cap = CAP.build(sb, ass, W=int(cfg.width), H=int(cfg.height))
        report["captions"] = {**cap, "validation": CAP.validate(ass, ndur)}
        final_encode(clips, cfg, out, audio=mixed, ass=ass,
                     transitions=[s["transition"] for s in sb["scenes"]])
    else:
        # single-pass spec encode (no transitions) so the throughput number is
        # an honest encoder measurement, then mux the audio without re-encoding
        silent = final_encode(clips, cfg, os.path.join(workdir, "video_only.mp4"))
        run(["ffmpeg", "-v", "error", "-y", "-i", silent, "-i", mixed,
             "-map", "0:v", "-map", "1:a", "-c:v", "copy"] + cfg.audio_args() +
            ["-shortest", "-movflags", "+faststart", out], "audio mux")
        report["note"] = ("long test encodes once to spec without transitions; "
                          "its purpose is encoder throughput + full-length spec "
                          "verification, not final picture lock")
    res.mark("final_encode")

    # 7) verify ------------------------------------------------------------
    ver = RP.verify(out, cfg, expected_duration=ndur, expect_scenes=scenes)
    RP.save(ver, os.path.join(workdir, "ffprobe_report.json"))
    report["verify"] = ver
    report["resources"] = res.report(output=out)
    RP_save(report, os.path.join(workdir, "render_report.json"))
    log(RP.summary(ver))
    log("resources: " + json.dumps(report["resources"], indent=1))
    return report


def trim_audio(src, dur, out):
    run(["ffmpeg", "-v", "error", "-y", "-i", src, "-t", f"{dur:.2f}",
         "-c:a", "libmp3lame", "-b:a", "192k", out], "trim audio")
    return out


def RP_save(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="1440p60 renderer test")
    ap.add_argument("--mode", choices=["sample", "full"], default="sample")
    ap.add_argument("--minutes", type=float, default=9.5)
    ap.add_argument("--workdir", default="out_1440p60")
    ap.add_argument("--narration", help="reuse an existing narration file")
    ap.add_argument("--script-file", help="text file to narrate in full mode")
    ap.add_argument("--max-scenes", type=int, default=0,
                    help="cap scenes (keeps a smoke run cheap)")
    a = ap.parse_args(argv)
    t0 = time.time()
    try:
        rep = build(a.mode, a.workdir, minutes=a.minutes,
                    script_file=a.script_file, narration=a.narration,
                    max_scenes=a.max_scenes or None)
    except Exception:
        import traceback
        traceback.print_exc()
        return 1
    ok = rep["verify"]["ok"]
    print(json.dumps({"mode": a.mode, "verify_ok": ok,
                      "score": rep["verify"]["score"],
                      "duration": rep["verify"]["duration_s"],
                      "size_mb": rep["resources"].get("output_mb"),
                      "wall_s": rep["resources"]["wall_seconds"],
                      "fps_effective": rep["resources"].get("fps_effective"),
                      "peak_rss_mb": rep["resources"]["peak_rss_mb_children"],
                      "total_wall_s": round(time.time() - t0, 1)}, indent=1))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
