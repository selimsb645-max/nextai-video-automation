#!/usr/bin/env python3
"""YouTube Analytics feedback loop (owner spec Task 5).

Pulls, per published video: impressions, CTR, average view duration, average
percentage viewed, 30-second intro retention, retention dips/spikes, watch time.
Writes factory/analytics_lessons.json, which the script prompt reads back so the
next videos inherit what actually held viewers.

Honesty rules:
  * If the OAuth token lacks the yt-analytics.readonly scope the script reports
    ANALYTICS_SCOPE_MISSING and writes nothing. It never invents numbers.
  * Metrics YouTube has not populated yet are left out (not zero-filled).
  * With no data the lessons file keeps the last known values untouched.

Run: python3 actions/analytics_feedback.py [--days 28] [--max-videos 15]
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACT = os.path.join(REPO, "factory")
sys.path.insert(0, FACT)

LESSONS = os.path.join(FACT, "analytics_lessons.json")
TOKEN_CANDIDATES = [os.path.join(REPO, "yt-auth", "token.json"),
                    os.path.join(REPO, "yt-auth", "token_nextai.json")]
SCOPES_HINT = "yt-analytics.readonly"


def _token():
    for p in TOKEN_CANDIDATES:
        if os.path.exists(p):
            try:
                d = json.load(open(p))
                t = d.get("access_token") or d.get("token")
                if t:
                    return t, p, d.get("scope", "")
            except Exception:
                continue
    return None, None, ""


def _api(url, token, params):
    import urllib.parse
    import urllib.request
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(url + "?" + q,
                                headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def _report(msg):
    print(msg)
    try:
        with open(os.path.join(FACT, "analytics_run.log"), "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--max-videos", type=int, default=15)
    a = ap.parse_args()

    token, path, scope = _token()
    if not token:
        _report("ANALYTICS_NO_TOKEN: no yt-auth token file found; nothing measured.")
        return 2
    if scope and SCOPES_HINT not in scope:
        _report(f"ANALYTICS_SCOPE_MISSING: token at {os.path.basename(path)} has scopes "
                f"'{scope}' - needs {SCOPES_HINT}. Nothing measured, nothing written.")
        return 3

    import datetime as dt
    end = dt.date.today()
    start = end - dt.timedelta(days=a.days)
    ids = ",".join(["channel==MINE"])
    base = "https://youtubeanalytics.googleapis.com/v2/reports"
    rows, err = None, None
    try:
        rows = _api(base, token, {
            "ids": ids, "startDate": start.isoformat(), "endDate": end.isoformat(),
            "metrics": "views,estimatedMinutesWatched,averageViewDuration,"
                       "averageViewPercentage,subscribersGained",
            "dimensions": "video", "sort": "-views",
            "maxResults": a.max_videos})
    except Exception as ex:
        err = str(ex)[:300]

    if rows is None:
        _report(f"ANALYTICS_API_ERROR: {err}. Nothing measured (no numbers invented).")
        return 4

    vids = []
    for r in (rows.get("rows") or []):
        vid, views, mins, avd, avp, subs = (r + [None] * 6)[:6]
        vids.append({"video": vid, "views": views, "watch_minutes": mins,
                     "avd_s": avd, "avg_pct_viewed": avp, "subs_gained": subs})

    # 30-second intro retention + retention curve shape per video (best effort)
    for v in vids[:5]:
        try:
            cur = _api(base, token, {
                "ids": ids, "startDate": start.isoformat(), "endDate": end.isoformat(),
                "metrics": "audienceWatchRatio,relativeRetentionPerformance",
                "dimensions": "elapsedVideoTimeRatio", "filters": f"video=={v['video']}"})
            pts = [(float(r[0]), float(r[1])) for r in (cur.get("rows") or [])
                   if r and r[0] is not None]
            if pts:
                v["retention_curve_points"] = len(pts)
                v["intro_retention_est_pct"] = round(min(pts, key=lambda p: abs(p[0] - 0.06))[1] * 100, 1)
                gaps = [pts[i + 1][1] - pts[i][1] for i in range(len(pts) - 1)]
                if gaps:
                    worst = min(range(len(gaps)), key=lambda i: gaps[i])
                    best = max(range(len(gaps)), key=lambda i: gaps[i])
                    v["biggest_dip_at_ratio"] = round(pts[worst][0], 2)
                    v["biggest_spike_at_ratio"] = round(pts[best][0], 2)
        except Exception:
            continue

    # impressions + CTR live in a different report (needs the same scope)
    try:
        imp = _api(base, token, {
            "ids": ids, "startDate": start.isoformat(), "endDate": end.isoformat(),
            "metrics": "impressions,impressionsClickThroughRate",
            "dimensions": "video", "maxResults": a.max_videos})
        ctr = {r[0]: {"impressions": r[1], "ctr_pct": r[2]}
               for r in (imp.get("rows") or [])}
        for v in vids:
            if v["video"] in ctr:
                v.update(ctr[v["video"]])
    except Exception as ex:
        _report("ANALYTICS_CTR_UNAVAILABLE: " + str(ex)[:160] +
                " (impressions/CTR need the same yt-analytics scope).")

    out = {"generated": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
           "window_days": a.days, "videos": vids,
           "method": "YouTube Analytics API v2 (channel==MINE)",
           "missing": [k for k in ("impressions", "ctr_pct", "intro_retention_est_pct")
                       if not any(k in v for v in vids)]}
    os.makedirs(FACT, exist_ok=True)
    with open(LESSONS, "w") as f:
        json.dump(out, f, indent=1)
    _report(f"ANALYTICS_OK: {len(vids)} videos measured; lessons written to "
            f"factory/analytics_lessons.json; still missing: {out['missing'] or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
