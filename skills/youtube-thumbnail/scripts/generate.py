#!/usr/bin/env python3
"""
Parallel thumbnail generation for the youtube-thumbnail skill.

Reads a concepts spec (written by the skill in Stage 4) and generates every
concept in parallel via Gemini, exporting each at exactly 1280x720. Also supports
the iteration loop: regenerate one concept as N variations with an optional tweak.

concepts.json format (in the run directory):
{
  "topic": "...",
  "concepts": [
    {"label": "A", "prompt": "<full image prompt>",
     "headshot": "/path/to/headshot.jpg",
     "assets": ["/path/logo.png", "/path/dashboard.png"]},
    ...
  ]
}

Usage:
    # generate all four concepts in parallel
    python3 generate.py RUN_DIR

    # iterate: 4 variations of concept B, optionally nudged
    python3 generate.py RUN_DIR --concept B --variations 4 --tweak "warmer palette, drop the number"

Outputs RUN_DIR/generated/<label>.png (or variations/<label>N.png) and a manifest.
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

from _gemini import generate_image

THUMB_W, THUMB_H = 1280, 720


def to_thumbnail_size(path: Path) -> None:
    """Resize+center-crop an image in place to exactly 1280x720 (cover fit, no distortion)."""
    im = Image.open(path).convert("RGB")
    src_w, src_h = im.size
    scale = max(THUMB_W / src_w, THUMB_H / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    im = im.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - THUMB_W) // 2
    top = (new_h - THUMB_H) // 2
    im = im.crop((left, top, left + THUMB_W, top + THUMB_H))
    im.save(path)


def _gen_one(label: str, concept: dict, out_path: Path) -> dict:
    """Generate a single concept image. Returns a result record (never raises)."""
    refs = []
    if concept.get("headshot"):
        refs.append(concept["headshot"])
    refs.extend(concept.get("assets", []))
    try:
        written = generate_image(concept["prompt"], reference_images=refs, out_path=out_path)
        to_thumbnail_size(written)
        return {"label": label, "ok": True, "path": str(written)}
    except Exception as e:  # one concept failing must not sink the batch
        return {"label": label, "ok": False, "error": str(e)}


def _load_spec(run_dir: Path) -> dict:
    spec_path = run_dir / "concepts.json"
    if not spec_path.is_file():
        raise SystemExit(f"No concepts.json in {run_dir}. Write the Stage 4 concepts there first.")
    return json.loads(spec_path.read_text())


def generate_all(run_dir: Path) -> list[dict]:
    spec = _load_spec(run_dir)
    gen_dir = run_dir / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)

    jobs = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for c in spec["concepts"]:
            label = c["label"]
            fut = pool.submit(_gen_one, label, c, gen_dir / f"{label}.png")
            jobs[fut] = label
        results = [f.result() for f in as_completed(jobs)]

    results.sort(key=lambda r: r["label"])
    (gen_dir / "manifest.json").write_text(json.dumps(results, indent=2))
    return results


def generate_variations(run_dir: Path, label: str, n: int, tweak: str) -> list[dict]:
    spec = _load_spec(run_dir)
    concept = next((c for c in spec["concepts"] if c["label"] == label), None)
    if concept is None:
        raise SystemExit(f"Concept {label!r} not found in concepts.json")

    concept = dict(concept)
    if tweak:
        concept["prompt"] = concept["prompt"] + f"\n\nVariation instruction: {tweak}"

    var_dir = run_dir / "generated" / "variations"
    var_dir.mkdir(parents=True, exist_ok=True)

    jobs = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i in range(1, n + 1):
            vlabel = f"{label}{i}"
            fut = pool.submit(_gen_one, vlabel, concept, var_dir / f"{vlabel}.png")
            jobs[fut] = vlabel
        results = [f.result() for f in as_completed(jobs)]

    results.sort(key=lambda r: r["label"])
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--concept", help="iterate: regenerate this concept label")
    ap.add_argument("--variations", type=int, default=4, help="number of variations (with --concept)")
    ap.add_argument("--tweak", default="", help="variation nudge appended to the prompt")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)

    if args.concept:
        results = generate_variations(run_dir, args.concept, args.variations, args.tweak)
        print(f"VARIATIONS of {args.concept}:")
    else:
        results = generate_all(run_dir)
        print("GENERATED concepts:")

    ok = [r for r in results if r["ok"]]
    for r in results:
        if r["ok"]:
            print(f"  {r['label']}: {r['path']}")
        else:
            print(f"  {r['label']}: FAILED - {r['error']}")
    print(f"\n{len(ok)}/{len(results)} succeeded.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
