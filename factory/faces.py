#!/usr/bin/env python3
"""Free-licensed portrait library for the @airevolutionx-style thumbnails.

Owner 2026-11-01: "প্রতেকটা ফটোর মধ্যে একটি করে মানুষের ফটো আছে" - the reference
channel puts a recognisable person in every thumbnail, so we do too.

HARD RULE (compliance): we never hotlink press photos. Every portrait here is a
verified FREE licence from Wikimedia Commons (CC BY / CC BY-SA / CC0 / PD) with
its author recorded, and the credit line is appended to the video description.
That keeps the editorial use lawful and attributable; it also means a missing or
un-downloadable portrait simply falls back to a face-less thumbnail.

People are matched to the story from its title/subject (company -> best known
face). Nothing is fabricated: a face is only used when the story really names
that person or their company.
"""
import json
import os
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "NextAIVision/1.0 (thumbnail faces; contact selimsb645@gmail.com)"}
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "faces_cache")

# key -> Commons file, licence, author (verified 2026-11-01 via the Commons API)
PEOPLE = {
    "sam_altman": {"file": "File:Sam Altman November 2022.jpg", "license": "CC BY 2.0",
                   "author": "Village Global", "name": "Sam Altman"},
    "dario_amodei": {"file": "File:Dario Amodei in 2023.jpg", "license": "CC BY 2.0",
                     "author": "UK Prime Minister", "name": "Dario Amodei"},
    "elon_musk": {"file": "File:Elon Musk (12270805983).jpg", "license": "CC BY 2.0",
                  "author": "Tesla Owners Club Belgium", "name": "Elon Musk"},
    "jensen_huang": {"file": "File:Jensen Huang (cropped) (2024).jpg", "license": "CC BY 4.0",
                     "author": "Peter Dasilva", "name": "Jensen Huang"},
    "satya_nadella": {"file": "File:MS-Exec-Nadella-Satya-2017-08-31-22.jpg",
                      "license": "CC BY-SA 4.0", "author": "Brian Smale / Microsoft",
                      "name": "Satya Nadella"},
    "demis_hassabis": {"file": "File:Demis Hassabis Royal Society.jpg",
                       "license": "CC BY-SA 4.0", "author": "Duncan.Hull",
                       "name": "Demis Hassabis"},
    "sundar_pichai": {"file": "File:Sundar pichai.png", "license": "CC BY 3.0",
                      "author": "YouTube", "name": "Sundar Pichai"},
    "mark_zuckerberg": {"file": "File:Mark-Zuckerberg-2019.jpg", "license": "CC BY-SA 4.0",
                        "author": "Anurag R Dubey", "name": "Mark Zuckerberg"},
    "yann_lecun": {"file": "File:Yann LeCun (29146901108).jpg", "license": "CC BY-SA 2.0",
                   "author": "Jérémy Barande", "name": "Yann LeCun"},
    "fei_fei_li": {"file": "File:Fei-Fei Li at AI for Good 2017.jpg", "license": "CC BY 2.0",
                   "author": "ITU Pictures", "name": "Fei-Fei Li"},
    "mira_murati": {"file": "File:Guests at the 2026 Met Gala 274 (Mira Murati).jpg",
                    "license": "CC BY 4.0", "author": "SWinxy", "name": "Mira Murati"},
    "aravind_srinivas": {"file": "File:Aravind Srinivas TC Day 3.jpg", "license": "CC BY 2.0",
                         "author": "TechCrunch", "name": "Aravind Srinivas"},
}

# story keyword -> person (person names win over companies; first match in order)
MATCH = [
    ("sam altman", "sam_altman"), ("altman", "sam_altman"),
    ("dario amodei", "dario_amodei"), ("amodei", "dario_amodei"),
    ("elon musk", "elon_musk"), ("musk", "elon_musk"),
    ("jensen huang", "jensen_huang"), ("huang", "jensen_huang"),
    ("satya nadella", "satya_nadella"), ("nadella", "satya_nadella"),
    ("demis hassabis", "demis_hassabis"), ("hassabis", "demis_hassabis"),
    ("sundar pichai", "sundar_pichai"), ("pichai", "sundar_pichai"),
    ("zuckerberg", "mark_zuckerberg"),
    ("yann lecun", "yann_lecun"), ("lecun", "yann_lecun"),
    ("fei-fei", "fei_fei_li"), ("fei fei", "fei_fei_li"),
    ("mira murati", "mira_murati"), ("murati", "mira_murati"),
    ("aravind", "aravind_srinivas"), ("perplexity", "aravind_srinivas"),
    # companies -> their best known face
    ("openai", "sam_altman"), ("gpt", "sam_altman"), ("chatgpt", "sam_altman"),
    ("anthropic", "dario_amodei"), ("claude", "dario_amodei"),
    ("xai", "elon_musk"), ("grok", "elon_musk"), ("tesla", "elon_musk"),
    ("spacex", "elon_musk"), ("neuralink", "elon_musk"),
    ("nvidia", "jensen_huang"), ("geforce", "jensen_huang"),
    ("microsoft", "satya_nadella"), ("copilot", "satya_nadella"),
    ("deepmind", "demis_hassabis"), ("alphafold", "demis_hassabis"),
    ("google", "sundar_pichai"), ("gemini", "sundar_pichai"),
    ("meta ", "mark_zuckerberg"), ("llama", "mark_zuckerberg"),
]


def pick(text):
    """Best matching person key for a title/subject, or None."""
    t = " " + re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()) + " "
    for needle, key in MATCH:
        if needle in t:
            return key
    return None


def credit(key):
    p = PEOPLE.get(key)
    if not p:
        return ""
    return (f"Thumbnail photo: {p['author']}, {p['license']}, via Wikimedia Commons "
            f"({p['file'].replace('File:', '')}).")


def _cache_path(key):
    return os.path.join(CACHE, key + ".jpg")


def fetch(key, timeout=60):
    """Download (once) and return a local portrait path, or None."""
    path = _cache_path(key)
    if os.path.exists(path) and os.path.getsize(path) > 20_000:
        return path
    p = PEOPLE.get(key)
    if not p:
        return None
    try:
        q = urllib.parse.urlencode({"action": "query", "format": "json", "titles": p["file"],
                                    "prop": "imageinfo", "iiprop": "url|extmetadata",
                                    "iiurlwidth": "1100"})
        req = urllib.request.Request("https://commons.wikimedia.org/w/api.php?" + q, headers=UA)
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        page = list(d["query"]["pages"].values())[0]
        ii = page["imageinfo"][0]
        url = ii.get("thumburl") or ii["url"]
        os.makedirs(CACHE, exist_ok=True)
        req2 = urllib.request.Request(url, headers=UA)
        data = urllib.request.urlopen(req2, timeout=timeout).read()
        if len(data) < 20_000:
            return None
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception as ex:
        print(f"faces: {key} unavailable ({str(ex)[:70]}) -> face-less thumbnail", flush=True)
        return None


def face_for(text, timeout=60):
    """(key, local_path) for a story, or (None, None)."""
    key = pick(text)
    if not key:
        return None, None
    return key, fetch(key, timeout)


if __name__ == "__main__":
    import sys
    k, p = face_for(" ".join(sys.argv[1:]) or "OpenAI GPT Sam Altman")
    print(k, p, credit(k) if k else "")
