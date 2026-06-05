#!/usr/bin/env python3
"""
Shared SerpAPI client for the youtube-thumbnail skill.

Two jobs:
  - youtube_search()  -> find high-performing competitor videos (views + thumbnail)
  - image_search()    -> gather reference assets (logos, products, visual metaphors)

The SERPAPI_KEY is read from the first .env that has it, searching a small list
of known locations. We never print the key.
"""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

SERP_ENDPOINT = "https://serpapi.com/search.json"

# .env locations to probe, in priority order. coaching-sales-os is the shared
# credential store on this host.
_ENV_CANDIDATES = [
    Path.home() / "repos" / "coaching-sales-os" / ".env",
    Path(__file__).resolve().parents[3] / "coaching-sales-os" / ".env",
    Path.cwd() / ".env",
]


def _load_key() -> str:
    """Return SERPAPI_KEY from the environment or the first .env that defines it."""
    key = os.environ.get("SERPAPI_KEY")
    if key:
        return key.strip()
    for env_path in _ENV_CANDIDATES:
        if not env_path.is_file():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("SERPAPI_KEY") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(
        "SERPAPI_KEY not found in environment or known .env files. "
        "Add it to coaching-sales-os/.env or export it."
    )


def _request(params: dict) -> dict:
    params = {**params, "api_key": _load_key()}
    resp = requests.get(SERP_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"SerpAPI error: {data['error']}")
    return data


# --- views / recency parsing ------------------------------------------------

_VIEW_SUFFIX = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def parse_views(raw) -> int:
    """'1.2M views' / '1,234 views' / 1234 -> int. Unknown -> 0."""
    if raw is None:
        return 0
    if isinstance(raw, (int, float)):
        return int(raw)
    text = str(raw).lower().replace("views", "").replace(",", "").strip()
    if not text:
        return 0
    m = re.match(r"([\d.]+)\s*([kmb]?)", text)
    if not m:
        return 0
    num = float(m.group(1))
    return int(num * _VIEW_SUFFIX.get(m.group(2), 1))


def _months_since(published_text: str) -> float:
    """Rough months elapsed from SerpAPI's 'published_date' free text.

    SerpAPI gives strings like '2 years ago', '3 months ago', '5 days ago'.
    We convert to an approximate month count, floored at ~0.5 so brand-new
    videos don't divide to absurd velocities.
    """
    if not published_text:
        return 12.0  # unknown -> assume a year so it doesn't dominate ranking
    text = published_text.lower()
    m = re.match(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", text)
    if not m:
        return 12.0
    n = int(m.group(1))
    unit = m.group(2)
    per_month = {
        "second": 1 / (60 * 24 * 30),
        "minute": 1 / (60 * 24 * 30),
        "hour": 1 / (24 * 30),
        "day": 1 / 30,
        "week": 7 / 30,
        "month": 1.0,
        "year": 12.0,
    }[unit]
    return max(n * per_month, 0.5)


def upgrade_thumbnail_url(url: str) -> str:
    """Rebuild a clean maxres thumbnail URL from the video ID.

    SerpAPI returns cropped, signed thumbnail URLs (hq720_2.jpg?sqp=...).
    We extract the /vi/<ID>/ segment and return the bare maxresdefault image
    with no crop params. maxresdefault is absent on a few low-res uploads;
    callers should fall back to hqdefault on a 404.
    """
    if not url:
        return url
    m = re.search(r"/vi/([A-Za-z0-9_-]{6,})/", url)
    if not m:
        return url.split("?")[0]
    return f"https://i.ytimg.com/vi/{m.group(1)}/maxresdefault.jpg"


def hqdefault_fallback(maxres_url: str) -> str:
    """hqdefault always exists; use when maxresdefault 404s."""
    return re.sub(r"/maxresdefault\.jpg$", "/hqdefault.jpg", maxres_url)


# --- public API -------------------------------------------------------------

def youtube_search(query: str, limit: int = 12) -> list[dict]:
    """Search YouTube and return ranked competitor videos.

    Each item: title, channel, link, views (int), published (str),
    months_old (float), views_per_month (float), thumbnail (maxres URL).
    Sorted by views_per_month descending -- recent breakouts rank above stale
    evergreen hits, which are the better thumbnail-pattern signal.
    """
    data = _request({"engine": "youtube", "search_query": query})
    out = []
    for v in data.get("video_results", []):
        views = parse_views(v.get("views"))
        months = _months_since(v.get("published_date", ""))
        thumb = ""
        t = v.get("thumbnail")
        if isinstance(t, dict):
            thumb = t.get("static") or t.get("rich") or ""
        elif isinstance(t, str):
            thumb = t
        out.append(
            {
                "title": v.get("title", ""),
                "channel": (v.get("channel") or {}).get("name", ""),
                "link": v.get("link", ""),
                "views": views,
                "published": v.get("published_date", ""),
                "months_old": round(months, 1),
                "views_per_month": round(views / months, 1),
                "thumbnail": upgrade_thumbnail_url(thumb),
            }
        )
    out.sort(key=lambda x: x["views_per_month"], reverse=True)
    return out[:limit]


def image_search(query: str, limit: int = 8) -> list[dict]:
    """Google Images search for reference assets.

    Each item: title, source, thumbnail, original (full-res URL).
    """
    data = _request({"engine": "google_images", "q": query})
    out = []
    for img in data.get("images_results", [])[:limit]:
        out.append(
            {
                "title": img.get("title", ""),
                "source": img.get("source", ""),
                "thumbnail": img.get("thumbnail", ""),
                "original": img.get("original", ""),
            }
        )
    return out


if __name__ == "__main__":
    # Smoke test: python3 _serpapi.py "<query>"
    q = sys.argv[1] if len(sys.argv) > 1 else "claude code automation"
    print(f"# youtube_search({q!r}) @ {datetime.now(timezone.utc).isoformat()}\n")
    for i, r in enumerate(youtube_search(q, limit=6), 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['channel']} | {r['views']:,} views | {r['published']} "
              f"| {r['views_per_month']:,}/mo")
        print(f"   {r['thumbnail']}\n")
