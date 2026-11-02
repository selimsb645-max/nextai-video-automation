"""Provider registry + feature flags.

Flags (all independent, all default-safe):

    ENABLE_MULTI_SOURCE_FOOTAGE   false   - master switch for the new matcher
    ENABLE_PIXABAY_PROVIDER       true    - existing source, on when a key exists
    ENABLE_PEXELS_PROVIDER        false   - needs PEXELS_API_KEY as well
    ENABLE_NASA_PROVIDER          true    - public API, no key

A provider that is switched on but has no credentials reports itself
unavailable with a reason and is skipped; nothing raises, so a workflow never
fails because a secret is missing. The old Pixabay-only path in
``cine/visual_match.py`` is untouched and remains the fallback.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .base import FootageProvider, env_flag, secret
from .mixkit import MixkitManualProvider
from .nasa import NASAVideoProvider
from .pexels import PexelsProvider
from .pixabay import PixabayProvider

FLAG_MASTER = "ENABLE_MULTI_SOURCE_FOOTAGE"
FLAG_PIXABAY = "ENABLE_PIXABAY_PROVIDER"
FLAG_PEXELS = "ENABLE_PEXELS_PROVIDER"
FLAG_NASA = "ENABLE_NASA_PROVIDER"


def flags() -> Dict[str, Any]:
    import os
    return {
        FLAG_MASTER: env_flag(FLAG_MASTER, False),
        FLAG_PIXABAY: env_flag(FLAG_PIXABAY, True),
        FLAG_PEXELS: env_flag(FLAG_PEXELS, False),
        FLAG_NASA: env_flag(FLAG_NASA, True),
        "PIXABAY_API_KEY_present": bool(secret("PIXABAY_API_KEY")),
        "PEXELS_API_KEY_present": bool(secret("PEXELS_API_KEY")),
        "raw": {k: os.environ.get(k, "") for k in
                (FLAG_MASTER, FLAG_PIXABAY, FLAG_PEXELS, FLAG_NASA)},
    }


def all_providers(log=None) -> List[FootageProvider]:
    """Every provider the flags allow, whether or not its key is present.
    Used for reporting, so a missing credential shows up as a status line
    instead of silently vanishing."""
    out: List[FootageProvider] = []
    if env_flag(FLAG_PIXABAY, True):
        out.append(PixabayProvider(log=log))
    if env_flag(FLAG_NASA, True):
        out.append(NASAVideoProvider(log=log))
    if env_flag(FLAG_PEXELS, False):
        out.append(PexelsProvider(log=log))
    out.append(MixkitManualProvider(log=log))
    return out


def enabled_providers(log=None) -> List[FootageProvider]:
    """Only the providers that can actually be used right now.

    Pixabay first (best cinematic stock), NASA second (space/science scenes the
    stock libraries do not have), Pexels third, Mixkit last because it is a
    hand-curated list. A provider whose credential is missing is skipped, never
    fatal - the run continues with the rest."""
    return [p for p in all_providers(log=log) if p.available()]


def rebuild_provider(name: str, log=None):
    """Build one named provider regardless of the flags (test harness only)."""
    for p in all_providers(log=log):
        if p.name == name:
            return p
    return None


def provider_status(log=None) -> Dict[str, Any]:
    """Everything the test workflow prints: flags, per-provider availability."""
    provs = all_providers(log=log)
    return {"flags": flags(),
            "providers": [p.status() for p in provs]}


__all__ = ["flags", "all_providers", "enabled_providers", "provider_status", "FootageProvider",
           "FLAG_MASTER", "FLAG_PIXABAY", "FLAG_PEXELS", "FLAG_NASA"]
