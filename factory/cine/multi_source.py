"""Phase 3+4+6 - multi-source scene matching, ranked selection and asset intake.

For every storyboard scene:
  1. build 2-4 concrete, filmable queries from the scene's own text and keywords;
  2. search every enabled provider (results are cached per query);
  3. rank by text relevance, real resolution, orientation, duration fit, source
     trust and freshness;
  4. download only the winner-candidates, verify each file with ffprobe;
  5. reject low resolution, wrong aspect, corrupt/too-short media, duplicate ids,
     identical file hashes and perceptual duplicates (dHash + hue histogram);
  6. validate the licence before the clip is accepted;
  7. if nothing qualifies, hand back a locally generated motion card - never an
     unrelated clip just to fill the scene.

Bounded concurrency is used for search prefetching only (a small pool, no
unbounded fan-out); downloads happen one at a time, because a render needs a
handful of clips, not a library.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:                                   # package import
    from . import licensing as LIC
    from . import visual_match as VM
    from .providers import enabled_providers, env_flag
    from .providers.base import MIN_WIDTH_HD, clean_query
except ImportError:                    # direct script use
    import licensing as LIC            # type: ignore
    import visual_match as VM          # type: ignore
    from providers import enabled_providers, env_flag      # type: ignore
    from providers.base import MIN_WIDTH_HD, clean_query   # type: ignore

FACTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(FACTORY, "footage", "multi_asset_manifest.json")

# what a scene renders at; a narrower source would have to be upscaled
TARGET_WIDTH_DEFAULT = 1920
MAX_USEFUL_DURATION = 45.0        # longer clips are fine, just less flexible
MIN_USABLE_DURATION = 1.6
ASPECT_MIN, ASPECT_MAX = 1.60, 1.90        # 16:9 with a little tolerance


# ── query construction ─────────────────────────────────────────────────────
_STOP = {"the", "and", "that", "this", "with", "from", "into", "just", "they",
         "their", "there", "what", "when", "which", "will", "would", "could",
         "have", "has", "had", "are", "was", "were", "for", "but", "not", "you",
         "your", "its", "it's", "about", "after", "before", "over", "than",
         "then", "them", "now", "new", "one", "two", "more", "most", "some"}


def _concrete_words(text: str, limit: int = 4) -> List[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", (text or "").lower())
    out, seen = [], set()
    for w in words:
        if w in _STOP or w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def scene_queries(scene: Dict[str, Any]) -> List[str]:
    """2-4 search queries for one scene. Concrete nouns first: stock libraries
    have footage of objects and places, not of abstract claims."""
    qs: List[str] = []

    def add(q: str) -> None:
        q = clean_query(q)
        if q and q.lower() not in {x.lower() for x in qs}:
            qs.append(q)

    add(scene.get("search_query", "") or "")
    kw = [k for k in (scene.get("keywords") or []) if str(k).strip()]
    if kw:
        add(" ".join(str(k) for k in kw[:2]))
        add(" ".join(str(k) for k in kw[:1] + ["cinematic"]))
    words = _concrete_words(scene.get("text", "") or scene.get("t", ""))
    if words:
        add(" ".join(words[:2]))
        add(" ".join(words[:3]))
    if str(scene.get("visual_type", "")).startswith("technology"):
        add(" ".join((kw[:1] or words[:1] or ["technology"]) + ["laboratory"]))
    return qs[:4]


# ── ranking ────────────────────────────────────────────────────────────────
def _text_score(query: str, cand) -> float:
    q = set(w for w in re.findall(r"[a-z\-]{3,}", query.lower()) if w not in _STOP)
    if not q:
        return 0.0
    blob = f"{getattr(cand, 'tags', '')} {getattr(cand, 'title', '')}".lower()
    hits = sum(1 for w in q if w in blob)
    return hits / len(q)


def _resolution_score(w: int, target_w: int) -> float:
    if not w:
        return 0.6                       # unknown until ffprobe (NASA)
    if w >= 3840:
        return 2.2
    if w >= 2560:
        return 2.6                       # 1440p timeline: no upscale at all
    if w >= 1920:
        return 2.4
    if w >= target_w:
        return 2.0
    if w >= MIN_WIDTH_HD:
        return 1.0                       # usable, but it will be upscaled
    return 0.0


def rank_candidates(cands: Iterable[Any], query: str, scene: Dict[str, Any],
                    target_w: int = TARGET_WIDTH_DEFAULT,
                    provider_trust: Optional[Dict[str, float]] = None) -> List[Tuple[float, Any]]:
    """Order candidates for one query. Deterministic and explainable: every
    component is a number a human can audit in the reject log."""
    trust = provider_trust or {}
    scene_dur = float(scene.get("duration") or 0) or 4.5
    scored: List[Tuple[float, Any]] = []
    for c in cands:
        if not getattr(c, "download_url", ""):
            continue
        w, h = int(getattr(c, "width", 0) or 0), int(getattr(c, "height", 0) or 0)
        aspect = (w / h) if w and h else 0.0
        text = _text_score(query, c) * 3.0
        res = _resolution_score(w, target_w)
        orient = 1.0 if (aspect == 0 or ASPECT_MIN <= aspect <= ASPECT_MAX) else -1.2
        dur = float(getattr(c, "duration", 0) or 0)
        if dur and dur < max(MIN_USABLE_DURATION, min(scene_dur, 3.0)):
            dur_s = -0.8
        elif dur > MAX_USEFUL_DURATION:
            dur_s = 0.3
        else:
            dur_s = 0.9
        prov = trust.get(getattr(c, "provider", ""), 0.85)
        lic = 1.0 if LIC.validate(c)["ok"] else -5.0
        scored.append((round(text + res + orient + dur_s + prov + lic, 4), c))
    scored.sort(key=lambda t: (-t[0], getattr(t[1], "asset_id", "")))
    return scored


# ── matcher ────────────────────────────────────────────────────────────────
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path: str = MANIFEST_PATH) -> Dict[str, Any]:
    try:
        with open(path) as f:
            doc = json.load(f)
        doc.setdefault("assets", [])
        doc.setdefault("ids", [])
        doc.setdefault("hashes", [])
        return doc
    except Exception:
        return {"assets": [], "ids": [], "hashes": []}


def save_manifest(doc: Dict[str, Any], path: str = MANIFEST_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=1)
    os.replace(tmp, path)


class MultiSourceMatcher:
    """Stateful matcher for one film: keeps the used-set, the persistent
    manifest and per-provider statistics."""

    def __init__(self, log=print, target_w: int = TARGET_WIDTH_DEFAULT,
                 cachedir: Optional[str] = None, manifest_path: str = MANIFEST_PATH,
                 providers: Optional[List[Any]] = None):
        self.log = log
        self.target_w = target_w
        # explicit providers are for tests/harnesses; production always resolves
        # the flag-gated registry so a missing key disables just that provider.
        self.providers = list(providers) if providers is not None else enabled_providers(log=log)
        self.manifest_path = manifest_path
        self.manifest = load_manifest(manifest_path)
        self.used_ids = set(self.manifest.get("ids", []))
        self.used_hashes = set(self.manifest.get("hashes", []))
        self.used_dhash: List[int] = []
        self.used_hue: List[list] = []
        self.stats: Dict[str, Any] = {"queries": 0, "candidates": 0,
                                      "downloads": 0, "accepted": 0,
                                      "rejected": 0, "duplicates_rejected": 0,
                                      "per_provider": {}, "rejects": []}
        self._cachedir = cachedir

    # -- helpers ---------------------------------------------------------
    def _provider_stat(self, name: str) -> Dict[str, int]:
        return self.stats["per_provider"].setdefault(
            name, {"search_hits": 0, "accepted": 0, "downloads": 0})

    @property
    def rejections(self) -> List[Dict[str, Any]]:
        """Everything the matcher refused, with the reason (audit trail)."""
        return self.stats["rejects"]

    def provider_trust(self) -> Dict[str, float]:
        return {"pixabay": 1.0, "pexels": 1.0, "nasa": 0.9, "mixkit": 0.8}

    def prefetch(self, scenes: List[Dict[str, Any]], workers: int = 3,
                 limit: int = 12) -> None:
        """Warm the query cache for every scene with bounded concurrency.
        Searches only; nothing is downloaded here."""
        jobs = [(p, q) for sc in scenes for q in scene_queries(sc)
                for p in self.providers if p.available()]

        def run(job):
            prov, q = job
            try:
                prov.search(q, limit=limit)
            except Exception as e:                     # never fatal
                self.log(f"  prefetch {prov.name}: {str(e)[:70]}")
            return 1

        if not jobs:
            return
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as ex:
            list(ex.map(run, jobs))

    def _reject(self, cand, why: str, query: str) -> None:
        self.stats["rejected"] += 1
        if len(self.stats["rejects"]) < 200:
            self.stats["rejects"].append({"provider": cand.provider,
                                          "id": cand.asset_id, "why": why,
                                          "query": query})

    # -- main entry ------------------------------------------------------
    def match_scene(self, scene: Dict[str, Any], out_dir: str,
                    min_relevance: float = 0.34) -> Dict[str, Any]:
        os.makedirs(out_dir, exist_ok=True)
        tag = f"s{int(scene.get('scene_id', 0)):02d}"
        queries = scene_queries(scene)
        scene_dur = float(scene.get("duration") or 0) or 4.5
        tried = 0

        for query in queries:
            pool = []
            for prov in self.providers:
                if not prov.available():
                    continue
                cands = prov.search(query, limit=12)
                self.stats["queries"] += 1
                self.stats["candidates"] += len(cands)
                self._provider_stat(prov.name)["search_hits"] += len(cands)
                pool.extend(cands)
            if not pool:
                continue
            ranked = rank_candidates(pool, query, scene, self.target_w,
                                     self.provider_trust())
            for score, cand in ranked[:8]:
                rel = _text_score(query, cand)
                if rel < min_relevance:
                    self._reject(cand, f"weak text relevance {rel:.2f}", query)
                    continue
                if cand.key in self.used_ids:
                    self._reject(cand, "asset id already used", query)
                    self.stats["duplicates_rejected"] += 1
                    continue
                lic = LIC.validate(cand)
                if not lic["ok"]:
                    self._reject(cand, "licence: " + lic["reason"], query)
                    continue
                if not cand.provider:
                    continue
                prov = next((p for p in self.providers if p.name == cand.provider), None)
                if prov is None or not prov.auto_download:
                    self._reject(cand, "provider not downloadable automatically", query)
                    continue
                dest = os.path.join(out_dir, f"{tag}_{cand.provider}_{cand.asset_id}.mp4")
                if not os.path.exists(dest):
                    tried += 1
                    self.stats["downloads"] += 1
                    self._provider_stat(cand.provider)["downloads"] += 1
                    if not prov.download(cand, dest):
                        self._reject(cand, "download failed", query)
                        continue
                probe = VM.probe(dest)
                if not probe:
                    self._reject(cand, "unreadable media (ffprobe failed)", query)
                    try:
                        os.remove(dest)
                    except OSError:
                        pass
                    continue
                dur, w, h = probe
                if dur < MIN_USABLE_DURATION:
                    self._reject(cand, f"too short ({dur:.1f}s)", query)
                    continue
                if w < MIN_WIDTH_HD:
                    self._reject(cand, f"low resolution {w}x{h}", query)
                    continue
                aspect = (w / h) if h else 0
                if not (ASPECT_MIN <= aspect <= ASPECT_MAX):
                    self._reject(cand, f"not 16:9 ({w}x{h})", query)
                    continue
                sha = _sha256_file(dest)
                if sha in self.used_hashes:
                    self._reject(cand, "identical file hash already used", query)
                    self.stats["duplicates_rejected"] += 1
                    continue
                try:
                    dh = VM.dhash(dest)
                    hue = VM.hue_hist(dest)
                except Exception:
                    dh, hue = None, None
                if dh is not None and any(VM.hamming(dh, u) < 6
                                          for u in self.used_dhash if u):
                    self._reject(cand, "perceptual duplicate", query)
                    self.stats["duplicates_rejected"] += 1
                    continue
                if hue and any(VM.hue_close(hue, u) for u in self.used_hue if u):
                    self._reject(cand, "same hue signature", query)
                    self.stats["duplicates_rejected"] += 1
                    continue

                # accept
                self.used_ids.add(cand.key)
                self.used_hashes.add(sha)
                if dh is not None:
                    self.used_dhash.append(dh)
                if hue:
                    self.used_hue.append(hue)
                self.stats["accepted"] += 1
                self._provider_stat(cand.provider)["accepted"] += 1
                rec = LIC.asset_record(cand, dest, probe, sha, scene.get("scene_id"))
                rec.update({"query": query, "relevance": round(rel, 3),
                            "rank_score": score,
                            "upscale_factor": round(max(self.target_w / max(w, 1), 1.0), 2)})
                self.manifest["assets"].append(rec)
                self.manifest["ids"].append(cand.key)
                self.manifest["hashes"].append(sha)
                save_manifest(self.manifest, self.manifest_path)
                self.log(f"  scene {scene.get('scene_id')}: {cand.provider} "
                         f"{cand.asset_id} {w}x{h} {dur:.1f}s rel={rel:.2f} "
                         f"[{query}]")
                return {
                    "kind": "video", "path": dest, "source": cand.provider,
                    "asset_id": cand.asset_id, "url": cand.page_url or cand.download_url,
                    "license": cand.license_name,
                    "attribution": cand.attribution_line(),
                    "duration": dur, "width": w, "height": h,
                    "query": query, "relevance": round(rel, 3),
                    "creator": cand.creator, "page": cand.page_url,
                    "sha256": sha,
                    "rejects": self.stats["rejects"][-6:],
                }

        # nothing qualified: an original motion card, never a random clip
        png = os.path.join(out_dir, f"{tag}_card.png")
        VM.make_card(scene, png)
        return {"kind": "image", "path": png, "source": "generated",
                "asset_id": f"card{scene.get('scene_id', 0)}",
                "url": "", "license": "original (generated locally)",
                "attribution": "NextAI Vision 4 - original motion card",
                "duration": 0.0, "width": 1920, "height": 1080,
                "query": queries[0] if queries else "n/a", "relevance": 0,
                "rejects": self.stats["rejects"][-6:],
                "fallback_reason": "no licensed clip passed verification"}

    def report(self) -> Dict[str, Any]:
        return {"stats": self.stats,
                "providers": [p.status() for p in self.providers],
                "manifest_path": self.manifest_path,
                "assets_in_manifest": len(self.manifest.get("assets", []))}


# ── drop-in replacement used by the editor when the flag is on ─────────────
_SINGLETON: Optional[MultiSourceMatcher] = None
_API_STATE: Dict[str, Any] = {"used_hashes": [], "used_hues": [], "used_ids": set()}


_SINGLETON = None


def last_stats():
    """Stats of the matcher that served the current process (reporting only)."""
    return _SINGLETON.stats if _SINGLETON is not None else {}


def match_scene_multi(scene, out_dir, manifest, used_hashes, used_hues, used_ids,
                      min_score=1, workdir_tag=None):
    """Same signature/return as visual_match.match_scene, so cine.editor can call
    it without knowing which engine produced the clip."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = MultiSourceMatcher()
    _API_STATE["used_ids"] = used_ids if used_ids is not None else set()
    _SINGLETON.used_ids = set(used_ids or set()) | set(_SINGLETON.used_ids)
    return _SINGLETON.match_scene(scene, out_dir)


def matcher_report() -> Dict[str, Any]:
    return _SINGLETON.report() if _SINGLETON else {}
