"""Next AI Vision 4 - multi-source footage harness (TEST MODE).

Renders a 60-90 second film through the cinematic editor with
ENABLE_MULTI_SOURCE_FOOTAGE=true, using only free providers (Pixabay, NASA,
Pexels when a key exists, Mixkit curated). It never uploads, never touches
YouTube credentials and never changes a production flag: the workflow that runs
it sets the flags for its own job only, and the production value stays false.

Outputs (all under --workdir):
  providers.json            provider availability + flags at run time
  multi_asset_manifest.json every accepted clip with licence provenance
  license_report.json       validation verdict per asset + rejects
  attribution.txt           credits block for the video description
  multisource_sample.mp4    the film
  selftest_summary.json     counts the final report quotes
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "factory"))

# ~185 words -> ~72 s at 150 wpm: inside the 60-90 s band the brief asks for.
STORY = (
    "Three companies just changed what a machine can do on its own. "
    "It started above us, on the space station, where a new sensor watched a storm "
    "build over the Pacific and warned the ground ninety minutes before landfall. "
    "That warning was not written by a person. It was assembled by a model reading "
    "satellite data in orbit, and it was right. "
    "Down here, the same trick is being pointed at the power grid. Engineers fed two "
    "years of failures into a small model, and it found the transformer that would "
    "break next week, months before the crew would have opened that cabinet. "
    "In a warehouse outside Osaka, a humanoid robot picked a box off a moving belt, "
    "turned it, and set it down without a single camera watching the hand. "
    "No markers, no rails, just touch. "
    "And on a laptop in Lagos, a developer shipped a product with a tool that writes "
    "code, tests it, and fixes what it broke before anyone wakes up. "
    "None of this needed a data center the size of a city. That is the part nobody "
    "is ready for: the machines got useful before they got expensive. "
    "So here is the question for tonight. When the warning, the repair, and the "
    "product all arrive without a human in the loop, what exactly is left for us to "
    "decide?"
)

BEATS = [
    ("Three companies just changed what a machine can do on its own.",
     "glowing world map network"),
    ("It started above us, on the space station, where a new sensor watched a storm "
     "build over the Pacific and warned the ground ninety minutes before landfall.",
     "earth from space station"),
    ("That warning was not written by a person. It was assembled by a model reading "
     "satellite data in orbit, and it was right.",
     "satellite orbiting earth"),
    ("Down here, the same trick is being pointed at the power grid.",
     "electrical power lines sunset"),
    ("Engineers fed two years of failures into a small model, and it found the "
     "transformer that would break next week, months before the crew would have "
     "opened that cabinet.",
     "electrical engineer control room"),
    ("In a warehouse outside Osaka, a humanoid robot picked a box off a moving belt, "
     "turned it, and set it down without a single camera watching the hand.",
     "robot arm factory automation"),
    ("No markers, no rails, just touch.",
     "robot hand close up"),
    ("And on a laptop in Lagos, a developer shipped a product with a tool that "
     "writes code, tests it, and fixes what it broke before anyone wakes up.",
     "developer coding laptop night"),
    ("None of this needed a data center the size of a city. That is the part nobody "
     "is ready for: the machines got useful before they got expensive.",
     "server room datacenter"),
    ("So here is the question for tonight. When the warning, the repair, and the "
     "product all arrive without a human in the loop, what exactly is left for us "
     "to decide?",
     "silhouette looking at city night"),
]


def log(msg):
    print(msg, flush=True)


def make_narration(text, out):
    """edge-tts when available (the production voice family), espeak-ng otherwise."""
    ok = False
    try:
        import asyncio
        import edge_tts

        async def go():
            c = edge_tts.Communicate(text, "en-US-AriaNeural")
            await c.save(out)

        asyncio.run(go())
        ok = os.path.exists(out) and os.path.getsize(out) > 20000
        log(f"  narration: edge-tts ok ({os.path.getsize(out)} bytes)")
    except Exception as ex:
        log(f"  narration: edge-tts unavailable -> {str(ex)[:110]}")
    if not ok:
        wav = out + ".wav"
        subprocess.run(["espeak-ng", "-v", "en-us", "-s", "150", "-w", wav, text],
                       check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a",
                        "libmp3lame", "-b:a", "192k", out], check=True)
        log(f"  narration: espeak-ng fallback ok ({os.path.getsize(out)} bytes)")
    return out



PROBE_QUERIES = {
    "pixabay": "server room technology",
    "pexels": "data center servers",
    "nasa": "earth from space",
    "mixkit": "office desk",
}


def probe_providers(wd, status, do_download=True):
    """Per-provider integration check: authentication, normalisation, licence,
    and (for auto-download providers) one real download verified with ffprobe."""
    from cine.providers import rebuild_provider
    from cine import licensing as LIC, visual_match as VM

    out = []
    for p in status["providers"]:
        name = p["provider"]
        row = {"provider": name, "available": p["available"],
               "reason": p.get("reason", ""), "license": p.get("license", ""),
               "query": PROBE_QUERIES.get(name, "technology"),
               "candidates": 0, "top": None, "download": None,
               "license_verdict": None}
        if not p["available"]:
            out.append(row)
            continue
        prov = rebuild_provider(name)
        cands = prov.search(row["query"], limit=6) if prov else []
        row["candidates"] = len(cands)
        if cands:
            c = cands[0]
            v = LIC.validate(c)
            row["top"] = {"asset_id": c.asset_id, "title": (c.title or "")[:70],
                          "creator": c.creator, "width": c.width, "height": c.height,
                          "duration": round(float(c.duration or 0), 1),
                          "page": c.page_url}
            row["license_verdict"] = {"ok": v["ok"], "reason": v["reason"],
                                      "commercial": v.get("commercial"),
                                      "attribution_required": v.get("attribution_required")}
            if do_download and prov.auto_download:
                dest = os.path.join(wd, f"probe_{name}.mp4")
                ok = prov.download(c, dest)
                pr = VM.probe(dest) if ok else None
                row["download"] = {"ok": bool(ok and pr),
                                   "bytes": os.path.getsize(dest) if os.path.exists(dest) else 0,
                                   "probe": pr}
                if os.path.exists(dest):
                    try:
                        os.remove(dest)
                    except OSError:
                        pass
        out.append(row)
    json.dump(out, open(os.path.join(wd, "provider_probe.json"), "w"), indent=1)
    for r in out:
        log(f"  probe {r['provider']:8s} avail={r['available']} cands={r['candidates']}"
            f" dl={ (r['download'] or {}).get('ok') } lic={ (r['license_verdict'] or {}).get('ok') }")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="cine_out_multisource")
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--max-seconds", type=float, default=95.0)
    ap.add_argument("--skip-probe", action="store_true")
    ap.add_argument("--skip-probe-download", action="store_true")
    args = ap.parse_args(argv)

    wd = os.path.abspath(args.workdir)
    os.makedirs(wd, exist_ok=True)
    t0 = time.time()

    # 1) provider inventory -------------------------------------------------
    from cine.providers import provider_status
    from cine import licensing as LIC

    status = provider_status(log=log)
    json.dump(status, open(os.path.join(wd, "providers.json"), "w"), indent=1)
    log("providers:")
    for p in status["providers"]:
        state = "READY" if p["available"] else "SKIPPED"
        log(f"  {state:8s} {p['provider']:8s} {p['reason'] or p['license']}")

    # 1b) per-provider integration probe -----------------------------------
    if not args.skip_probe:
        probe_providers(wd, status, do_download=not args.skip_probe_download)

    # 2) narration ----------------------------------------------------------
    nar = make_narration(STORY, os.path.join(wd, "narration.mp3"))

    # 3) render through the cinematic editor with the multi-source matcher ---
    from cine import editor as ED

    entry = {
        "id": "multisource_selftest_2026_11_02",
        "title": "The Machines Got Useful Before They Got Expensive",
        "kind": "long",
        "narration": STORY,
        "beats": [{"t": t, "kw": kw} for t, kw in BEATS],
        "content_pillar": "ai_updates",
    }
    log("rendering with ENABLE_MULTI_SOURCE_FOOTAGE="
        + os.environ.get("ENABLE_MULTI_SOURCE_FOOTAGE", "(unset)"))
    rep = ED.build(entry, wd, narration_path=nar, W=args.width, H=args.height,
                   fps=args.fps, force=True, log=log)
    out = rep["output"]
    sample = os.path.join(wd, "multisource_sample.mp4")
    try:
        import shutil
        shutil.copyfile(out, sample)
    except Exception as ex:
        log(f"  sample copy failed: {str(ex)[:100]}")
        sample = out
    dur = float((rep.get("qc") or {}).get("duration_s")
                or (rep.get("stages", {}).get("audio", {}).get("duration") or 0))

    # 4) licence + attribution artefacts ------------------------------------
    assets = rep.get("assets") or []
    provenance = []
    try:
        from cine import multi_source as MS
        provenance = (MS.load_manifest(MS.MANIFEST_PATH).get("assets") or [])
    except Exception as ex:
        log(f"  manifest read failed: {str(ex)[:100]}")
    by_id = {a.get("asset_id"): a for a in provenance if a.get("asset_id")}
    rows = []
    for a in assets:
        src = a.get("source") or ""
        if src in ("generated", "", None):
            continue
        merged = dict(by_id.get(a.get("asset_id")) or {})
        merged.update({k: v for k, v in a.items() if v not in (None, "")})
        rows.append(merged)
    checks = []
    for a in rows:
        v = LIC.validate(type("C", (), {
            "provider": a.get("provider", ""),
            "asset_id": a.get("asset_id", ""),
            "license_name": a.get("license", ""),
            "commercial_ok": a.get("commercial_ok", True),
            "extra": a.get("extra") or {},
        })())
        checks.append({"scene_id": a.get("scene_id"), "provider": a.get("provider"),
                       "asset_id": a.get("asset_id"), "license": a.get("license"),
                       "ok": v["ok"], "reason": v["reason"],
                       "commercial": v.get("commercial", False),
                       "attribution_required": v.get("attribution_required", False)})
    report = {"assets": len(rows), "validated": sum(1 for c in checks if c["ok"]),
              "rejected": [c for c in checks if not c["ok"]], "checks": checks}
    json.dump(report, open(os.path.join(wd, "license_report.json"), "w"), indent=1)
    attribution = LIC.attribution_report(rows, entry["title"])
    open(os.path.join(wd, "attribution.txt"), "w").write(attribution)

    manifest_path = os.path.join(ROOT, "factory", "footage",
                                 "multi_asset_manifest.json")
    if os.path.exists(manifest_path):
        with open(os.path.join(wd, "multi_asset_manifest.json"), "w") as fh:
            fh.write(open(manifest_path).read())

    matcher = {}
    try:
        from cine import multi_source as MS
        matcher = MS.last_stats() or {}
    except Exception:
        pass
    summary = {
        "output": sample,
        "render_output": out,
        "duration_s": round(dur, 2),
        "inside_target_band": 60.0 <= dur <= args.max_seconds,
        "scenes": len(assets),
        "clips_by_provider": {p: sum(1 for a in rows if a.get("provider") == p)
                              for p in sorted({a.get("provider") for a in rows if a.get("provider")})},
        "fallback_cards": (rep.get("stages", {}).get("visuals", {})
                           .get("generated_cards", 0)),
        "distinct_sources": (rep.get("stages", {}).get("visuals", {})
                             .get("distinct_sources", 0)),
        "licence_checks": {"assets": report["assets"],
                           "validated": report["validated"],
                           "rejected": len(report["rejected"])},
        "qc": (rep.get("qc") or {}).get("score"),
        "wall_seconds": round(time.time() - t0, 1),
        "provider_searches": (matcher or {}).get("per_provider") or {},
        "provider_errors": [{"provider": p["provider"], "errors": p.get("errors")}
                            for p in status["providers"] if p.get("errors")],
    }
    if matcher:
        summary["duplicates_rejected"] = matcher.get("duplicates_rejected", 0)
        summary["rejects_sample"] = (matcher.get("rejects") or [])[:12]
    json.dump(summary, open(os.path.join(wd, "selftest_summary.json"), "w"), indent=1)
    log("SUMMARY " + json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
