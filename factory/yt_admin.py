"""Small YouTube admin CLI for the channel (owner 2026-11-14).

Needed when the owner wants a Short taken off the channel before it goes public:
``factory.py`` can upload and schedule, but it has no delete/unschedule path.

    python3 factory/yt_admin.py list <video_id>
    python3 factory/yt_admin.py unschedule <video_id>   # private, publishAt cleared
    python3 factory/yt_admin.py delete <video_id>

Auth is the same headless OAuth token the factory uses (yt-auth/token_nextai.json,
written from the YT_TOKEN_JSON secret by the workflow).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import factory as F  # noqa: E402

API = "https://www.googleapis.com/youtube/v3/"


def call(method, path, params, body=None):
    url = API + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, data=(json.dumps(body).encode() if body is not None else None),
        method=method,
        headers={"Authorization": "Bearer " + F.get_token()["access_token"],
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:400]}


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: yt_admin.py list|unschedule|delete <video_id>")
    cmd, vid = sys.argv[1], sys.argv[2]
    if cmd == "list":
        code, doc = call("GET", "videos", {"part": "snippet,status", "id": vid})
        for it in doc.get("items", []):
            print(json.dumps({"id": it["id"], "title": it["snippet"]["title"],
                              "status": it["status"]}, ensure_ascii=False, indent=1))
        if not doc.get("items"):
            print("EMPTY (already deleted or not on this channel):", vid,
                  "| http", code)
        return
    if cmd == "unschedule":
        code, doc = call("PUT", "videos", {"part": "status"},
                         {"id": vid, "status": {"privacyStatus": "private"}})
        print("unschedule:", code, json.dumps(doc)[:300])
        return
    if cmd == "delete":
        code, doc = call("DELETE", "videos", {"id": vid})
        print("delete:", code, json.dumps(doc)[:300])
        return
    raise SystemExit("unknown command " + cmd)


if __name__ == "__main__":
    main()
