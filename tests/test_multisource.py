"""Next AI Vision 4 - multi-source footage engine unit tests.

No network calls: every HTTP entry point is stubbed. These tests pin the rules
the engine must never break - provider gating, normalisation, licence rejection,
ranking, dedupe, cache behaviour, rate limiting, attribution and fallback.
"""
import json
import os
import sys
import time

import pytest

FACTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "factory")
sys.path.insert(0, FACTORY)

from cine import licensing as LIC                              # noqa: E402
from cine import multi_source as MS                            # noqa: E402
from cine import visual_match as VM                            # noqa: E402
from cine.providers import base as PB                          # noqa: E402
from cine.providers import enabled_providers, provider_status   # noqa: E402
from cine.providers import mixkit as MK                        # noqa: E402
from cine.providers import nasa as NA                          # noqa: E402
from cine.providers import pexels as PX                        # noqa: E402
from cine.providers import pixabay as PXB                      # noqa: E402


def cand(**kw):
    base = dict(provider="pixabay", asset_id="1", title="server room", page_url="https://p/1",
                download_url="https://d/1.mp4", creator="someone",
                license_name="Pixabay Content License", width=1920, height=1080,
                duration=12.0, tags=["server", "room", "data"], commercial_ok=True)
    base.update(kw)
    return PB.ClipCandidate(**base)


# ── feature flags ----------------------------------------------------------
def test_flags_default_off_and_pixabay_on(monkeypatch):
    for k in ("ENABLE_MULTI_SOURCE_FOOTAGE", "ENABLE_PIXABAY_PROVIDER",
              "ENABLE_PEXELS_PROVIDER", "ENABLE_NASA_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    assert PB.env_flag("ENABLE_MULTI_SOURCE_FOOTAGE") is False
    assert PB.env_flag("ENABLE_PIXABAY_PROVIDER", True) is True
    assert PB.env_flag("ENABLE_PEXELS_PROVIDER") is False
    assert PB.env_flag("ENABLE_NASA_PROVIDER", True) is True


def test_missing_keys_disable_only_that_provider(monkeypatch):
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.setenv("ENABLE_PEXELS_PROVIDER", "true")
    st = {p["provider"]: p for p in provider_status()["providers"]}
    assert st["pixabay"]["available"] is False
    assert "PIXABAY_API_KEY" in st["pixabay"]["reason"]
    assert st["pexels"]["available"] is False
    assert "PEXELS_API_KEY" in st["pexels"]["reason"]
    assert st["nasa"]["available"] is True                 # keyless provider
    names = [p.name for p in enabled_providers()]
    assert "pixabay" not in names and "pexels" not in names
    assert "nasa" in names


def test_keys_never_leak_into_status(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "SUPERSECRETKEY")
    blob = json.dumps(provider_status())
    assert "SUPERSECRETKEY" not in blob


# ── licence layer ----------------------------------------------------------
@pytest.mark.parametrize("licence", ["Pixabay Content License", "Pexels License",
                                     "NASA Media Usage Guidelines",
                                     "Mixkit Stock Video Free License", "Public Domain"])
def test_approved_licences_are_commercial(licence):
    res = LIC.validate(cand(license_name=licence, provider="nasa" if "NASA" in licence else "pixabay"))
    assert res["ok"] is True, res["reason"]
    assert res["commercial"] is True


def test_unknown_or_restricted_licence_is_rejected():
    res = LIC.validate(cand(license_name="All rights reserved"))
    assert res["ok"] is False and "unknown licence" in res["reason"]
    res2 = LIC.validate(cand(license_name="CC BY-NC 4.0"))
    assert res2["ok"] is False


def test_nasa_third_party_rights_are_vetoed():
    res = LIC.validate(cand(provider="nasa", license_name="NASA Media Usage Guidelines",
                            extra={"third_party_rights": True}))
    assert res["ok"] is False and "third-party" in res["reason"].lower()


def test_unreviewed_manual_entry_rejected():
    res = LIC.validate(cand(provider="mixkit", license_name="Mixkit Stock Video Free License",
                            extra={"curated": True, "license_reviewed": False}))
    assert res["ok"] is False and "not licence-reviewed" in res["reason"]


def test_attribution_report_dedupes_and_names_creators():
    assets = [
        {"provider": "pixabay", "asset_id": "1", "creator": "Ann",
         "license": "Pixabay Content License", "page_url": "https://p/1"},
        {"provider": "pixabay", "asset_id": "1", "creator": "Ann",
         "license": "Pixabay Content License", "page_url": "https://p/1"},
        {"provider": "nasa", "asset_id": "2", "creator": "NASA",
         "license": "NASA Media Usage Guidelines", "page_url": "https://p/2"},
    ]
    text = LIC.attribution_report(assets, title="Test film")
    assert text.startswith("Footage credits - Test film")
    assert text.count("Ann") == 1, "duplicate asset must appear once"
    assert "NASA" in text
    assert "https://p/1" in text


def test_generated_card_is_not_attributed():
    text = LIC.attribution_report([{"provider": "gen", "asset_id": "s1",
                                    "license": "original (generated locally)"}])
    assert "generated locally" in text


# ── scene matching ---------------------------------------------------------
def test_scene_queries_are_two_to_four_and_lead_with_search_query():
    sc = {"scene_id": 1, "text": "The servers started to glow as the model woke up.",
          "keywords": ["server room", "glowing lights"], "search_query": "server room glowing"}
    qs = MS.scene_queries(sc)
    assert 2 <= len(qs) <= 4
    assert qs[0] == "server room glowing"
    assert len(set(q.lower() for q in qs)) == len(qs), "no repeated query"


def test_ranking_prefers_hd_landscape_and_rejects_portrait():
    scene = {"scene_id": 1, "text": "server room glowing", "keywords": ["server", "room"],
             "search_query": "server room", "duration": 10}
    ranked = MS.rank_candidates(
        [cand(asset_id="hd"), cand(asset_id="lo", width=640, height=360),
         cand(asset_id="portrait", width=1080, height=1920)],
        "server room", scene, 1920, {})
    order = [c.asset_id for _s, c in ranked]
    assert order[0] == "hd"
    assert order.index("hd") < order.index("lo")
    # portrait footage is heavily penalised, never selected first
    assert order.index("hd") < order.index("portrait")


def test_match_scene_falls_back_to_motion_card_without_providers():
    m = MS.MultiSourceMatcher(providers=[], log=lambda *_: None,
                              manifest_path="/tmp/ms_fallback_manifest.json")
    sc = {"scene_id": 3, "text": "An empty street at night.", "keywords": [],
          "search_query": "", "duration": 4.0}
    out = m.match_scene(sc, "/tmp/ms_fallback_assets")
    assert out["kind"] == "image"
    assert out["source"] in ("gen", "generated")
    assert out.get("fallback_reason")


def test_match_scene_rejects_low_res_then_uses_next_candidate(tmp_path, monkeypatch):
    class FakeProvider(PB.FootageProvider):
        name = "pixabay"
        license_name = "Pixabay Content License"

        def __init__(self):
            super().__init__(log=lambda *_: None)
            self.served = 0

        def available(self):
            return True

        def _search(self, query, limit):
            return [cand(asset_id="low", width=640, height=360,
                         download_url="https://d/low.mp4"),
                    cand(asset_id="good", width=1920, height=1080,
                         download_url="https://d/good.mp4")]

        def download(self, c, dest):
            open(dest, "wb").write(b"x" * 2048)
            return True

    prov = FakeProvider()
    prov.cache = PB.SearchCache("test-lowres", str(tmp_path / "cache"))
    prober = {"good": (12.0, 1920, 1080), "low": (12.0, 640, 360)}
    monkeypatch.setattr(VM, "probe", lambda p: prober[os.path.basename(p).split("_")[-1].split(".")[0]])
    monkeypatch.setattr(VM, "dhash", lambda p: f"dh{os.path.basename(p)}")
    monkeypatch.setattr(VM, "hue_hist", lambda p: [0.1, 0.2])
    monkeypatch.setattr(MS, "_sha256_file", lambda p: "hash-" + os.path.basename(p))

    m = MS.MultiSourceMatcher(providers=[prov], log=lambda *_: None,
                              manifest_path=str(tmp_path / "manifest.json"))
    sc = {"scene_id": 1, "text": "server room glowing", "keywords": ["server", "room"],
          "search_query": "server room", "duration": 8.0}
    out = m.match_scene(sc, str(tmp_path))
    assert out["kind"] == "video"
    assert "good" in out["path"], "the HD clip must win"
    rec = [a for a in m.manifest["assets"] if a["asset_id"] == "good"][0]
    assert rec["width"] >= 1280, "an accepted clip is never sub-HD"
    assert not any(a["asset_id"] == "low" for a in m.manifest["assets"]), \
        "the 640x360 clip must never be accepted"


def test_same_clip_is_never_used_twice(tmp_path, monkeypatch):
    class OneClipProvider(PB.FootageProvider):
        name = "pixabay"
        license_name = "Pixabay Content License"

        def __init__(self):
            super().__init__(log=lambda *_: None)

        def available(self):
            return True

        def _search(self, query, limit):
            return [cand(asset_id="only", download_url="https://d/only.mp4")]

        def download(self, c, dest):
            open(dest, "wb").write(b"x" * 2048)
            return True

    prov = OneClipProvider()
    prov.cache = PB.SearchCache("test-oneclip", str(tmp_path / "cache"))
    monkeypatch.setattr(VM, "probe", lambda p: (12.0, 1920, 1080))
    monkeypatch.setattr(VM, "dhash", lambda p: "samehash")
    monkeypatch.setattr(VM, "hue_hist", lambda p: [0.1, 0.2])
    monkeypatch.setattr(MS, "_sha256_file", lambda p: "same-bytes")

    m = MS.MultiSourceMatcher(providers=[prov], log=lambda *_: None,
                              manifest_path=str(tmp_path / "manifest.json"))
    scenes = [{"scene_id": i, "text": "server room glowing", "keywords": ["server", "room"],
               "search_query": "server room", "duration": 6.0} for i in (1, 2)]
    first = m.match_scene(scenes[0], str(tmp_path))
    second = m.match_scene(scenes[1], str(tmp_path))
    assert first["kind"] == "video"
    assert second["kind"] == "image", "reuse must fall back to a card, not repeat the clip"
    assert m.stats["duplicates_rejected"] >= 1


# ── providers --------------------------------------------------------------
def test_pixabay_normalisation_and_no_key_in_output(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "SUPERSECRETKEY")
    monkeypatch.setenv("FOOTAGE_CACHE_DIR", "/tmp/ms_cache_px")
    monkeypatch.setattr(PXB, "http_json", lambda *a, **k: {"hits": [{
        "id": 42, "pageURL": "https://pixabay.com/videos/42", "tags": "server, room, data",
        "duration": 14, "user": "Ann",
        "videos": {"large": {"url": "https://cdn/42.mp4", "width": 1920, "height": 1080}}}]})
    p = PXB.PixabayProvider(log=lambda *_: None)
    p.cache = PB.SearchCache("pixabay-test", "/tmp/ms_cache_px")
    got = p.search("server room 42", limit=3)
    assert got and got[0].asset_id == "42"
    assert (got[0].width, got[0].height) == (1920, 1080)
    assert got[0].license_name == "Pixabay Content License"
    assert got[0].commercial_ok is True
    blob = json.dumps([c.to_dict() for c in got])
    assert "SUPERSECRETKEY" not in blob


def test_pexels_needs_key_then_normalises(monkeypatch, tmp_path):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert PX.PexelsProvider(log=lambda *_: None).available() is False

    monkeypatch.setenv("PEXELS_API_KEY", "k")
    monkeypatch.setenv("ENABLE_PEXELS_PROVIDER", "true")
    p = PX.PexelsProvider(log=lambda *_: None)
    assert p.available() is True
    p.cache = PB.SearchCache("pexels-test", str(tmp_path / "cache"))
    monkeypatch.setattr(PX, "http_json", lambda *a, **k: {"videos": [{
        "id": 7, "url": "https://www.pexels.com/video/7", "duration": 9,
        "width": 1920, "height": 1080, "user": {"name": "Bo"},
        "video_files": [{"link": "https://cdn/7.mp4", "width": 1920, "height": 1080,
                          "file_type": "video/mp4"}]}]})
    got = p.search("city night skyline", limit=2)
    assert got[0].provider == "pexels" and got[0].asset_id == "7"
    assert got[0].license_name == "Pexels License" and got[0].commercial_ok


def test_nasa_marks_third_party_assets(monkeypatch):
    item = {"href": "https://images-api.nasa.gov/asset/x",
            "data": [{"nasa_id": "x", "title": "Artemis crew", "description": "d",
                      "center": "JSC", "secondary_creator": "Acme Studio"}],
            "links": [{"href": "https://img/x.jpg"}]}
    monkeypatch.setattr(NA, "http_json", lambda *a, **k: {"collection": {"items": [item]}})
    p = NA.NASAVideoProvider(log=lambda *_: None)
    monkeypatch.setattr(p, "_renditions", lambda nasa_id: ["https://assets/x~large.mp4"])
    got = p.search("artemis crew 1", limit=2)
    assert got and got[0].commercial_ok is False
    assert LIC.validate(got[0])["ok"] is False


def test_mixkit_serves_only_reviewed_curated_entries(tmp_path, monkeypatch):
    path = tmp_path / "mixkit_curated.json"
    path.write_text(json.dumps({"assets": [
        {"id": "m1", "title": "Drone over city", "download_url": "https://x/m1.mp4",
         "page_url": "https://mixkit.co/m1", "creator": "Mixkit", "width": 1920,
         "height": 1080, "duration": 12, "license": "Mixkit Stock Video Free License",
         "license_reviewed": True, "tags": ["city", "drone"]},
        {"id": "m2", "title": "Unreviewed", "download_url": "https://x/m2.mp4",
         "license": "Mixkit Stock Video Free License", "license_reviewed": False,
         "tags": ["city"]}]}))
    monkeypatch.setattr(MK, "CURATED", str(path))
    p = MK.MixkitManualProvider(log=lambda *_: None)
    p.cache = PB.SearchCache("mixkit-test", str(tmp_path / "cache"))
    hits = p.search("city drone 1", limit=5)
    assert [c.asset_id for c in hits] == ["m1"]


def test_provider_errors_never_raise(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")

    def boom(*a, **k):
        raise PB.ProviderError("pixabay", "HTTP 429", 429)

    monkeypatch.setattr(PXB, "http_json", boom)
    p = PXB.PixabayProvider(log=lambda *_: None)
    p.cache = PB.SearchCache("pixabay-err", "/tmp/ms_cache_px")
    assert p.search("anything at all", limit=3) == []
    assert p.errors and "429" in p.errors[-1]


# ── cache, rate limiting, secrets -----------------------------------------
def test_search_cache_avoids_second_api_call(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        return {"hits": [{"id": 5, "pageURL": "https://p/5", "tags": "server",
                          "duration": 10, "user": "A",
                          "videos": {"large": {"url": "https://d/5.mp4",
                                               "width": 1920, "height": 1080}}}]}

    monkeypatch.setattr(PXB, "http_json", fake)
    p = PXB.PixabayProvider(log=lambda *_: None)
    p.cache = PB.SearchCache("pixabay-cache", str(tmp_path))
    first = p.search("server room cache", limit=2)
    second = p.search("server room cache", limit=2)
    assert len(first) == 1 and len(second) == 1
    assert calls["n"] == 1, "cache must prevent a repeated provider query"


def test_rate_limiter_spaces_requests():
    rl = PB.RateLimiter("test", per_minute=60, min_interval=0.2)
    t0 = time.monotonic()
    for _ in range(3):
        rl.acquire()
    assert time.monotonic() - t0 >= 0.35


def test_redact_hides_credentials():
    assert "secretkey" not in PB.redact("failed key=secretkey&q=x").lower()
    assert "bearer" not in PB.redact("Authorization: Bearer abc123").lower()
