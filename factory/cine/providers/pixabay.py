"""Pixabay video API provider.

Licence: Pixabay Content Licence - free for commercial use, no attribution
required, modification allowed (do not resell unmodified clips). We still record
the page URL and author so an attribution block can be produced on request.

Terms we honour here:
  * documented key-based API only, no scraping;
  * results are cached per query (SearchCache) so repeated renders never repeat
    requests - Pixabay explicitly asks that the API is not queried in mass;
  * paced with a hard ceiling below the documented 100 requests/minute.
"""
from __future__ import annotations

from typing import List

from .base import ClipCandidate, FootageProvider, http_json, secret

API = "https://pixabay.com/api/videos/"


class PixabayProvider(FootageProvider):
    name = "pixabay"
    display = "Pixabay"
    requires_key = "PIXABAY_API_KEY"
    per_minute = 90          # documented ceiling is 100/min
    min_interval = 0.7
    license_name = "Pixabay Content License"
    license_url = "https://pixabay.com/service/license-summary/"

    def _search(self, query: str, limit: int) -> List[ClipCandidate]:
        doc = http_json(self.name, API, params={
            "key": secret("PIXABAY_API_KEY"),
            "q": query,
            "video_type": "film",      # real footage only, no 3D renders
            "safesearch": "true",
            "order": "popular",
            "per_page": max(3, min(int(limit), 50)),
        }, limiter=self.limiter, log=self.log)

        out: List[ClipCandidate] = []
        for h in doc.get("hits", []):
            vids = h.get("videos") or {}
            # prefer the largest rendition that is not a 4K giant we cannot use
            best = (vids.get("large") or vids.get("medium") or
                    vids.get("small") or vids.get("tiny") or {})
            if not best.get("url"):
                continue
            out.append(ClipCandidate(
                provider=self.name,
                asset_id=str(h.get("id")),
                download_url=best["url"],
                title=(h.get("tags") or "").strip()[:120],
                page_url=h.get("pageURL", ""),
                creator=h.get("user", ""),
                license_name=self.license_name,
                license_url=self.license_url,
                commercial_ok=True,
                attribution_required=False,
                width=int(best.get("width") or 0),
                height=int(best.get("height") or 0),
                duration=float(h.get("duration") or best.get("duration") or 0),
                tags=h.get("tags", ""),
                thumbnail=(vids.get("medium") or best).get("thumbnail", ""),
                extra={"views": h.get("views"), "downloads": h.get("downloads")},
            ))
        return out
