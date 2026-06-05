#!/usr/bin/env python3
"""
Compose generated thumbnails into a labeled 2x2 comparison grid.

Takes the generated thumbnails for a run (the four concepts, or N variations) and
lays them out in a grid with a corner label on each so the user can pick a favourite
at a glance.

Usage:
    # grid of the four concepts in RUN_DIR/generated/
    python3 make_grid.py RUN_DIR

    # grid of variations in RUN_DIR/generated/variations/
    python3 make_grid.py RUN_DIR --variations

    # or pass explicit image paths
    python3 make_grid.py --images a.png b.png c.png d.png --out grid.png

Writes RUN_DIR/grid.png (or variations_grid.png) and prints the path.
"""

import argparse
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CELL_W, CELL_H = 640, 360  # half a 1280x720 thumbnail; grid stays a sane size
GUTTER = 12
LABEL_BG = (16, 16, 16)
LABEL_FG = (255, 255, 255)


def _label_font(size: int) -> ImageFont.FreeTypeFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_label(cell: Image.Image, text: str) -> None:
    draw = ImageDraw.Draw(cell)
    font = _label_font(34)
    pad = 10
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.rectangle([0, 0, tw + pad * 2, th + pad * 2], fill=LABEL_BG)
    draw.text((pad, pad - bbox[1]), text, fill=LABEL_FG, font=font)


def build_grid(images: list[Path], out_path: Path, labels: list[str] | None = None) -> Path:
    images = [p for p in images if Path(p).is_file()]
    if not images:
        raise SystemExit("No images to place in the grid.")
    if labels is None:
        labels = [Path(p).stem.upper() for p in images]

    cols = 2 if len(images) > 1 else 1
    rows = math.ceil(len(images) / cols)
    grid_w = cols * CELL_W + (cols + 1) * GUTTER
    grid_h = rows * CELL_H + (rows + 1) * GUTTER
    canvas = Image.new("RGB", (grid_w, grid_h), (40, 40, 40))

    for idx, (img_path, label) in enumerate(zip(images, labels)):
        cell = Image.open(img_path).convert("RGB").resize((CELL_W, CELL_H), Image.LANCZOS)
        _draw_label(cell, label)
        r, c = divmod(idx, cols)
        x = GUTTER + c * (CELL_W + GUTTER)
        y = GUTTER + r * (CELL_H + GUTTER)
        canvas.paste(cell, (x, y))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return out_path


def _collect(gen_dir: Path) -> list[Path]:
    return sorted(p for p in gen_dir.glob("*.png") if p.name != "grid.png")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?")
    ap.add_argument("--variations", action="store_true", help="grid the variations subfolder")
    ap.add_argument("--images", nargs="+", help="explicit image paths")
    ap.add_argument("--out", help="output path")
    args = ap.parse_args()

    if args.images:
        images = [Path(p) for p in args.images]
        out = Path(args.out or "grid.png")
    else:
        if not args.run_dir:
            raise SystemExit("Provide RUN_DIR or --images.")
        run_dir = Path(args.run_dir)
        if args.variations:
            images = _collect(run_dir / "generated" / "variations")
            out = Path(args.out or run_dir / "variations_grid.png")
        else:
            images = _collect(run_dir / "generated")
            out = Path(args.out or run_dir / "grid.png")

    written = build_grid(images, out)
    print(f"GRID: {written}  ({len(images)} images)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
