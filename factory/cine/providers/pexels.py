"""Pexels video API provider.

Licence: Pexels Licence - free for commercial use, no attribution required.
Attribution is still recorded (author + page URL) because it costs nothing.

Gated twice: the ENABLE_PEXELS_PROVIDER flag and a present PEXELS_API_KEY. With
either missing the provider reports itself unavailable and the rest of the
pipeline carries on - a missing secret never blocks a workflow.

Quota: Pexels documents 200 requests/hour and 20k/month, so the pacer is set to
180/hour equivalent (3/minute) rather than anything aggressive.
"""
from __future__ import annotations

from typing import List

from .base import ClipCandidate, FootageProvider, env_flag, http_json, secret

API = "https://api.pexels.com/videos/search"


class PexelsProvider(FootageProvider):
    name = "pexels"
    display = "Pexels"
    requires_key = "PEXELS_API_KEY"
    per_minute = 3            # ~180/hour, under the documented 200/hour
    min_interval = 1.2
    license_name = "Pexels License"
    license_url = "https://www.pexels.com/license/"

    def unavailable_reason(self):
        if not env_flag("ENABLE_PEXELS_PROVIDER", False):
            return "ENABLE_PEXELS_PROVIDER=false"
        return super().unavailable_reason()

    def _search(self, query: str, limit: int) -> List[ClipCandidate]:
        doc = http_json(self.name, API, params={
            "query": query,
            "per_page": max(3, min(int(limit), 40)),
            "orientation": "landscape",
            "size": "medium",     # HD and up; avoids 4K giants
        }, headers={"Authorization": secret("PEXELS_API_KEY")},
            limiter=self.limiter, log=self.log)

        out: List[ClipCandidate] = []
        for v in doc.get("videos", []):
            files = [f for f in (v.get("video_files") or [])
                     if (f.get("file_type") or "").lower() == "video/mp4"
                     and f.get("link")]
            if not files:
                continue
            # best landscape rendition at or below UHD, largest first
            files.sort(key=lambda f: (int(f.get("width") or 0)), reverse=True)
            pick = None
            for f in files:
                w, h = int(f.get("width") or 0), int(f.get("height") or 0)
                if w and h and w >= h and w <= 3840:
                    pick = f
                    break
            pick = pick or files[0]
            user = v.get("user") or {}
            out.append(ClipCandidate(
                provider=self.name,
                asset_id=str(v.get("id")),
                download_url=pick["link"],
                title=(v.get("url") or "").rstrip("/").split("/")[-1].replace("-", " ")[:120],
                page_url=v.get("url", ""),
                creator=user.get("name", ""),
                license_name=self.license_name,
                license_url=self.license_url,
                commercial_ok=True,
                attribution_required=False,
                width=int(pick.get("width") or v.get("width") or 0),
                height=int(pick.get("height") or v.get("height") or 0),
                duration=float(v.get("duration") or 0),
                tags=query,
                thumbnail=v.get("image", ""),
                extra={"quality": pick.get("quality")},
            ))
        return out
