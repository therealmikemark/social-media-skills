---
name: youtube-thumbnail
description: >
  Research-driven YouTube thumbnail engine. Finds the highest-performing competitor
  thumbnails for the topic (SerpAPI, ranked by views/month), extracts their winning
  patterns, works the Desire Loop to produce four distinct concepts that deliberately
  break the pattern, gathers reference assets, then generates all four in parallel via
  Gemini (Nano Banana) into a 1280x720 2x2 comparison grid with a fast iteration loop.
  Uses a reference photo of the creator and brand colours. Use whenever the user says
  "thumbnail", "youtube thumbnail", "build me a thumbnail", or wants a video cover image
  before writing the script. Sells the video before anyone hears a word of the script.
---

# YouTube Thumbnail

A research → strategy → concept engine. Don't just template a prompt — find what is
already winning in this niche, then beat it.

## CRITICAL: Auto-start on load

When this skill triggers, go straight to Stage 1. Scripts live in `scripts/`,
frameworks in `references/`.

## Stage 1. Gather inputs

Find the brand/reference config. Look in this order:
1. `thumbnail-config.md` in the project root
2. `brand-kit.md` — reference image path + brand colours
3. `about-me.md` — creator name and positioning

Then collect:
- **Video title or topic** (required). If they only have a topic, offer to propose 3
  click-worthy titles first.
- **Any must-include assets** — logos, product shots, screenshots, a specific number.
- **Reference photo** — if a path is stored, pre-fill it. Otherwise ask for a clear
  headshot they will reuse across videos for brand consistency.

## Stage 2. Select the headshot

Look for a `headshots/` folder in the project (or this skill's `headshots/`). The
convention is one image per expression: `surprised.jpg`, `happy.jpg`, `pointing.jpg`,
`confident.jpg`, `confused.jpg`. Pick the expression that matches each concept's
emotional tone (set in Stage 4).

If only a single photo exists, use it for all concepts and note to the user that adding
expression variants (surprised / pointing / confident) will improve results.

## Stage 3. Research the competition

Run the research script with the topic:

```bash
python3 scripts/research.py "<video topic>" --top 6
```

It searches YouTube, ranks results by **views-per-month** (recent breakouts beat stale
evergreen hits), downloads the top thumbnails, and writes a manifest. Note the printed
`RUN_DIR` — every later stage writes into it.

Then **Read each downloaded thumbnail** (paths are printed and listed in
`research/manifest.json`) and extract the winning pattern:
- Dominant colours and background treatment (bright vs dark, flat vs scene)
- Face placement, size, expression
- Text style, length, position, devices (strikethrough, numbers, arrows)
- Recurring composition tropes

Write a short **pattern summary** and a **differentiation directive**: how to stand out.
If everyone is bright/white, go dark cinematic. If everyone crops face-right with yellow
text, do something else. Standing out beats looking good. (See
`references/thumbnail-principles.md`.)

## Stage 4. Work the Desire Loop → four concepts

Using `references/desire-loop.md`, work the loop for this video's viewer:
**Desired Outcome → Pain Point → Solution → Curiosity Gap.**

Then produce **four distinct concepts**. Make them genuinely different angles (e.g.
number-led, before/after, contrarian "you're doing it wrong", authority/proof), each
honouring the differentiation directive from Stage 3. For each concept output:

```
CONCEPT [A-D]: [one-line angle]

Desire Loop: outcome / pain / solution / gap (one line each)
Hook text: "[3-5 words, from the gap]"
Expression: [headshot to use]
Composition: [face side + %, focal payoff element, text placement]
Colour palette: [primary hex], [accent hex], [background hex]  (break the pattern)
Supporting element: [logo / product / number / metaphor]
```

Present all four, then ask the user to pick favourites or request changes.

## Stage 5. Gather reference assets

For each approved concept, decide what supporting imagery it needs (logos, product
shots, screenshots, visual metaphors) and gather it:

```bash
python3 scripts/gather_assets.py "<RUN_DIR>" A "Claude AI logo" "marketing dashboard"
```

Pass the run directory from Stage 3, the concept label, then one search phrase per asset.
Downloaded files land in `RUN_DIR/assets/<concept>/` and are listed in
`assets/manifest.json`. Concepts with no external assets (face + text only) can skip this.
Skip any asset query for which nothing usable downloads — the concept still generates from
the headshot and prompt alone.

## Stage 6. Generate

Two paths. Prefer automatic generation when `GEMINI_API_KEY` is available.

**Automatic (Gemini / Nano Banana).** Write the four concepts to `RUN_DIR/concepts.json`,
then generate all of them in parallel:

```json
// RUN_DIR/concepts.json
{
  "topic": "<topic>",
  "concepts": [
    {"label": "A", "prompt": "<full image prompt>",
     "headshot": "<path to selected headshot>",
     "assets": ["<gathered asset>", "..."]},
    {"label": "B", "prompt": "...", "headshot": "...", "assets": []}
  ]
}
```

```bash
python3 scripts/generate.py "<RUN_DIR>"          # 4 concepts in parallel -> generated/<label>.png, exact 1280x720
python3 scripts/make_grid.py "<RUN_DIR>"         # -> RUN_DIR/grid.png (labeled 2x2)
```

Read `RUN_DIR/grid.png` and show the user the four concepts. The default model is
`gemini-2.5-flash-image`; set `GEMINI_IMAGE_MODEL=gemini-3-pro-image` for higher fidelity.
Each concept's prompt should bake in the full brief from Stage 4 (composition, hook text,
palette, supporting element) and the brand guards below.

**Manual bridge.** If keys are not set, output a Gemini image prompt per concept for the
user to paste:

```
Using the attached reference photo of me, generate a YouTube thumbnail at 1280 x 720
pixels (16:9).

Composition:
- Place me [left / right / centre] filling [30-50]% of the frame
- Expression: [tone details]
- Gaze: [direction]

Text:
- Display "[hook phrase]" in large bold sans-serif typography
- Text colour: [hex]; outline: [colour/thickness for readability]
- Placement: [specific area, never bottom-right]

Colour palette:
- Primary [hex], Accent [hex], Background [hex] — [treatment]

Supporting element: [specific description]

Constraints:
- Face clear and sharp; text readable at 320px wide (mobile)
- No watermarks, no YouTube UI, no bottom-right corner text
- High contrast between face, text, and background
```

Tell the user:
> Paste each into a new Gemini chat, attach your reference photo, enable Create Image,
> select Nano Banana, generate at 1280x720.

## Stage 7. Iterate

After the user reviews the grid, refine. To spin a favourite into four fresh takes:

```bash
python3 scripts/generate.py "<RUN_DIR>" --concept B --variations 4 \
  --tweak "warmer palette, simplify the text, bigger number"
python3 scripts/make_grid.py "<RUN_DIR>" --variations   # -> RUN_DIR/variations_grid.png
```

The `--tweak` text is appended to that concept's prompt, so the user's notes ("remove the
text", "change to red", "different layout") flow straight through. Read the variations grid,
show it, and repeat until the user picks a winner. The chosen file in
`RUN_DIR/generated/` (or `variations/`) is the final 1280x720 thumbnail.

## Rules

- 1280x720 pixels (16:9). YouTube's native thumbnail size.
- Never put the reference photo path in the prompt itself — the user attaches it separately.
- Never more than 6 words of text; 5 ideal, 3 best.
- Face is always a visible focal point. No face-hidden compositions.
- Never use em dashes.
- British English in prose unless voice.md says otherwise (hook text follows the title).
- If `brand-kit.md` exists, read it and use exact brand colours.
- Always ground concepts in the Stage 3 research — never skip straight to generation.
- Recommend a consistent thumbnail style across videos for channel recognition.
