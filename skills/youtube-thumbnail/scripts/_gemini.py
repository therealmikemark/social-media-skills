#!/usr/bin/env python3
"""
Gemini image-generation client for the youtube-thumbnail skill.

Calls the Generative Language REST API directly (no SDK dependency) to generate
thumbnail images from a text prompt plus reference images (the creator headshot
and any gathered reference assets). Returns/saves the decoded image.

Default model is gemini-2.5-flash-image ("Nano Banana"). Override with the
GEMINI_IMAGE_MODEL env var or the model= argument (e.g. gemini-3-pro-image for
higher fidelity).

The GEMINI_API_KEY is read from the environment or a known .env, never printed.
"""

import base64
import mimetypes
import os
import sys
from pathlib import Path

import requests

DEFAULT_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_ENV_CANDIDATES = [
    Path.home() / "repos" / "coaching-sales-os" / ".env",
    Path(__file__).resolve().parents[3] / "coaching-sales-os" / ".env",
    Path.cwd() / ".env",
]


def _load_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key.strip()
    for env_path in _ENV_CANDIDATES:
        if not env_path.is_file():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(
        "GEMINI_API_KEY not found in environment or known .env files."
    )


def _image_part(path: Path) -> dict:
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"inline_data": {"mime_type": mime, "data": data}}


def generate_image(
    prompt: str,
    reference_images: list | None = None,
    out_path: str | Path | None = None,
    model: str | None = None,
    aspect_ratio: str = "16:9",
    timeout: int = 120,
) -> Path:
    """Generate one image. Returns the path it was written to.

    reference_images: paths attached as input (headshot first, then assets).
    out_path: where to save; defaults to ./thumbnail.png next to cwd.
    """
    model = model or DEFAULT_MODEL
    parts: list = [{"text": prompt}]
    for ref in reference_images or []:
        p = Path(ref)
        if p.is_file():
            parts.append(_image_part(p))

    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect_ratio},
        },
    }

    url = f"{API_BASE}/{model}:generateContent?key={_load_key()}"
    resp = requests.post(url, json=body, timeout=timeout)
    if resp.status_code != 200:
        # Surface the API message but never the URL (carries the key).
        try:
            msg = resp.json().get("error", {}).get("message", resp.text[:300])
        except Exception:
            msg = resp.text[:300]
        raise RuntimeError(f"Gemini {model} HTTP {resp.status_code}: {msg}")

    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data}")

    img_b64 = None
    out_mime = "image/png"
    for part in candidates[0].get("content", {}).get("parts", []):
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            img_b64 = inline["data"]
            out_mime = inline.get("mimeType") or inline.get("mime_type") or out_mime
            break
    if not img_b64:
        # Model sometimes refuses and returns only text; surface it.
        texts = [p.get("text", "") for p in candidates[0].get("content", {}).get("parts", [])]
        raise RuntimeError(f"No image in response. Model said: {' '.join(texts)[:300]}")

    ext = ".png" if "png" in out_mime else ".jpg"
    if out_path is None:
        out_path = Path.cwd() / f"thumbnail{ext}"
    out_path = Path(out_path)
    if out_path.suffix == "":
        out_path = out_path.with_suffix(ext)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(img_b64))
    return out_path


if __name__ == "__main__":
    # Smoke test: python3 _gemini.py "<prompt>" [reference_image ...]
    prompt = sys.argv[1] if len(sys.argv) > 1 else (
        "Generate a YouTube thumbnail at 1280x720. Dark navy background, bold white "
        "sans-serif text reading 'IT WORKS', a glowing teal upward arrow on the right. "
        "High contrast, readable on mobile."
    )
    refs = sys.argv[2:]
    out = generate_image(prompt, reference_images=refs, out_path=Path.cwd() / "smoke_thumbnail")
    from PIL import Image
    im = Image.open(out)
    print(f"OK wrote {out} | {im.size[0]}x{im.size[1]} {im.mode} | model={DEFAULT_MODEL}")
