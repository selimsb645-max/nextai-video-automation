"""NASA Images and Video Library provider (images-api.nasa.gov).

Licence: NASA Media Usage Guidelines - NASA content is generally not subject to
copyright and may be used commercially, provided NASA is not implied to endorse
the product. A minority of items carry third-party rights, so this provider
flags any record that mentions a copyright holder or a non-NASA
``secondary_creator`` as NOT commercially cleared. The licence layer
(cine/licensing.py) then rejects those instead of guessing.

Two documented endpoints are used, nothing is scraped:
  search  GET https://images-api.nasa.gov/search?media_type=video&q=...
  asset   GET https://images-api.nasa.gov/asset/<nasa_id>   (file manifest)

Resolution is not in the search payload, so candidates are ranked mostly on
text relevance and the real width/height are confirmed by ffprobe after
download - a candidate that turns out too small is simply rejected there.
"""
from __future__ import annotations

import urllib.parse
from typing import List

from .base import (ClipCandidate, FootageProvider, http_download, http_json,
                   redact)

SEARCH = "https://images-api.nasa.gov/search"
ASSET = "https://images-api.nasa.gov/asset/"
GUIDELINES = "https://www.nasa.gov/nasa-brand-center/images-and-media/"

# file renditions NASA publishes, best first
# "~orig" can be a multi-GB master; "~large" is the 1080p rendition and is
# what a 1080p/1440p timeline actually needs.
PREF = ("~large.mp4", "~medium.mp4", "~orig.mp4", "~small.mp4", "~mobile.mp4")


class NASAVideoProvider(FootageProvider):
    name = "nasa"
    display = "NASA Image & Video Library"
    requires_key = None            # public API, no key needed
    per_minute = 30
    min_interval = 1.0
    license_name = "NASA Media Usage Guidelines (public domain, no endorsement)"
    license_url = GUIDELINES

    def _search(self, query: str, limit: int) -> List[ClipCandidate]:
        doc = http_json(self.name, SEARCH, params={
            "q": query,
            "media_type": "video",
            "page_size": max(4, min(int(limit), 25)),
        }, limiter=self.limiter, log=self.log)

        items = (((doc.get("collection") or {}).get("items")) or [])[:max(1, min(limit, 10))]
        out: List[ClipCandidate] = []
        for it in items:
            data = (it.get("data") or [{}])[0]
            nasa_id = data.get("nasa_id") or ""
            if not nasa_id:
                continue
            try:
                renditions = self._renditions(nasa_id)
            except Exception as e:
                self.log(f"  nasa: asset manifest failed for {nasa_id}: "
                         f"{redact(str(e))[:90]}")
                continue
            if not renditions:
                continue
            url = renditions[0]
            title = (data.get("title") or nasa_id)[:120]
            desc = (data.get("description") or "")[:400]
            creator = data.get("secondary_creator") or data.get("center") or "NASA"
            # third-party rights are the exception: mark, do not assume
            blob = " ".join([title, desc, str(data.get("secondary_creator") or ""),
                             str(data.get("copyright") or "")]).lower()
            third_party = ("©" in blob or "copyright" in blob
                           or bool(data.get("secondary_creator")))
            out.append(ClipCandidate(
                provider=self.name,
                asset_id=nasa_id,
                download_url=url,
                title=title,
                page_url="https://images.nasa.gov/details/" + urllib.parse.quote(nasa_id),
                creator=str(creator),
                license_name=self.license_name,
                license_url=self.license_url,
                commercial_ok=not third_party,
                attribution_required=True,      # courtesy credit for NASA
                width=0, height=0, duration=0.0,
                tags=" ".join(data.get("keywords") or []) + " " + title,
                thumbnail=((it.get("links") or [{}])[0].get("href") or ""),
                extra={"third_party_rights": third_party,
                       "renditions": renditions,
                       "nasa_center": data.get("center", ""),
                       "date_created": data.get("date_created", "")},
            ))
        return out

    def download(self, cand, dest: str) -> bool:
        """Try each published rendition until one is under the size ceiling.
        NASA often publishes only a multi-GB master; downloading that inside a
        render is wasteful, so the cap decides, not the filename."""
        urls = list((cand.extra or {}).get("renditions") or [cand.download_url])
        for u in urls:
            if http_download(self.name, u, dest, limiter=self.limiter, log=self.log):
                return True
        return False

    def _renditions(self, nasa_id: str) -> list:
        doc = http_json(self.name, ASSET + urllib.parse.quote(nasa_id), attempts=2,
                        limiter=self.limiter, log=self.log)
        hrefs = [i.get("href", "") for i in ((doc.get("collection") or {}).get("items") or [])]
        hrefs = [h for h in hrefs if h.lower().endswith((".mp4", ".mov", ".webm"))]
        out = []
        for pref in PREF:
            for h in hrefs:
                if h.endswith(pref) and h not in out:
                    out.append(h)
        for h in hrefs:
            if h not in out:
                out.append(h)
        return out
