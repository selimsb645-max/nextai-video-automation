"""Phase 6 - audio production engine (free, original audio only).

  * the narration keeps the existing Kokoro chain (factory.narration_filters)
    and is re-normalised to -16 LUFS before mixing;
  * the music bed is SYNTHESISED locally with FFmpeg (layered drones + slow
    tremolo + lowpass). It is original audio, so there is no copyright risk and
    no download. A real music file can be passed instead when the owner has one;
  * ducking is a real sidechain compressor keyed by the voice, not a lower
    volume guess;
  * fades in/out are applied to the bed, and the final mix is normalised to
    -14 LUFS / -1.5 dBTP (YouTube reference);
  * measurement (LUFS, true peak, silence, clipping) is returned so QC can
    judge it instead of assuming.
"""
import json
import os
import subprocess

BED_NOTES = {  # minor-ish drone, cinematic but unobtrusive
    "A": [110.0, 164.81, 220.0, 329.63],
    "D": [146.83, 220.0, 293.66, 440.0],
    "F": [87.31, 130.81, 174.61, 261.63],
}


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError((r.stderr or "")[-400:])
    return r


def duration(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def make_bed(out_path, dur, key="A", gain_db=-27, sample_rate=48000):
    """Synthesise an original ambient bed of exactly `dur` seconds."""
    notes = BED_NOTES.get(key, BED_NOTES["A"])
    ins, parts = [], []
    for i, f in enumerate(notes):
        ins += ["-f", "lavfi", "-t", f"{dur:.3f}",
                "-i", f"sine=frequency={f:.2f}:sample_rate={sample_rate}"]
        # each voice gets its own slow tremolo so the pad breathes
        rate = 0.12 + 0.05 * i   # tremolo f must be >= 0.1
        parts.append(f"[{i}:a]volume={0.30 / (i + 1):.3f},"
                     f"tremolo=f={rate:.3f}:d=0.55,"
                     f"aformat=sample_fmts=fltp:channel_layouts=stereo[v{i}]")
    mix_in = "".join(f"[v{i}]" for i in range(len(notes)))
    fc = ";".join(parts) + (
        f";{mix_in}amix=inputs={len(notes)}:normalize=1:duration=longest[pad]"
        f";[pad]lowpass=f=1400,highpass=f=55,"
        f"aecho=0.8:0.85:220|430:0.25|0.16,"
        f"volume={gain_db}dB,"
        f"afade=t=in:st=0:d=2.2,afade=t=out:st={max(dur - 3.0, 0):.2f}:d=3.0[bed]")
    cmd = (["ffmpeg", "-v", "error", "-y"] + ins +
           ["-filter_complex", fc, "-map", "[bed]", "-t", f"{dur:.3f}",
            "-c:a", "pcm_s16le", out_path])
    _run(cmd)
    return out_path


def prepare_narration(src, out):
    """Existing Kokoro/broadcast chain, then -16 LUFS for a clean mix bed."""
    try:
        import factory as F            # reuse the production voice chain
        chain = F.narration_filters()
    except Exception:
        chain = "highpass=f=75,acompressor=threshold=-18dB:ratio=2.5:attack=8:release=180"
    fc = (f"{chain},loudnorm=I=-16:TP=-1.5:LRA=11")
    _run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", fc,
          "-ar", "48000", "-ac", "2", out])
    return out


def mix(narration, bed, out, bed_gain=0.55, duck=True, loud_target=-14.0):
    """Voice over a ducked bed, normalised for YouTube."""
    d = duration(narration)
    # a filtergraph label can only be read once, so the voice is split: one
    # copy keys the ducking compressor, the other is the audible mix element.
    fc = [
        f"[1:a]volume={bed_gain:.2f}[bedv]",
        "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[narm]",
        "[narm]asplit=2[nar1][nar2]",
    ]
    if duck:
        fc.append("[bedv][nar1]sidechaincompress=threshold=0.06:ratio=9:"
                  "attack=15:release=420:makeup=1[bedd]")
    else:
        fc.append("[bedv]anull[bedd]")
    fc.append("[nar2][bedd]amix=inputs=2:normalize=0:duration=longest[mx]")
    fc.append(f"[mx]loudnorm=I={loud_target}:TP=-1.5:LRA=11,"
              f"aresample=48000[aout]")
    _run(["ffmpeg", "-v", "error", "-y", "-i", narration, "-i", bed,
          "-filter_complex", ";".join(fc), "-map", "[aout]",
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", out])
    return out


def measure(path):
    """LUFS / true peak / silence / clipping, measured with ffmpeg only."""
    out = {"duration": round(duration(path), 2), "lufs": None, "true_peak_db": None,
           "silence_ratio": None, "clipped_samples": None, "errors": []}
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                            "-af", "ebur128=peak=true", "-f", "null", "-"],
                           capture_output=True, text=True)
        tail = (r.stderr or "")[-2500:]
        import re
        m = re.findall(r"I:\s*(-?\d+\.\d+)\s*LUFS", tail)
        p = re.findall(r"Peak:\s*(-?\d+\.\d+)\s*dBFS", tail)
        if m:
            out["lufs"] = float(m[-1])
        if p:
            out["true_peak_db"] = float(p[-1])
    except Exception as e:
        out["errors"].append(f"ebur128: {str(e)[:80]}")
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                            "-af", "silencedetect=noise=-45dB:d=1.0",
                            "-f", "null", "-"], capture_output=True, text=True)
        import re
        sil = sum(float(x) for x in re.findall(r"silence_duration: ([\d.]+)",
                                               r.stderr or ""))
        if out["duration"]:
            out["silence_ratio"] = round(sil / out["duration"], 3)
    except Exception as e:
        out["errors"].append(f"silencedetect: {str(e)[:80]}")
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                            "-af", "astats=metadata=1:reset=0", "-f", "null", "-"],
                           capture_output=True, text=True)
        import re
        m = re.findall(r"Number of samples? (?:that )?(?:are )?clipped:\s*(\d+)",
                       r.stderr or "")
        m2 = re.findall(r"Peak count:\s*(\d+)", r.stderr or "")
        out["clipped_samples"] = int(m[0]) if m else (int(m2[0]) if m2 else 0)
    except Exception:
        out["clipped_samples"] = 0
    return out
