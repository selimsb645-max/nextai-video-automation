"""Bridge between the Python factory and the Remotion graphics layer.

Division of labour (owner's five-tool stack, 2026-11-21):

    Python   orchestration — this file, actions/runner.py
    Node.js  runtime that executes the Remotion CLI
    Remotion React components -> frames (intro, data cards, captions, outro)
    FFmpeg   assembly, concat, loudness, mux — the footage stays FFmpeg's job
    HyperFrames  optional HTML scene renderer; not wired in (see note at the bottom)

Why a separate module: runner.py already imports a lot, and rendering graphics must never
be able to break a video that would otherwise publish. Every function here fails soft and
returns None, so the caller keeps the existing render.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REMOTION_DIR = REPO / "remotion"
NODE_TIMEOUT = int(os.environ.get("REMOTION_TIMEOUT", "900"))


def _log(msg: str) -> None:
    print(f"[remotion] {msg}", flush=True)


def available() -> bool:
    """True only when Node and the Remotion project are both present."""
    if not (REMOTION_DIR / "package.json").exists():
        return False
    return shutil.which("npx") is not None


SETUP_TIMEOUT = int(os.environ.get("REMOTION_SETUP_TIMEOUT", "1200"))
_setup_state = {"done": False, "ok": False}


def _run_setup_cmd(cmd: list[str], timeout: int):
    try:
        return subprocess.run(cmd, cwd=str(REMOTION_DIR), capture_output=True,
                              text=True, timeout=timeout)
    except Exception as ex:
        _log(f"setup: {' '.join(cmd[:3])} could not run ({type(ex).__name__})")
        return None


def ensure_setup() -> bool:
    """Make the graphics layer runnable on a bare CI runner (2026-11-22).

    A fresh checkout has no node_modules, and the production workflow has no
    Node steps at all: GitHub's ubuntu image ships Node/npm, but not this
    project's dependencies or Remotion's headless browser. Until now that
    meant `npx remotion render` failed on every production run and the
    failure stayed invisible. The bridge therefore installs what it needs
    itself, once per process, and logs exactly what it did and why it gave
    up. Returns True when a render can be attempted.
    """
    if _setup_state["done"]:
        return _setup_state["ok"]
    _setup_state["done"] = True
    if not (REMOTION_DIR / "package.json").exists():
        _log("setup: remotion/package.json missing - graphics unavailable")
        return False
    if shutil.which("npm") is None or shutil.which("npx") is None:
        _log("setup: node/npm not on PATH - graphics unavailable here")
        return False
    if not (REMOTION_DIR / "node_modules").exists():
        _log("setup: node_modules missing - running npm ci (first run only)")
        proc = _run_setup_cmd(["npm", "ci", "--no-audit", "--no-fund"],
                              SETUP_TIMEOUT)
        if (proc is None or proc.returncode != 0
                or not (REMOTION_DIR / "node_modules").exists()):
            tail = ""
            if proc is not None:
                tail = " | ".join(
                    (proc.stderr or proc.stdout or "").strip()
                    .splitlines()[-3:])[:300]
            _log(f"setup: npm ci failed - graphics unavailable ({tail})")
            return False
        _log("setup: npm ci complete")
    proc = _run_setup_cmd(["npx", "remotion", "browser", "ensure"], 600)
    if proc is None or proc.returncode != 0:
        _log("setup: 'remotion browser ensure' did not complete - a render "
             "will still be attempted (the CLI can fetch the browser itself)")
    _setup_state["ok"] = True
    return True


def render(
    composition: str,
    out_path: str | Path,
    props: dict | None = None,
    timeout: int = NODE_TIMEOUT,
) -> Path | None:
    """Render one composition to an mp4. Returns the path, or None on any failure.

    props are passed as Remotion input props (--props), so the same component can carry
    today's headline/number without editing React code.
    """
    if not (REMOTION_DIR / "package.json").exists():
        _log("skipped: remotion/package.json not found")
        return None
    if shutil.which("npx") is None:
        _log("skipped: npx not on PATH (Node.js missing)")
        return None
    if not ensure_setup():
        return None

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "npx", "remotion", "render", "src/index.ts", composition, str(out),
        "--log=error",
    ]
    if props:
        # --props takes a file path or JSON string; a file avoids shell-quoting issues
        props_file = out.with_suffix(".props.json")
        props_file.write_text(json.dumps(props), encoding="utf-8")
        cmd += ["--props", str(props_file)]

    try:
        proc = subprocess.run(
            cmd, cwd=str(REMOTION_DIR), capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        _log(f"{composition}: render timed out after {timeout}s")
        return None
    except Exception as ex:                                  # pragma: no cover
        _log(f"{composition}: render failed to start ({type(ex).__name__})")
        return None

    if proc.returncode != 0 or not out.exists():
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-4:]
        _log(f"{composition}: exit {proc.returncode} — {' | '.join(tail)[:300]}")
        return None
    _log(f"{composition}: rendered {out.stat().st_size // 1024} KB -> {out.name}")
    return out


def concat(parts: list[Path], out_path: str | Path, reencode: bool = True) -> Path | None:
    """Join mp4s with FFmpeg.

    Re-encode by default: the graphics render and the factory render can differ in
    profile/level, and a stream copy across mismatched parameters produces a broken file
    that only shows up on playback.
    """
    parts = [p for p in parts if p and Path(p).exists()]
    if len(parts) < 2:
        _log(f"concat needs 2+ parts, got {len(parts)}")
        return None

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        for p in parts:
            fh.write(f"file '{Path(p).resolve()}'\n")
        listfile = fh.name

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile]
    if reencode:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
    else:
        cmd += ["-c", "copy"]
    cmd.append(str(out))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    finally:
        os.unlink(listfile)

    if proc.returncode != 0 or not out.exists():
        _log(f"concat failed: {(proc.stderr or '')[-200:]}")
        return None
    _log(f"concat: {len(parts)} parts -> {out.name} ({out.stat().st_size // 1024} KB)")
    return out


def add_intro_outro(
    main_video: str | Path,
    workdir: str | Path,
    headline: str = "",
    brand: str = "NEXTAI VISION",
) -> Path | None:
    """Wrap a finished long video in the branded intro and outro.

    Deliberately additive: if either graphic fails to render we return the ORIGINAL video
    path so the upload still happens. A missing intro is a cosmetic loss; a missing video
    is a lost day.
    """
    main = Path(main_video)
    if not main.exists():
        _log(f"main video missing: {main}")
        return None

    work = Path(workdir)
    intro = render("IntroCard", work / "intro.mp4", {"brand": brand, "headline": headline})
    outro = render("OutroCard", work / "outro.mp4", {"brand": brand})
    if not intro or not outro:
        _log("graphics unavailable — keeping the original cut")
        return main

    joined = concat([intro, main, outro], work / "final_with_graphics.mp4")
    return joined or main


# NOTE on HyperFrames (github.com/heygen-com/hyperframes, HeyGen, free/open-source):
# it renders HTML/CSS scenes to MP4 the same way Remotion renders React to MP4. Running both
# would mean two Node toolchains, two asset pipelines and two failure modes for the same
# frames. Remotion is already proven here (13.17s proof, 23.78s on a clean runner), so it
# stays the graphics engine. HyperFrames is worth a side-by-side test only if we want its
# Studio preview or HTML-authored scenes; that is an owner decision, not a default.
