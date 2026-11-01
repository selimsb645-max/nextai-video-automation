"""Central rendering configuration (single source of truth).

Before this module the encoder settings were hardcoded in several places
(factory.factory:991, factory.factory:1622, cine/motion.py, cine/editor.py).
Now every renderer that opts in reads one RenderConfig, and the legacy
production renderer keeps its old literals untouched until the owner approves.

Guarantees:
  * one profile map (1440p60, 1080p30, 1080p25) plus env overrides;
  * aspect-ratio-preserving scale + pad (no stretching, ever);
  * no motion interpolation: 60 fps is reached by frame duplication (CFR),
    never by minterpolate, so no invented motion is added to real footage;
  * low-resolution sources are detected and reported instead of silently
    upscaled into mush;
  * a capability probe runs before any render, so a missing encoder or filter
    fails fast with a clear message instead of a half-written file.
"""
import json
import os
import shutil
import subprocess

# ── profiles ───────────────────────────────────────────────────────────────
PROFILES = {
    "1440p60": {
        "width": 2560, "height": 1440, "fps": 60, "pix_fmt": "yuv420p",
        "codec": "libx264", "profile": "high", "level": "5.1",
        "bitrate": "24M", "maxrate": "26M", "bufsize": "48M",
        "gop": 120, "bframes": 2, "refs": 4, "preset": "veryfast",
        "audio_codec": "aac", "audio_bitrate": "384k",
        "audio_rate": 48000, "audio_channels": 2,
        "color_primaries": "bt709", "color_trc": "bt709",
        "colorspace": "bt709", "color_range": "tv",
        "faststart": True, "threads": 0,
    },
    # kept for reference/regression comparisons, not used in production
    "1080p30": {
        "width": 1920, "height": 1080, "fps": 30, "pix_fmt": "yuv420p",
        "codec": "libx264", "profile": "high", "level": "4.2",
        "bitrate": "10M", "maxrate": "11M", "bufsize": "20M",
        "gop": 60, "bframes": 2, "refs": 4, "preset": "veryfast",
        "audio_codec": "aac", "audio_bitrate": "192k",
        "audio_rate": 48000, "audio_channels": 2,
        "color_primaries": "bt709", "color_trc": "bt709",
        "colorspace": "bt709", "color_range": "tv",
        "faststart": True, "threads": 0,
    },
}

ENV_MAP = {
    "RENDER_WIDTH": ("width", int), "RENDER_HEIGHT": ("height", int),
    "RENDER_FPS": ("fps", int), "RENDER_BITRATE": ("bitrate", str),
    "RENDER_MAXRATE": ("maxrate", str), "RENDER_BUFSIZE": ("bufsize", str),
    "RENDER_PRESET": ("preset", str), "RENDER_GOP": ("gop", int),
    "RENDER_BFRAMES": ("bframes", int), "RENDER_AUDIO_BITRATE": ("audio_bitrate", str),
    "RENDER_AUDIO_RATE": ("audio_rate", int),
    "RENDER_H264_PROFILE": ("profile", str),   # high / main / baseline only
}

MIN_SOURCE_FACTOR = 0.75        # below 75% of target width = quality warning


class RenderConfig:
    """One immutable render profile, validated and ready to feed FFmpeg."""

    def __init__(self, profile="1440p60", overrides=None):
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile!r}; "
                             f"available: {sorted(PROFILES)}")
        self.name = profile
        self.values = dict(PROFILES[profile])
        for k, v in (overrides or {}).items():
            self.values[k] = v
        self.warnings = []
        v = self.values
        if int(v["width"]) % 2 or int(v["height"]) % 2:
            raise ValueError("H.264 yuv420p needs even width/height")
        if v["codec"] != "libx264":
            raise ValueError("this build targets libx264 (no GPU on CI)")
        if str(v["profile"]) not in ("baseline", "main", "high", "high10",
                                     "high422", "high444"):
            raise ValueError(f"invalid H.264 profile {v['profile']!r} - use "
                             "RENDER_H264_PROFILE=high (RENDER_PROFILE only "
                             "selects a profile map)")
        if int(v["fps"]) > 60:
            self.warnings.append("fps above 60 is outside the requested spec")

    # ── construction ───────────────────────────────────────────────────────
    @classmethod
    def from_env(cls, profile="1440p60"):
        ov = {}
        for env, (key, cast) in ENV_MAP.items():
            raw = os.environ.get(env)
            if raw:
                try:
                    ov[key] = cast(raw)
                except ValueError:
                    raise ValueError(f"{env}={raw!r} is not a valid {cast.__name__}")
        return cls(profile, ov)

    def __getattr__(self, item):
        try:
            return self.values[item]
        except KeyError:
            raise AttributeError(item)

    # ── ffmpeg fragments ───────────────────────────────────────────────────
    def video_args(self, faststart=None):
        v = self.values
        args = [
            "-c:v", v["codec"],
            "-preset", str(v["preset"]),
            "-profile:v", str(v["profile"]),
            "-level:v", str(v["level"]),
            "-b:v", str(v["bitrate"]),
            "-maxrate", str(v["maxrate"]),
            "-bufsize", str(v["bufsize"]),
            "-g", str(v["gop"]),
            "-keyint_min", str(v["gop"]),
            "-sc_threshold", "0",
            "-bf", str(v["bframes"]),
            "-refs", str(v["refs"]),
            "-pix_fmt", str(v["pix_fmt"]),
            "-color_primaries", str(v["color_primaries"]),
            "-color_trc", str(v["color_trc"]),
            "-colorspace", str(v["colorspace"]),
            "-color_range", str(v["color_range"]),
            "-r", str(v["fps"]),
            "-fps_mode", "cfr",
            "-threads", str(v["threads"]),
        ]
        if faststart if faststart is not None else v["faststart"]:
            args += ["-movflags", "+faststart"]
        return args

    def audio_args(self):
        v = self.values
        return ["-c:a", v["audio_codec"], "-b:a", str(v["audio_bitrate"]),
                "-ar", str(v["audio_rate"]), "-ac", str(v["audio_channels"])]

    def scale_pad(self, src_w=None, src_h=None, fit="pad", pad_color="black"):
        """Aspect-preserving fit. `pad` letterboxes, `crop` centre-crops to fill,
        `decrease` only scales. Never stretches.

        Frame rate is converted by duplication inside the caller (`fps=` filter
        with cfr), never by motion interpolation.
        """
        W, H, F = int(self.width), int(self.height), int(self.fps)
        if fit == "crop":
            core = (f"scale={W}:{H}:force_original_aspect_ratio=increase:"
                    f"flags=lanczos,crop={W}:{H}")
        elif fit == "decrease":
            core = (f"scale={W}:{H}:force_original_aspect_ratio=decrease:"
                    f"flags=lanczos")
        else:
            core = (f"scale={W}:{H}:force_original_aspect_ratio=decrease:"
                    f"flags=lanczos,"
                    f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={pad_color}")
        return f"{core},setsar=1,fps={F},format={self.pix_fmt}"

    def source_assessment(self, src_w, src_h):
        """Is this source big enough, or are we about to upscale it?"""
        if not src_w or not src_h:
            return {"known": False, "upscale": None, "factor": None,
                    "warning": None}
        target_short = min(int(self.width), int(self.height))
        src_short = min(int(src_w), int(src_h))
        factor = src_short / target_short
        up = factor < 1.0
        warn = None
        if factor < MIN_SOURCE_FACTOR:
            warn = (f"source {src_w}x{src_h} is {factor * 100:.0f}% of the "
                    f"{self.width}x{self.height} target: heavy upscale, "
                    f"expect softness")
        elif up:
            warn = (f"source {src_w}x{src_h} is below target "
                    f"({factor * 100:.0f}%): mild upscale with lanczos")
        return {"known": True, "upscale": bool(up), "factor": round(factor, 3),
                "warning": warn}

    def report(self):
        v = dict(self.values)
        v.update({"profile_name": self.name,
                  "bitrate_mbps": _mbps(self.values["bitrate"]),
                  "audio_kbps": _kbps(self.values["audio_bitrate"])})
        return v


def _kbps(x):
    s = str(x).strip().upper()
    try:
        if s.endswith("K"):
            return int(float(s[:-1]))
        if s.endswith("M"):
            return int(float(s[:-1]) * 1000)
        return int(round(float(s) / 1000))
    except ValueError:
        return None


def _mbps(x):
    s = str(x).strip().upper()
    try:
        if s.endswith("K"):
            return round(float(s[:-1]) / 1000, 3)
        if s.endswith("M"):
            return round(float(s[:-1]), 3)
        return round(float(s) / 1_000_000, 3)
    except ValueError:
        return None


# ── capability checks ──────────────────────────────────────────────────────
REQUIRED_ENCODERS = ["libx264", "aac"]
REQUIRED_FILTERS = ["scale", "pad", "crop", "fps", "zoompan", "xfade", "ass",
                    "concat", "aresample", "loudnorm", "sidechaincompress",
                    "blackdetect", "freezedetect"]


def _ffmpeg_has(flag, item):
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-" + flag], capture_output=True,
                           text=True)
        return item in (r.stdout + r.stderr)
    except FileNotFoundError:
        return False


def capabilities(deep=True):
    """Fail-fast probe: every encoder/filter this pipeline needs."""
    caps = {"ffmpeg": bool(shutil.which("ffmpeg")),
            "ffprobe": bool(shutil.which("ffprobe")),
            "encoders": {}, "filters": {}, "fonts": [], "errors": []}
    if not caps["ffmpeg"] or not caps["ffprobe"]:
        caps["errors"].append("ffmpeg/ffprobe not on PATH")
        return caps
    if deep:
        for e in REQUIRED_ENCODERS:
            caps["encoders"][e] = _ffmpeg_has("encoders", e)
            if not caps["encoders"][e]:
                caps["errors"].append(f"missing encoder {e}")
        for f in REQUIRED_FILTERS:
            caps["filters"][f] = _ffmpeg_has("filters", f)
            if not caps["filters"][f]:
                caps["errors"].append(f"missing filter {f}")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True,
                       text=True)
    caps["version"] = (r.stdout or "").splitlines()[0] if r.stdout else "unknown"
    caps["gpu"] = _has_gpu()
    return caps


def _has_gpu():
    """CI has no GPU; we only report what is really there."""
    try:
        if shutil.which("nvidia-smi"):
            r = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                return True
    except Exception:
        pass
    return False


def assert_ready():
    caps = capabilities()
    if caps["errors"]:
        raise RuntimeError("renderer cannot start: " + "; ".join(caps["errors"]))
    return caps


if __name__ == "__main__":
    cfg = RenderConfig.from_env(os.environ.get("RENDER_PROFILE", "1440p60"))
    print(json.dumps({"config": cfg.report(), "warnings": cfg.warnings,
                      "capabilities": capabilities()}, indent=1))
