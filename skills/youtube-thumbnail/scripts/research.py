#!/usr/bin/env python3
"""
Competitor thumbnail research for the youtube-thumbnail skill.

Given a topic, find the highest-performing YouTube videos (ranked by
views-per-month so recent breakouts beat stale evergreen hits), download
their thumbnails locally, and write a manifest the skill can read.

This script is deterministic: it fetches, ranks, and downloads. The actual
pattern extraction ("everyone uses bright backgrounds -> go dark cinematic")
is vision + judgment work that the skill does by Reading the downloaded
images listed in the manifest.

Usage:
    python3 research.py "how to lose visceral fat" [--top 6] [--pool 12] [--out DIR]

Prints the run directory and the list of downloaded thumbnail paths.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

from _serpapi import youtube_search, hqdefault_fallback


def slugify(text: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:maxlen].strip("-") or "topic"


def download(url: str, dest: Path) -> bool:
    """Download url -> dest. On a maxresdefault 404, retry hqdefault. Return success."""
    for candidate in (url, hqdefault_fallback(url)):
        try:
            r = requests.get(candidate, timeout=30)
            if r.status_code == 200 and len(r.content) > 1000:
                dest.write_bytes(r.content)
                return True
        except requests.RequestException:
            continue
    return False


def run(topic: str, top: int, pool: int, out_dir: Path) -> dict:
    videos = youtube_search(topic, limit=pool)
    research_dir = out_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)

    competitors = []
    for i, v in enumerate(videos[:top], 1):
        fname = f"{i:02d}_{slugify(v['title'], 30)}.jpg"
        dest = research_dir / fname
        ok = download(v["thumbnail"], dest)
        competitors.append(
            {
                "rank": i,
                "title": v["title"],
                "channel": v["channel"],
                "link": v["link"],
                "views": v["views"],
                "published": v["published"],
                "months_old": v["months_old"],
                "views_per_month": v["views_per_month"],
                "thumbnail_url": v["thumbnail"],
                "local_path": str(dest) if ok else None,
                "downloaded": ok,
            }
        )

    manifest = {
        "topic": topic,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ranking": "views_per_month",
        "pool_size": len(videos),
        "competitors": competitors,
    }
    (research_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Human-readable table for quick scanning / the brief.
    lines = [
        f"# Competitor thumbnails: {topic}",
        f"_Ranked by views/month, generated {manifest['generated_at']}_",
        "",
        "| # | Title | Channel | Views | Age | Views/mo | Image |",
        "|---|-------|---------|-------|-----|----------|-------|",
    ]
    for c in competitors:
        img = Path(c["local_path"]).name if c["local_path"] else "(download failed)"
        lines.append(
            f"| {c['rank']} | {c['title']} | {c['channel']} | {c['views']:,} | "
            f"{c['published']} | {c['views_per_month']:,.0f} | {img} |"
        )
    (research_dir / "competitors.md").write_text("\n".join(lines) + "\n")

    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--top", type=int, default=6, help="thumbnails to download")
    ap.add_argument("--pool", type=int, default=12, help="search results to rank")
    ap.add_argument("--out", default=None, help="run directory (default: ./thumbnail-runs/<date>-<slug>)")
    args = ap.parse_args()

    if args.out:
        out_dir = Path(args.out)
    else:
        stamp = datetime.now().strftime("%Y%m%d")
        out_dir = Path.cwd() / "thumbnail-runs" / f"{stamp}-{slugify(args.topic)}"

    manifest = run(args.topic, args.top, args.pool, out_dir)

    downloaded = [c for c in manifest["competitors"] if c["downloaded"]]
    print(f"RUN_DIR: {out_dir}")
    print(f"RESEARCH_DIR: {out_dir / 'research'}")
    print(f"DOWNLOADED: {len(downloaded)}/{len(manifest['competitors'])}")
    print("\nTop competitor thumbnails to analyze (Read these images):")
    for c in downloaded:
        print(f"  {c['local_path']}  <- {c['title']} ({c['views_per_month']:,.0f}/mo)")
    if len(downloaded) < len(manifest["competitors"]):
        print("\nNote: some maxres thumbnails 404'd and were skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
