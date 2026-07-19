# Images: covers and reels

Ask before generating any image:

1. Text baked into image, or artwork only?
2. Visual style preference?
3. If no preference, propose 2–3 directions and recommend one

## Paths

| Asset | Path | Frame |
|-------|------|-------|
| YouTube cover | `edit/cover.png` or `.jpg` | 16:9 |
| Podcast cover | `edit/podcast_cover.png` or `.jpg` | 1:1, ≥1400×1400 |
| YouTube prompt | `edit/cover_prompt.md` | — |
| Podcast prompt | `edit/podcast_cover_prompt.md` | — |

Podcast cover defaults to **episode-specific** art unless user wants show-level branding.  
Do not reuse a 16:9 YouTube composition unchanged for square covers.

## Style directions (examples)

- documentary editorial
- cinematic philosophical
- bold modern collage
- minimal high contrast

## Generation priority

1. If the runtime has a built-in image tool (e.g. Codex), use it and save into `edit/`
2. Otherwise local helper:

```bash
uv run helpers/generate_image.py \
  --prompt-file /path/to/edit/cover_prompt.md \
  --output /path/to/edit/cover.png
```

Defaults for local helpers:

- provider: OpenAI `gpt-image-2`
- optional Gemini: `--provider gemini` or `generate_gemini_image.py`

```bash
uv run helpers/generate_image.py \
  --provider openai --model gpt-image-2 \
  --prompt-file /path/to/edit/cover_prompt.md \
  --output /path/to/edit/cover.png

uv run helpers/generate_gemini_image.py \
  --prompt-file /path/to/edit/cover_prompt.md \
  --output /path/to/edit/cover.png
```

Reel images:

```bash
uv run helpers/render_reels.py /path/to/audio.wav --edit-dir /path/to/edit --generate-images
# Gemini path:
uv run helpers/render_reels.py /path/to/audio.wav --edit-dir /path/to/edit \
  --generate-images --image-provider gemini --image-model gemini-3.1-flash-image-preview
```

## Prompt contents

Include:

- episode title / working title
- host or guest identity if relevant
- mood and palette
- composition guidance (16:9 or 1:1)
- typography notes only if text is requested
- negative prompt (clutter, unreadable type, distorted hands/faces)

## Keys

- `OPENAI_API_KEY` for local OpenAI image helper
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` for Gemini path
- Built-in runtime image tools usually need no extra key in-session
