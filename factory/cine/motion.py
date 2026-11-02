"""Phase 4 + 7 - cinematic visual engine and timeline editing (FFmpeg only).

Every scene is rendered to an intermediate clip with its own move and grade,
then the timeline is assembled with real xfade transitions. Rules baked in:

  * motion is chosen per scene (zoom in / zoom out / pan / push) and never the
    same move applied to the whole film;
  * grade profiles rotate so the film breathes instead of looking uniform;
  * stills get Ken-Burns movement, clips get a slow scale drift;
  * no black frames by construction: scenes are joined with xfade offsets and
    the first/last fade is added once, on the finished timeline;
  * quality and speed are configurable (RENDER_QUALITY=draft|standard|high) so
    GitHub Actions stays inside its CPU budget.
"""
import json
import os
import shlex
import subprocess

QUALITY = {
    "draft":    {"crf": 24, "preset": "veryfast", "grain": 4, "inter": 24},
    "standard": {"crf": 20, "preset": "veryfast", "grain": 6, "inter": 20},
    "high":     {"crf": 18, "preset": "medium",   "grain": 8, "inter": 18},
}

GRADES = {
    # contrast, saturation, brightness, gamma, warmth
    "cool_lab":    "eq=contrast=1.07:saturation=1.04:brightness=-0.010:gamma=0.99",
    "warm_night":  "eq=contrast=1.05:saturation=1.10:brightness=-0.004:gamma=1.01",
    "neutral_doc": "eq=contrast=1.03:saturation=1.02:brightness=0.000",
    "deep_blue":   "eq=contrast=1.08:saturation=1.00:brightness=-0.014:gamma=0.98",
}


def quality():
    return QUALITY.get(os.environ.get("RENDER_QUALITY", "standard"), QUALITY["standard"])


def motion_expr(style, dur, fps):
    """zoompan expression + crop anchor for one motion style."""
    frames = max(int(round(dur * fps)), 2)
    zmax = 1.14
    ramp = f"(1+{zmax - 1:.3f}*on/{frames})"
    back = f"({zmax:.3f}-{zmax - 1:.3f}*on/{frames})"
    if style == "zoom_in":
        return dict(z=ramp, x="iw/2-(iw/zoom/2)", y="ih/2-(ih/zoom/2)")
    if style == "zoom_out":
        return dict(z=back, x="iw/2-(iw/zoom/2)", y="ih/2-(ih/zoom/2)")
    if style == "push_in_slow":
        return dict(z=f"(1+0.08*on/{frames})", x="iw/2-(iw/zoom/2)",
                    y="ih/2-(ih/zoom/2)")
    if style == "pan_left":
        return dict(z="1.12", x=f"(iw-iw/zoom)*(1-on/{frames})",
                    y="ih/2-(ih/zoom/2)")
    if style == "pan_right":
        return dict(z="1.12", x=f"(iw-iw/zoom)*(on/{frames})",
                    y="ih/2-(ih/zoom/2)")
    if style == "drift_up":
        return dict(z="1.10", x="iw/2-(iw/zoom/2)",
                    y=f"(ih-ih/zoom)*(1-on/{frames})")
    return dict(z="1.06", x="iw/2-(iw/zoom/2)", y="ih/2-(ih/zoom/2)")


def grade_for(scene):
    if scene.get("_grade"):
        return scene["_grade"]
    order = ["cool_lab", "warm_night", "neutral_doc", "deep_blue"]
    if scene.get("visual_type") in ("infographic", "motion_graphics"):
        return "neutral_doc"
    return order[(scene["scene_id"] - 1) % len(order)]


def scene_filter(scene, dur, W, H, fps, still=False):
    """Filter chain that turns one asset into one timed, moving, graded clip."""
    m = motion_expr(scene.get("motion_style", "zoom_in"), dur, fps)
    q = quality()
    up = 1.28                                   # headroom for the move
    parts = [
        f"scale={int(W * up)}:{int(H * up)}:force_original_aspect_ratio=increase",
        f"crop={int(W * up)}:{int(H * up)}",
        f"setsar=1",
        (f"zoompan=z='{m['z']}':x='{m['x']}':y='{m['y']}':d=1:"
         f"s={W}x{H}:fps={fps}"),
        GRADES[grade_for(scene)],
    ]
    if scene.get("visual_type") in ("infographic", "motion_graphics"):
        parts.append("unsharp=5:5:0.55")        # crisper type/lines
    if q["grain"] > 0:
        parts.append(f"noise=alls={q['grain']}:allf=t+u")
    parts.append("vignette=PI/5")
    parts.append("format=yuv420p")
    return ",".join(parts)


def render_scene(scene, asset, out_path, dur, W=1920, H=1080, fps=25, log=print):
    """Render one scene clip. Raises on failure so the editor can recover."""
    q = quality()
    still = asset.get("kind") == "image"
    vf = scene_filter(scene, dur, W, H, fps, still=still)
    if still:
        cmd = ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", asset["path"],
               "-t", f"{dur:.3f}", "-vf", vf, "-r", str(fps),
               "-c:v", "libx264", "-preset", q["preset"], "-crf", str(q["inter"]),
               "-pix_fmt", "yuv420p", "-an", out_path]
    else:
        # Use a quarter into the clip (past any fade-in) and LOOP the source:
        # a 9.5s stock clip under a 12s beat used to come out 9.5s long, and the
        # editor then replaced the scene with a motion card (2026-11-02 selftest,
        # scene 3). -stream_loop keeps the scene exactly as long as its narration
        # while -t still bounds the output.
        src_dur = float(asset.get("duration") or 0)
        start = max(min(src_dur * 0.25, max(src_dur - dur, 0)), 0.0) if src_dur else 0.0
        cmd = ["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1",
               "-ss", f"{start:.2f}",
               "-i", asset["path"], "-t", f"{dur:.3f}", "-vf", vf,
               "-r", str(fps), "-c:v", "libx264", "-preset", q["preset"],
               "-crf", str(q["inter"]), "-pix_fmt", "yuv420p", "-an", out_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or not os.path.exists(out_path):
        raise RuntimeError(f"scene {scene['scene_id']} render failed: "
                           f"{(r.stderr or '')[-220:]}")
    ok = probe_video(out_path)
    if not ok or ok[0] < dur * 0.8:
        raise RuntimeError(f"scene {scene['scene_id']} short/invalid output {ok}")
    log(f"  scene {scene['scene_id']:02d} {scene.get('motion_style','?'):12s} "
        f"{dur:5.2f}s {asset['source']:9s} -> {os.path.basename(out_path)}")
    return out_path


def probe_video(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height,r_frame_rate:format=duration",
                            "-of", "json", path], capture_output=True, text=True)
        d = json.loads(r.stdout or "{}")
        st = (d.get("streams") or [{}])[0]
        return (float((d.get("format") or {}).get("duration") or 0),
                int(st.get("width") or 0), int(st.get("height") or 0),
                st.get("r_frame_rate", "0/1"))
    except Exception:
        return None


def concat_hard(clips, out_path, log=print):
    """Baseline join: plain concat, no transitions (the pre-upgrade behaviour)."""
    lst = out_path + ".txt"
    with open(lst, "w") as f:
        for c in clips:
            f.write("file '" + os.path.abspath(c).replace("'", "'\\''") + "'\n")
    q = quality()
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", lst, "-c:v", "libx264", "-preset", q["preset"],
                        "-crf", str(q["crf"]), "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", out_path],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("baseline concat failed: " + (r.stderr or "")[-300:])
    log(f"baseline: {len(clips)} scenes -> {probe_video(out_path)[0]:.1f}s")
    return out_path


XF = {"dissolve": "dissolve", "fade": "fade", "smoothleft": "smoothleft",
      "wipeleft": "wipeleft", "slideleft": "slideleft", "circleopen": "circleopen"}


def assemble(clips, transitions, trans_dur, out_path, W=1920, H=1080, fps=25,
             fade_in=0.8, fade_out=1.2, log=print):
    """Join scene clips with xfade, then fade the finished timeline in/out."""
    if not clips:
        raise RuntimeError("assemble: no clips")
    if len(clips) == 1:
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", clips[0], "-c", "copy", out_path]
        subprocess.run(cmd, check=True)
        return out_path
    inputs, fc = [], []
    for c in clips:
        inputs += ["-i", c]
    durs = [probe_video(c)[0] for c in clips]
    # xfade consumes trans_dur of overlap, so cut the tail of every clip but
    # the last one is handled by the offset maths below.
    cur, off = "[0:v]", 0.0
    for i in range(1, len(clips)):
        off += durs[i - 1] - trans_dur
        tr = XF.get(transitions[i - 1] if i - 1 < len(transitions) else "dissolve",
                    "dissolve")
        lbl = f"[vx{i}]"
        fc.append(f"{cur}[{i}:v]xfade=transition={tr}:duration={trans_dur:.3f}:"
                  f"offset={max(off, 0):.3f}{lbl}")
        cur = lbl
    total = sum(durs) - trans_dur * (len(clips) - 1)
    fc.append(f"{cur}fade=t=in:st=0:d={fade_in:.2f},"
              f"fade=t=out:st={max(total - fade_out, 0):.2f}:d={fade_out:.2f},"
              f"format=yuv420p[vout]")
    q = quality()
    cmd = (["ffmpeg", "-v", "error", "-y"] + inputs +
           ["-filter_complex", ";".join(fc), "-map", "[vout]",
            "-r", str(fps), "-c:v", "libx264", "-preset", q["preset"],
            "-crf", str(q["crf"]), "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            out_path])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or not os.path.exists(out_path):
        raise RuntimeError("assemble failed: " + (r.stderr or "")[-400:])
    log(f"assemble: {len(clips)} scenes -> {total:.1f}s "
        f"({os.path.getsize(out_path) // 1024} KB)")
    return out_path
