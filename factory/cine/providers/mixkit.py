"""Mixkit - manual / curated source, deliberately NOT automated.

Mixkit has no public API and its terms do not invite automated bulk retrieval,
so this provider never searches or scrapes the site. It only serves entries that
the owner (or an editor) has added by hand to

    factory/footage/mixkit_curated.json

with a verified licence. An entry is only usable when it says
``"license_reviewed": true`` and names the Mixkit Stock Video Free License; every
other entry is skipped and reported, so an un-vetted row in that file can never
slip into a commercial video.

File shape (all fields optional except id/download_url/license_reviewed)::

    {"assets": [{
        "id": "mixkit-1234",
        "title": "Circuit board macro",
        "download_url": "https://assets.mixkit.co/videos/preview/mixkit-....mp4",
        "page_url": "https://mixkit.co/free-stock-video/...",
        "creator": "Mixkit",
        "license": "Mixkit Stock Video Free License",
        "license_reviewed": true,
        "width": 1920, "height": 1080, "duration": 12.4,
        "tags": "circuit board macro electronics"
    }]}
"""
from __future__ import annotations

import json
import os
from typing import List

from .base import ClipCandidate, FACTORY, FootageProvider, clean_query

CURATED = os.path.join(FACTORY, "footage", "mixkit_curated.json")
LICENSE = "Mixkit Stock Video Free License"
LICENSE_URL = "https://mixkit.co/license/#videoFree"


class MixkitManualProvider(FootageProvider):
    name = "mixkit"
    display = "Mixkit (manual, curated)"
    requires_key = None
    per_minute = 6
    min_interval = 1.0
    license_name = LICENSE
    license_url = LICENSE_URL

    def __init__(self, log=None):
        super().__init__(log=log)
        self.skipped: List[str] = []

    def _load(self) -> List[dict]:
        try:
            doc = json.load(open(CURATED))
        except Exception:
            return []
        rows = doc.get("assets") if isinstance(doc, dict) else doc
        out = []
        for r in rows or []:
            rid = str(r.get("id") or "")
            reviewed = r.get("license_reviewed") is True
            lic = str(r.get("license") or "")
            if not rid or not r.get("download_url"):
                continue
            if not reviewed or lic != LICENSE:
                # never serve an asset whose licence a human has not confirmed
                self.skipped.append(f"{rid}: licence not verified")
                continue
            out.append(r)
        return out

    def unavailable_reason(self):
        if not os.path.exists(CURATED):
            return "no curated list (manual source, no automated API)"
        if not self._load():
            return "curated list empty or unverified"
        return None

    def status(self):
        s = super().status()
        s["skipped"] = self.skipped[:5]
        s["mode"] = "manual-curated"
        return s

    def _search(self, query: str, limit: int) -> List[ClipCandidate]:
        words = set(clean_query(query).lower().split())
        out: List[ClipCandidate] = []
        for r in self._load():
            tags = str(r.get("tags") or "").lower()
            score = sum(1 for w in words if len(w) > 2 and w in tags)
            if words and score == 0:
                continue
            out.append(ClipCandidate(
                provider=self.name,
                asset_id=str(r["id"]),
                download_url=r["download_url"],
                title=str(r.get("title") or "")[:120],
                page_url=str(r.get("page_url") or ""),
                creator=str(r.get("creator") or "Mixkit"),
                license_name=LICENSE,
                license_url=LICENSE_URL,
                commercial_ok=True,
                attribution_required=False,
                width=int(r.get("width") or 0),
                height=int(r.get("height") or 0),
                duration=float(r.get("duration") or 0),
                tags=tags,
                extra={"score": score, "curated": True},
            ))
        out.sort(key=lambda c: -int(c.extra.get("score", 0)))
        return out[:limit]
