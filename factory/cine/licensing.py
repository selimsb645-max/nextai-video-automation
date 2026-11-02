"""Phase 5 - licence validation and attribution.

A free download is not a commercial licence. Every candidate is checked against
an explicit rule table; an unknown licence, a flagged third-party claim or an
unreviewed manual entry is REJECTED rather than assumed usable.

The same module writes the per-video attribution block that belongs in the
YouTube description, and it never invents a creator or a licence it was not told.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional

# licence_name -> rule. "attribution" is a courtesy requirement we honour even
# when the provider says it is optional.
RULES: Dict[str, Dict[str, Any]] = {
    "Pixabay Content License": {
        "commercial": True, "attribution_required": False,
        "url": "https://pixabay.com/service/license-summary/",
        "note": "Free for commercial use, no attribution required; do not resell "
                "unmodified clips and do not redistribute as stock.",
    },
    "Pexels License": {
        "commercial": True, "attribution_required": False,
        "url": "https://www.pexels.com/license/",
        "note": "Free to use, including commercially; no attribution required; "
                "do not sell unmodified copies or imply endorsement.",
    },
    "NASA Media Usage Guidelines (public domain, no endorsement)": {
        "commercial": True, "attribution_required": True,
        "url": "https://www.nasa.gov/nasa-brand-center/images-and-media/",
        "note": "Generally not copyrighted and usable commercially; NASA must not "
                "appear to endorse the channel. Items with third-party rights are "
                "excluded by the provider.",
    },
    "Mixkit Stock Video Free License": {
        "commercial": True, "attribution_required": False,
        "url": "https://mixkit.co/license/#videoFree",
        "note": "Free for commercial projects; do not redistribute the raw clip "
                "as stock or in a competing stock library.",
    },
    "Public Domain": {
        "commercial": True, "attribution_required": False,
        "url": "", "note": "No copyright restrictions; commercial reuse allowed.",
    },
    "original (generated locally)": {
        "commercial": True, "attribution_required": False,
        "url": "", "note": "Rendered by this pipeline; no third-party rights.",
    },
}


# The same licence is spelled several ways (providers add qualifiers), so match
# on a normalised prefix instead of requiring an exact table key.
ALIASES = {
    "pixabay content licence": "Pixabay Content License",
    "pixabay content license": "Pixabay Content License",
    "pexels licence": "Pexels License",
    "pexels license": "Pexels License",
    "nasa media usage guidelines": "NASA Media Usage Guidelines (public domain, no endorsement)",
    "nasa media usage guidelines (public domain, no endorsement)":
        "NASA Media Usage Guidelines (public domain, no endorsement)",
    "mixkit stock video free licence": "Mixkit Stock Video Free License",
    "mixkit stock video free license": "Mixkit Stock Video Free License",
    "public domain": "Public Domain",
}


def canonical(license_name: str) -> str:
    key = (license_name or "").strip().lower()
    if key in ALIASES:
        return ALIASES[key]
    for alias, real in ALIASES.items():                 # tolerate suffixes
        if key.startswith(alias):
            return real
    return ""


def rule_for(license_name: str) -> Optional[Dict[str, Any]]:
    return RULES.get((license_name or "").strip())


def validate(cand) -> Dict[str, Any]:
    """Return {ok, reason, commercial, attribution_required, record}.

    ``cand`` is a ClipCandidate. Rejection reasons are specific so the test
    report can say why a source was refused."""
    lic = (getattr(cand, "license_name", "") or "").strip()
    rule = rule_for(canonical(lic) or lic)
    out: Dict[str, Any] = {
        "provider": getattr(cand, "provider", ""),
        "asset_id": getattr(cand, "asset_id", ""),
        "license": lic,
        "commercial": False,
        "attribution_required": False,
        "ok": False,
        "reason": "",
    }
    if not rule:
        out["reason"] = f"unknown licence: {lic or '(empty)'}"
        return out
    if not rule["commercial"]:
        out["reason"] = "licence not cleared for commercial use"
        return out
    # provider-level veto (NASA third-party rights, unverified manual entry...)
    extra = getattr(cand, "extra", {}) or {}
    if extra.get("third_party_rights"):
        out["reason"] = "third-party rights flagged by provider"
        return out
    if not getattr(cand, "commercial_ok", False):
        out["reason"] = "provider reports no commercial clearance"
        return out
    if extra.get("curated") and extra.get("license_reviewed") is False:
        out["reason"] = "manual entry not licence-reviewed"
        return out
    out.update({
        "ok": True,
        "commercial": True,
        "attribution_required": bool(rule["attribution_required"]
                                     or getattr(cand, "attribution_required", False)),
        "license_url": rule["url"],
        "note": rule["note"],
    })
    return out


def asset_record(cand, path: str, probe: Optional[tuple], sha256: str,
                 scene_id: Optional[int] = None) -> Dict[str, Any]:
    """The manifest row for one downloaded asset. No secret, no fake field."""
    dur, w, h = (probe if probe else (0.0, 0, 0))
    v = validate(cand)
    return {
        "scene_id": scene_id,
        "provider": cand.provider,
        "asset_id": cand.asset_id,
        "title": cand.title,
        "creator": cand.creator,
        "source_page": cand.page_url,
        "download_url": cand.download_url,
        "license": cand.license_name,
        "license_url": v.get("license_url") or cand.license_url,
        "license_note": v.get("note", ""),
        "commercial_ok": bool(v["ok"]),
        "attribution_required": bool(v["attribution_required"]),
        "downloaded_at": _now(),
        "sha256": sha256,
        "path": path,
        "file_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
        "duration_s": round(float(dur), 3),
        "width": int(w), "height": int(h),
        "attribution": cand.attribution_line(),
    }


def _now() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def attribution_report(assets: Iterable[Dict[str, Any]], title: str = "") -> str:
    """Human-readable credits block for the video description.

    One line per distinct asset, in scene order. Sources whose licence needs a
    credit are marked; every source is listed because crediting costs nothing.
    """
    rows: List[Dict[str, Any]] = [a for a in assets
                                  if a and a.get("provider")
                                  and a.get("license") != "original (generated locally)"]
    seen, uniq = set(), []
    for a in rows:
        k = f"{a.get('provider')}:{a.get('asset_id')}"
        if k in seen:
            continue
        seen.add(k)
        uniq.append(a)
    lines = [f"Footage credits{f' - {title}' if title else ''}", ""]
    if not uniq:
        lines.append("No third-party footage used (all visuals generated locally).")
        return "\n".join(lines) + "\n"
    for a in uniq:
        bits = [a.get("title") or a.get("asset_id", "")]
        if a.get("creator"):
            bits.append(a["creator"])
        bits.append(a.get("provider", ""))
        bits.append(a.get("license", ""))
        page = a.get("source_page") or a.get("page_url")
        if page:
            bits.append(page)
        star = " *" if a.get("attribution_required") else ""
        lines.append("- " + " | ".join(str(b) for b in bits if b) + star)
    lines += ["", "* = credit requested by the source's licence terms.",
              "All clips are used under the licences above; no clip is resold or "
              "redistributed as stock footage."]
    return "\n".join(lines) + "\n"


def write_attribution(path: str, assets: Iterable[Dict[str, Any]], title: str = "") -> str:
    txt = attribution_report(assets, title)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(txt)
    return txt


def validation_summary(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    ok = [r for r in rows if r.get("ok")]
    bad = [r for r in rows if not r.get("ok")]
    by_reason: Dict[str, int] = {}
    for r in bad:
        by_reason[r.get("reason") or "unknown"] = by_reason.get(r.get("reason") or "unknown", 0) + 1
    return {"checked": len(rows), "accepted": len(ok), "rejected": len(bad),
            "rejected_by_reason": by_reason,
            "licenses": sorted({r.get("license") for r in ok if r.get("license")})}
