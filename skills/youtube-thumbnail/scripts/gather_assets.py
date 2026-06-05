#!/usr/bin/env python3
"""
Reference-asset gathering for the youtube-thumbnail skill.

For a given concept, search the web for supporting images (logos, product shots,
screenshots, visual metaphors) and download usable ones into the run directory so
they can be attached to the generation call alongside the headshot.

The skill (LLM) decides *what* to gather per concept in Stage 4, then calls this
script with those queries. This script just fetches and validates.

Usage:
    python3 gather_assets.py RUN_DIR CONCEPT_LABEL "query one" "query two" ...
    # e.g. python3 gather_assets.py ./thumbnail-runs/20260604-foo A "Claude logo" "marketing dashboard"

Options:
    --per N    images to keep per query (default 2)

Writes RUN_DIR/assets/CONCEPT_LABEL/ and appends to RUN_DIR/assets/manifest.json.
Prints the downloaded asset paths.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import requests

from _serpapi import image_search

# Only keep real raster images we can hand to the image model.
_OK_TYPES = ("image/jpeg", "image/png", "image/webp")
_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def slugify(text: str, maxlen: int = 30) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:maxlen].strip("-") or "asset"


def _download(url: str, dest_stem: Path) -> Path | None:
    """Download url if it's a usable raster image. Returns the written path or None."""
    if not url:
        return None
    try:
        r = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (thumbnail-skill asset fetch)"},
        )
    except requests.RequestException:
        return None
    ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if r.status_code != 200 or ctype not in _OK_TYPES or len(r.content) < 1500:
        return None
    dest = dest_stem.with_suffix(_EXT[ctype])
    dest.write_bytes(r.content)
    return dest


def gather(run_dir: Path, concept: str, queries: list[str], per: int) -> dict:
    concept_dir = run_dir / "assets" / concept
    concept_dir.mkdir(parents=True, exist_ok=True)

    collected = []
    for q in queries:
        results = image_search(q, limit=per * 4)  # over-fetch; many URLs fail
        kept = 0
        for j, img in enumerate(results):
            if kept >= per:
                break
            stem = concept_dir / f"{slugify(q)}_{kept + 1}"
            # Prefer the full-res original, fall back to SerpAPI's own thumbnail.
            path = _download(img.get("original", ""), stem) or _download(
                img.get("thumbnail", ""), stem
            )
            if path:
                collected.append(
                    {
                        "query": q,
                        "source": img.get("source", ""),
                        "title": img.get("title", ""),
                        "local_path": str(path),
                    }
                )
                kept += 1

    # Merge into a run-level assets manifest.
    manifest_path = run_dir / "assets" / "manifest.json"
    manifest = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
    manifest.setdefault("concepts", {})[concept] = {
        "queries": queries,
        "assets": collected,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return {"concept": concept, "assets": collected, "dir": str(concept_dir)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("concept")
    ap.add_argument("queries", nargs="+")
    ap.add_argument("--per", type=int, default=2)
    args = ap.parse_args()

    result = gather(Path(args.run_dir), args.concept, args.queries, args.per)

    print(f"CONCEPT: {result['concept']}")
    print(f"ASSET_DIR: {result['dir']}")
    print(f"COLLECTED: {len(result['assets'])}")
    for a in result["assets"]:
        print(f"  {a['local_path']}  <- {a['query']} ({a['source']})")
    if not result["assets"]:
        print("  (no usable images downloaded; the concept can still generate "
              "from the headshot + prompt alone)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
