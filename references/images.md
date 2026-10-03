# Images: covers and reels

Ask before generating any image:

1. Text baked into image, or artwork only?
2. Visual style preference?
3. If no preference, propose 2–3 directions and recommend one

Standing rule: every cover and reel image includes at least one person in the
scene. This holds for all styles — cartoon, illustration, painting, collage —
with people rendered in that style. Never ship an empty-scene or object-only
visual.

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

- cyanotype blueprint (vintage Prussian-blue engineering print)
- risograph duotone (grain, misregistration, zine energy)
- hand-painted Taiwanese cinema billboard (gouache, ornate frame)
- documentary editorial
- cinematic philosophical
- bold modern collage
- minimal high contrast

Pick from the episode's content (metaphors, guests, stakes) before defaulting to
generic podcast visuals; research 2–3 references before writing the prompt.

## Generation via Codex (ChatGPT subscription, no API key)

If the local Codex CLI is signed in (`codex login status`), prefer:

```bash
uv run helpers/generate_codex_image.py \
  --prompt-file /path/to/edit/cover_prompt.md \
  --output /path/to/edit/cover.png \
  --size 1536x1024 --quality medium
```

Sizes: `1024x1024` (1:1), `1536x1024` (16:9), `1024x1536` (9:16). Quality:
`low|medium|high` (low for drafts). A typical turn costs ~30k Codex agent tokens
on top of image-gen usage. Requires `codex login` when the token expires.
## Generation priority

1. If this runtime exposes a built-in image tool (omp `xd://generate_image` via the `image` model role; Codex CLI via `generate_codex_image.py`), use it and save into `edit/`
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
- human presence (at least one person, styled to match)
- composition guidance (16:9 or 1:1)
- typography notes only if text is requested
- negative prompt (clutter, unreadable type, distorted hands/faces)

## Keys

- `OPENAI_API_KEY` for local OpenAI image helper
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` for Gemini path
- Built-in runtime image tools usually need no extra key in-session
