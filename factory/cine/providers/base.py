"""Phase 2 - provider base layer.

Everything that is common to every footage source lives here so a new provider
is ~80 lines of mapping code, not a new HTTP client:

  * ``ClipCandidate``  - one normalized search hit (source, ids, licence, media)
  * ``SearchCache``    - on-disk query cache (providers are never asked twice for
                         the same query inside the TTL, which is also how we stay
                         inside Pixabay's "no mass automated queries" rule)
  * ``RateLimiter``    - per-provider request pacing + hard per-minute ceiling
  * ``http_json``      - retries with backoff on 429/5xx/timeouts, and it never
                         puts an API key into a log line or an exception message
  * ``FootageProvider``- the contract: available() / search() / download()

No provider here assumes that a free download is a commercial licence. Every
candidate carries an explicit licence name, a licence reference and a
``commercial_ok`` flag that the licence layer (``cine/licensing.py``) validates
independently before a clip is allowed into a film.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

FACTORY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_ROOT = os.path.join(FACTORY, "footage", "_cache")

UA = ("NextAIVision4/1.0 (documentary editor; +https://github.com/"
      "selimsb645-max/nextai-video-automation)")

# Ask for enough width to survive a 1440p timeline without upscaling.
MIN_WIDTH_HD = 1280
MIN_WIDTH_PREFERRED = 1920


# ── small utilities ────────────────────────────────────────────────────────
def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean feature flag. Anything but an explicit truthy value is
    false, so a typo can never switch a provider on by accident."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def secret(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def redact(text: str) -> str:
    """Strip anything that looks like an API key from a message we may log."""
    t = str(text)
    t = re.sub(r"(?i)(key|token|api_key|apikey)=([^&\s]+)", r"\1=***", t)
    t = re.sub(r"(?i)(authorization:\s*)(bearer\s+)?[A-Za-z0-9._\-]{6,}", r"\1***", t)
    t = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{6,}", r"\1***", t)
    for n in ("PIXABAY_API_KEY", "PEXELS_API_KEY"):
        v = os.environ.get(n)
        if v and len(v) > 6:
            t = t.replace(v, "***")
    return t


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def clean_query(q: str) -> str:
    q = " ".join(str(q or "").split())
    return q[:120]


@dataclass
class ClipCandidate:
    """One normalized search result. ``asset_id`` is the provider's own id."""
    provider: str
    asset_id: str
    download_url: str
    title: str = ""
    page_url: str = ""
    creator: str = ""
    license_name: str = ""
    license_url: str = ""
    commercial_ok: bool = False
    attribution_required: bool = False
    width: int = 0
    height: int = 0
    duration: float = 0.0
    fps: float = 0.0
    tags: str = ""
    thumbnail: str = ""
    kind: str = "video"
    query: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.asset_id}"

    @property
    def aspect(self) -> float:
        if not self.width or not self.height:
            return 0.0
        return round(self.width / self.height, 3)

    def attribution_line(self) -> str:
        bits = [self.title or f"{self.provider} clip {self.asset_id}"]
        if self.creator:
            bits.append(self.creator)
        bits.append(self.provider)
        if self.license_name:
            bits.append(self.license_name)
        if self.page_url:
            bits.append(self.page_url)
        return " | ".join(bits)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["key"] = self.key
        d["aspect"] = self.aspect
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ClipCandidate":
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in allowed})


# ── HTTP with retry/backoff ────────────────────────────────────────────────
class ProviderError(RuntimeError):
    """Raised for a provider-level failure (network, auth, quota)."""

    def __init__(self, provider: str, message: str, status: int = 0):
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.status = status


RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


def http_json(provider: str, url: str, params: Optional[Dict[str, Any]] = None,
              headers: Optional[Dict[str, str]] = None, timeout: int = 30,
              attempts: int = 3, limiter: Optional["RateLimiter"] = None,
              log=None) -> Dict[str, Any]:
    """GET a JSON document with bounded retries. The API key (when present in
    ``params``) is never included in a logged message."""
    q = dict(params or {})
    full = url + ("?" + urllib.parse.urlencode(q) if q else "")
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    hdrs.update(headers or {})
    last: Tuple[str, int] = ("unknown", 0)
    for i in range(attempts):
        if limiter is not None:
            limiter.acquire()
        try:
            req = urllib.request.Request(full, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            return json.loads(raw or b"{}")
        except urllib.error.HTTPError as e:
            last = (f"HTTP {e.code}", e.code)
            if e.code not in RETRY_STATUS:
                raise ProviderError(provider, f"HTTP {e.code}", e.code) from None
        except Exception as e:  # timeouts, DNS, TLS, bad JSON
            last = (type(e).__name__ + ": " + redact(str(e)), 0)
        if i < attempts - 1:
            # 1.5s, 3.5s (+ jitter) - enough to clear a 429 burst
            time.sleep(1.5 * (2 ** i) + random.uniform(0, 0.6))
    raise ProviderError(provider, f"giving up after {attempts} tries ({last[0]})",
                        last[1])


def head_size(url: str, timeout: int = 25) -> int:
    """Content-Length of a URL, or 0 when the host does not tell us."""
    try:
        url = urllib.parse.quote(str(url), safe=":/?&=%~+#[],'!$&()*;@")
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(r.headers.get("Content-Length") or 0)
    except Exception:
        return 0


def http_download(provider: str, url: str, dest: str, timeout: int = 240,
                  min_bytes: int = 120_000, limiter: Optional["RateLimiter"] = None,
                  log=None, max_bytes: int = 260 * 1024 * 1024) -> bool:
    """Stream one file to ``dest`` via a temp file. Returns False (never a fake
    True) when the transfer fails or the result is implausibly small."""
    tmp = dest + ".part"
    # NASA (and some archive hosts) publish file names with spaces and unicode -
    # urllib refuses control/space characters, so normalize the path only.
    url = urllib.parse.quote(str(url), safe=":/?&=%~+#[],'!$&()*;@")
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    size = head_size(url)
    if size and size > max_bytes:
        if log:
            log(f"  {provider}: skip {size // 1024 // 1024}MB master (cap "
                f"{max_bytes // 1024 // 1024}MB)")
        return False
    if limiter is not None:
        limiter.acquire()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
            if r.status and int(r.status) >= 400:
                raise ProviderError(provider, f"download HTTP {r.status}", r.status)
            total = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:               # hard ceiling
                    raise ProviderError(provider, "asset larger than 400MB")
                f.write(chunk)
        if os.path.getsize(tmp) < min_bytes:
            raise ProviderError(provider, "file too small to be video")
        os.replace(tmp, dest)
        return True
    except Exception as e:
        if log:
            log(f"  download failed [{provider}]: {redact(str(e))[:110]}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


# ── rate limiting ──────────────────────────────────────────────────────────
class RateLimiter:
    """Token-bucket-ish pacing: at most ``per_minute`` requests per rolling
    minute and at least ``min_interval`` seconds between starts. Cheap, global
    per process, and it makes a provider's documented limits a hard ceiling
    instead of a suggestion."""

    _lock = threading.Lock()
    _state: Dict[str, List[float]] = {}

    def __init__(self, provider: str, per_minute: int = 60, min_interval: float = 0.4):
        self.provider = provider
        self.per_minute = per_minute
        self.min_interval = min_interval

    def acquire(self) -> None:
        with RateLimiter._lock:
            now = time.monotonic()
            hist = [t for t in RateLimiter._state.get(self.provider, [])
                    if now - t < 60.0]
            if len(hist) >= self.per_minute:
                wait = 60.0 - (now - hist[0]) + 0.05
                time.sleep(max(wait, 0))
                now = time.monotonic()
                hist = [t for t in hist if now - t < 60.0]
            if hist and now - hist[-1] < self.min_interval:
                time.sleep(self.min_interval - (now - hist[-1]))
                now = time.monotonic()
            hist.append(now)
            RateLimiter._state[self.provider] = hist


# ── search cache ───────────────────────────────────────────────────────────
class SearchCache:
    """Disk cache keyed by provider + query + limit. Keeps repeated renders and
    the retry loops from hammering an API, which is what the providers' terms
    ask for. TTL defaults to 24h (``FOOTAGE_CACHE_TTL_S`` overrides)."""

    def __init__(self, provider: str, root: Optional[str] = None, ttl: Optional[float] = None):
        self.provider = provider
        self.root = os.path.join(root or CACHE_ROOT, "search", provider)
        if ttl is None:
            try:
                ttl = float(os.environ.get("FOOTAGE_CACHE_TTL_S", "") or 86400)
            except ValueError:
                ttl = 86400.0
        self.ttl = ttl
        self.hits = 0
        self.misses = 0

    def _path(self, query: str, limit: int) -> str:
        return os.path.join(self.root, sha1(f"{clean_query(query).lower()}|{limit}") + ".json")

    def get(self, query: str, limit: int) -> Optional[List[ClipCandidate]]:
        p = self._path(query, limit)
        try:
            if not os.path.exists(p):
                return None
            doc = json.load(open(p))
            if self.ttl and time.time() - float(doc.get("ts", 0)) > self.ttl:
                return None
            self.hits += 1
            return [ClipCandidate.from_dict(d) for d in doc.get("candidates", [])]
        except Exception:
            return None

    def put(self, query: str, limit: int, cands: List[ClipCandidate]) -> None:
        try:
            os.makedirs(self.root, exist_ok=True)
            p = self._path(query, limit)
            tmp = p + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"ts": time.time(), "provider": self.provider,
                           "query": clean_query(query), "limit": limit,
                           "candidates": [c.to_dict() for c in cands]}, f)
            os.replace(tmp, p)
            self.misses += 1
        except Exception:
            pass

    def stats(self) -> Dict[str, Any]:
        return {"provider": self.provider, "hits": self.hits,
                "misses": self.misses, "ttl_s": self.ttl}


# ── provider contract ──────────────────────────────────────────────────────
class FootageProvider:
    """Base class. Subclasses implement ``_search`` and (optionally) override
    ``download`` when the file host needs different handling."""

    name = "base"
    display = "Base"
    requires_key: Optional[str] = None      # env var name
    auto_download = True
    per_minute = 60
    min_interval = 0.4
    license_name = ""
    license_url = ""

    def __init__(self, log=None):
        self.log = log or (lambda *_a, **_k: None)
        self.limiter = RateLimiter(self.name, self.per_minute, self.min_interval)
        self.cache = SearchCache(self.name)
        self.errors: List[str] = []
        self.requests = 0

    # -- availability ------------------------------------------------------
    def available(self) -> bool:
        return self.unavailable_reason() is None

    def unavailable_reason(self) -> Optional[str]:
        if self.requires_key and not secret(self.requires_key):
            return f"{self.requires_key} not set"
        return None

    def status(self) -> Dict[str, Any]:
        return {"provider": self.name, "available": self.available(),
                "reason": self.unavailable_reason() or "",
                "requires_key": self.requires_key or "",
                "auto_download": self.auto_download,
                "license": self.license_name,
                "errors": self.errors[-5:]}

    # -- search ------------------------------------------------------------
    def search(self, query: str, limit: int = 12) -> List[ClipCandidate]:
        query = clean_query(query)
        if not query or not self.available():
            return []
        hit = self.cache.get(query, limit)
        if hit is not None:
            return hit
        try:
            self.requests += 1
            cands = self._search(query, limit)
        except ProviderError as e:
            self.errors.append(redact(str(e)))
            self.log(f"  {self.name}: search failed for {query!r}: {redact(str(e))[:110]}")
            return []
        except Exception as e:  # a provider bug must never kill a render
            self.errors.append(redact(f"{type(e).__name__}: {e}"))
            self.log(f"  {self.name}: unexpected error for {query!r}: "
                     f"{redact(str(e))[:110]}")
            return []
        cands = [c for c in cands if c and c.download_url]
        for c in cands:
            c.query = query
        self.cache.put(query, limit, cands)
        return cands

    def _search(self, query: str, limit: int) -> List[ClipCandidate]:
        raise NotImplementedError

    # -- download ----------------------------------------------------------
    def download(self, cand: ClipCandidate, dest: str) -> bool:
        if not self.auto_download:
            self.errors.append(f"{self.name}: automated download not permitted")
            return False
        return http_download(self.name, cand.download_url, dest,
                             limiter=self.limiter, log=self.log)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} available={self.available()}>"
