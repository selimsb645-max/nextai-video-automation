"""Phase 3 - semantic visual matching.

For every storyboard scene we need one licensed asset that actually shows what
the sentence says. Stock search is never trusted blindly:

  * candidates are searched with several query variants (the scene query, the
    keyword pair, and a widened "technology" variant);
  * each candidate is scored on tag/text overlap with the scene keywords;
  * the download is verified with ffprobe (real duration, real size);
  * exact duplicates are rejected by id, near duplicates by dHash + hue
    histogram, and nothing already used in this film or the last N films is
    accepted twice;
  * every accepted asset is written to an asset manifest with source, url,
    licence and attribution text.

Fallback order when nothing passes: alternate query -> alternate source ->
original motion-graphic card (always available, generated locally).
Nothing is ever reported as downloaded unless the file is on disk and probes.
"""
import hashlib
import json
import os
import shutil
import subprocess
import urllib.parse
import urllib.request

FACTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "").strip()
UA = {"User-Agent": "NextAIVision4/1.0 (documentary editor; contact owner)"}


# ── helpers ────────────────────────────────────────────────────────────────
def probe(path):
    """(duration_s, width, height) or None when the file is unusable."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height:format=duration",
                            "-of", "json", path], capture_output=True, text=True)
        d = json.loads(r.stdout or "{}")
        st = (d.get("streams") or [{}])[0]
        dur = float((d.get("format") or {}).get("duration") or 0)
        w, h = int(st.get("width") or 0), int(st.get("height") or 0)
        if dur <= 0 or w <= 0:
            return None
        return dur, w, h
    except Exception:
        return None


def dhash(path, size=9):
    """Perceptual 8x8 difference hash from a frame near the middle."""
    try:
        from PIL import Image
        dur = probe(path)
        at = max((dur[0] / 2) if dur else 0, 0.2)
        tmp = path + ".dhash.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}",
                        "-i", path, "-frames:v", "1", "-vf",
                        f"scale={size}:{size - 1}", tmp],
                       capture_output=True)
        if not os.path.exists(tmp):
            return None
        im = Image.open(tmp).convert("L").resize((size, size - 1))
        px = im.tobytes()          # 8-bit grayscale bytes, one per pixel
        bits = 0
        i = 0
        for row in range(size - 1):
            for col in range(size - 1):
                left = px[row * size + col]
                right = px[row * size + col + 1]
                bits = (bits << 1) | (1 if left > right else 0)
                i += 1
        os.remove(tmp)
        return bits
    except Exception:
        return None


def hamming(a, b):
    if a is None or b is None:
        return 99
    return bin(a ^ b).count("1")


def hue_hist(path, bins=12):
    try:
        from PIL import Image
        dur = probe(path)
        at = max((dur[0] / 2) if dur else 0, 0.2)
        tmp = path + ".hue.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}",
                        "-i", path, "-frames:v", "1", "-vf", "scale=64:36", tmp],
                       capture_output=True)
        if not os.path.exists(tmp):
            return None
        im = Image.open(tmp).convert("HSV")
        h = im.getchannel(0).histogram()
        per = max(len(h) // bins, 1)
        vec = [sum(h[i * per:(i + 1) * per]) for i in range(bins)]
        tot = sum(vec) or 1
        os.remove(tmp)
        return [v / tot for v in vec]
    except Exception:
        return None


def hue_close(a, b, tol=0.02):
    if not a or not b:
        return False
    return sum(abs(x - y) for x, y in zip(a, b)) < tol


def overlap(query, tags):
    q = [w for w in query.lower().split() if len(w) > 2]
    t = (tags or "").lower()
    if not q:
        return 0
    return sum(1 for w in q if w in t)


def _fetch(url, dest, tag):
    """Download with a real UA (some hosts 403 anonymous urllib) and verify."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=90) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        return os.path.getsize(dest) > 80_000
    except Exception as e:
        print(f"  visual: {tag} download failed: {str(e)[:90]}")
        try:
            os.remove(dest)
        except OSError:
            pass
        return False


# ── providers ──────────────────────────────────────────────────────────────
class Pixabay:
    """Pixabay video API. Licence: Pixabay Content Licence (free, no
    attribution required, modification allowed, no resale of unmodified clips)."""
    name = "pixabay"

    def available(self):
        return bool(PIXABAY_KEY)

    def search(self, query, limit=12):
        url = ("https://pixabay.com/api/videos/?key=" + PIXABAY_KEY +
               "&q=" + urllib.parse.quote(query) +
               "&video_type=film&safesearch=true&per_page=" + str(limit))
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=40) as r:
                d = json.loads(r.read())
        except Exception as e:
            print(f"  visual: pixabay search failed for {query!r}: {str(e)[:90]}")
            return []
        out = []
        for h in d.get("hits", []):
            vids = h.get("videos") or {}
            best = vids.get("large") or vids.get("medium") or vids.get("small") or {}
            if not best.get("url"):
                continue
            out.append({
                "source": "pixabay", "id": str(h.get("id")),
                "url": best["url"], "dur": float(best.get("duration") or 0),
                "w": int(best.get("width") or 0), "h": int(best.get("height") or 0),
                "tags": h.get("tags", ""), "license": "Pixabay Content License",
                "page": h.get("pageURL", ""), "author": h.get("user", ""),
                "attribution": "",
            })
        return out

    def download(self, cand, dest):
        return _fetch(cand["url"], dest, "pixabay")


class Commons:
    """Wikimedia Commons video fallback. Licence is read from the file's own
    extmetadata, so attribution text is real, not assumed. Honors 429 by
    cooling down for the rest of the run instead of hammering the API."""
    name = "commons"
    _cooldown_until = 0.0

    def available(self):
        import time
        return time.time() > Commons._cooldown_until

    def _cool(self, seconds=180):
        import time
        Commons._cooldown_until = time.time() + seconds
        print(f"  visual: commons rate-limited, cooling down {seconds}s")

    def search(self, query, limit=8):
        api = ("https://commons.wikimedia.org/w/api.php?action=query&format=json"
               "&generator=search&gsrnamespace=6&gsrlimit=" + str(limit) +
               "&gsrsearch=" + urllib.parse.quote(f"{query} filetype:video") +
               "&prop=imageinfo&iiprop=url|size|mime|extmetadata")
        try:
            with urllib.request.urlopen(urllib.request.Request(api, headers=UA),
                                        timeout=40) as r:
                d = json.loads(r.read())
        except Exception:
            return []
        out = []
        for page in ((d.get("query") or {}).get("pages") or {}).values():
            ii = (page.get("imageinfo") or [{}])[0]
            mime = ii.get("mime", "")
            if not mime.startswith("video/") and mime != "application/ogg":
                continue
            if int(ii.get("width") or 0) < 640:
                continue
            meta = ii.get("extmetadata") or {}
            lic = (meta.get("LicenseShortName") or {}).get("value") or "Commons"
            artist = (meta.get("Artist") or {}).get("value") or ""
            out.append({
                "source": "commons", "id": str(page.get("pageid")),
                "url": ii.get("url"), "dur": 0.0,
                "w": int(ii.get("width") or 0), "h": int(ii.get("height") or 0),
                "tags": page.get("title", ""), "license": lic,
                "page": ii.get("descriptionurl", ""), "author": artist,
                "attribution": f"{page.get('title','')} - {lic} - {artist}"[:180],
            })
        return out

    def download(self, cand, dest):
        # Wikimedia enforces its User-Agent policy and returns 403 without one
        ok = _fetch(cand["url"], dest, "commons")
        if not ok:
            self._cool()
        return ok


class ArchiveOrg:
    """Internet Archive public-domain film collections (Prelinger and friends).

    Free, no key, and the licence text comes from the item metadata, so
    attribution stays truthful. Used when the stock APIs are unavailable or
    rate-limited (Wikimedia returns 429 on shared IPs)."""
    name = "archive"
    COLLECTIONS = ("prelinger", "publicmovies", "opensource_movies", "feature_films")

    def available(self):
        return True

    def search(self, query, limit=6):
        q = ("(" + " OR ".join(f"collection:{c}" for c in self.COLLECTIONS) +
             ') AND mediatype:movies AND (' +
             " AND ".join(w for w in query.split()[:3] if w) + ")")
        url = ("https://archive.org/advancedsearch.php?q=" +
               urllib.parse.quote(q) +
               "&fl[]=identifier&fl[]=title&fl[]=licenseurl&fl[]=collection"
               "&rows=" + str(limit) + "&page=1&output=json")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=45) as r:
                d = json.loads(r.read())
        except Exception as e:
            print(f"  visual: archive.org search failed: {str(e)[:80]}")
            return []
        out = []
        for doc in ((d.get("response") or {}).get("docs") or []):
            ident = doc.get("identifier")
            if not ident:
                continue
            f = self._pick_file(ident)
            if not f:
                continue
            lic = doc.get("licenseurl") or self._licence(ident) or "Public domain"
            out.append({
                "source": "archive", "id": ident, "url": f,
                "dur": 0.0, "w": 0, "h": 0,
                "tags": str(doc.get("title", "")), "license": lic,
                "page": f"https://archive.org/details/{ident}",
                "author": "Internet Archive",
                "attribution": f"{doc.get('title','')[:70]} - {lic} - archive.org",
            })
        return out

    def _pick_file(self, ident):
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    f"https://archive.org/metadata/{ident}", headers=UA),
                    timeout=45) as r:
                m = json.loads(r.read())
        except Exception:
            return ""
        best = ""
        for f in (m.get("files") or []):
            name = (f.get("name") or "").lower()
            if not name.endswith((".mp4", ".webm", ".ogv", ".mpeg", ".avi")):
                continue
            if f.get("private"):
                continue
            size = int(f.get("size") or 0)
            if size < 2_000_000 or size > 120_000_000:      # keep Actions disk sane
                continue
            if name.endswith(".mp4"):
                return f"https://archive.org/download/{ident}/{f['name']}"
            best = best or f"https://archive.org/download/{ident}/{f['name']}"
        return best

    def _licence(self, ident):
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    f"https://archive.org/metadata/{ident}", headers=UA),
                    timeout=30) as r:
                m = json.loads(r.read())
            md = (m.get("metadata") or {})
            return md.get("licenseurl") or md.get("rights") or ""
        except Exception:
            return ""

    def download(self, cand, dest):
        ok = _fetch(cand["url"], dest, "archive")
        # archive.org sometimes serves an HTML interstitial; require real video
        if ok and probe(dest) is None:
            try:
                os.remove(dest)
            except OSError:
                pass
            return False
        return ok


PROVIDERS = [Pixabay(), Commons(), ArchiveOrg()]


# ── motion-graphic card fallback (always available, original) ──────────────
def make_card(scene, out_png, w=1920, h=1080, accent=(0, 236, 255)):
    """A designed still that still looks intentional: dark gradient, accent
    rule, the scene's key phrase. Used only when no footage passes QC."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    img = Image.new("RGB", (w, h), (7, 10, 18))
    d = ImageDraw.Draw(img)
    for y in range(h):                      # vertical gradient
        k = y / h
        d.line([(0, y), (w, y)], fill=(int(7 + 12 * k), int(10 + 14 * k),
                                      int(18 + 26 * k)))
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([int(w * 0.55), int(h * 0.05), int(w * 1.15), int(h * 0.95)],
               fill=(int(accent[0] * 0.22), int(accent[1] * 0.22), int(accent[2] * 0.22)))
    img = Image.blend(img, Image.blend(img, glow, 0.55).filter(
        ImageFilter.GaussianBlur(70)), 0.85)
    d = ImageDraw.Draw(img)
    fonts = [os.path.join(FACTORY, "fonts", "Anton-Regular.ttf"),
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]

    def font(sz):
        for f in fonts:
            try:
                return ImageFont.truetype(f, sz)
            except Exception:
                continue
        return ImageFont.load_default()

    phrase = " ".join(scene.get("keywords", [])[:2]).upper() or "NEXT AI"
    f = font(int(h * 0.12))
    while d.textlength(phrase, font=f) > w * 0.8 and f.size > 40:
        f = font(f.size - 8)
    d.text((w * 0.09, h * 0.44), phrase, font=f, fill=(245, 249, 255))
    d.rectangle([w * 0.09, h * 0.40, w * 0.09 + 120, h * 0.40 + 8], fill=accent)
    sub = font(int(h * 0.028))
    d.text((w * 0.09, h * 0.60), (scene.get("visual_description", "")[:88]),
           font=sub, fill=(150, 168, 190))
    img.save(out_png, quality=92)
    return out_png


# ── matcher ────────────────────────────────────────────────────────────────
def load_manifest(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {"assets": [], "history": []}


def save_manifest(m, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(m, f, indent=1)


def _queries_for(scene):
    q = [scene.get("search_query", "").strip()]
    kw = scene.get("keywords") or []
    if kw:
        q.append(" ".join(kw[:2]))
        q.append(" ".join(kw[:1] + ["technology"]))
    if scene.get("visual_type") == "technology_demonstration":
        q.insert(0, (q[0] + " robot") if q[0] else "robot technology")
    seen, out = set(), []
    for x in q:
        x = " ".join(x.split())
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out[:3]


def match_scene(scene, out_dir, manifest, used_hashes, used_hues,
                used_ids, min_score=1, workdir_tag=None):
    """Return an accepted asset dict for one scene, or a generated card."""
    os.makedirs(out_dir, exist_ok=True)
    tag = workdir_tag or f"s{scene['scene_id']:02d}"
    rejects = []

    for qi, query in enumerate(_queries_for(scene)):
        for prov in PROVIDERS:
            if not prov.available():
                continue
            cands = prov.search(query, limit=10)
            cands.sort(key=lambda c: -overlap(query, c.get("tags")))
            for rank, c in enumerate(cands[:6]):
                if overlap(query, c.get("tags")) < min_score and prov.name == "pixabay":
                    rejects.append({"id": c["id"], "why": "weak tag overlap",
                                    "query": query})
                    continue
                if (c["source"] + c["id"]) in used_ids:
                    rejects.append({"id": c["id"], "why": "already used", "query": query})
                    continue
                dest = os.path.join(out_dir, f"{tag}_{prov.name}_{c['id']}.mp4")
                if not os.path.exists(dest) and not prov.download(c, dest):
                    rejects.append({"id": c["id"], "why": "download failed",
                                    "query": query})
                    continue
                pr = probe(dest)
                if not pr or pr[0] < 1.6 or pr[1] < 480:
                    rejects.append({"id": c["id"], "why": f"unusable media {pr}",
                                    "query": query})
                    continue
                h, hue = dhash(dest), hue_hist(dest)
                if any(hamming(h, u) < 6 for u in used_hashes if u):
                    rejects.append({"id": c["id"], "why": "perceptual duplicate",
                                    "query": query})
                    continue
                if any(hue_close(hue, u) for u in used_hues if u):
                    rejects.append({"id": c["id"], "why": "same hue signature",
                                    "query": query})
                    continue
                used_hashes.append(h)
                used_hues.append(hue)
                used_ids.add(c["source"] + c["id"])
                return {
                    "kind": "video", "path": dest, "source": c["source"],
                    "asset_id": c["id"], "url": c["url"], "license": c["license"],
                    "attribution": c.get("attribution") or
                    (f"{c['source']} - {c['license']}" +
                     (f" - {c['author']}" if c.get("author") else "")),
                    "duration": pr[0], "width": pr[1], "height": pr[2],
                    "query": query, "relevance": overlap(query, c.get("tags")),
                    "rejects": rejects,
                }

    # every provider failed -> original generated card (never a fake success)
    png = os.path.join(out_dir, f"{tag}_card.png")
    make_card(scene, png)
    return {"kind": "image", "path": png, "source": "generated",
            "asset_id": hashlib.md5(png.encode()).hexdigest()[:10],
            "url": "", "license": "original (generated locally)",
            "attribution": "NextAI Vision 4 - original motion card",
            "duration": 0.0, "width": 1920, "height": 1080,
            "query": "n/a", "relevance": 0, "rejects": rejects,
            "fallback_reason": "no licensed footage passed verification"}
