# podcast-use

Conversation-driven podcast editing skill for Claude Code.

This project is an audio-first fork concept inspired by `browser-use/video-use`, adapted for podcast and spoken-word editing workflows.

## What it does

- Transcribes audio with Groq Whisper
- Packs word timestamps into a compact markdown view
- Lets Claude Code reason over the transcript and produce an edit decision list
- Renders a clean audio edit with ffmpeg
- Applies spoken-word audio processing during render
- Builds subtitles as `.srt`
- Creates a static-image YouTube `.mp4`
- Generates YouTube cover art with Gemini image models
- Renders vertical reels with subtitles and generated visuals
- Produces packaging artifacts for show notes, timestamps, and YouTube description

## Arch Linux setup

Install system packages:

```bash
sudo pacman -S ffmpeg python uv
```

Sync dependencies with `uv`:

```bash
cd podcast-use
uv sync
```

Configure Groq:

```bash
cp .env.example .env
$EDITOR .env
```

## Claude Code skill install

```bash
ln -s "$(pwd)" ~/.claude/skills/podcast-use
```

## Typical workflow

Put your audio files in a directory, then from Claude Code ask it to use the `podcast-use` skill.

Manual helper usage:

```bash
uv run helpers/transcribe_groq.py /path/to/audio.wav
uv run helpers/pack_transcripts.py --edit-dir /path/to/edit
```

Choose a model explicitly when needed:

```bash
uv run helpers/transcribe_groq.py /path/to/audio.wav --model whisper-large-v3-turbo
uv run helpers/transcribe_groq.py /path/to/audio.wav --model whisper-large-v3
```

Model guidance:

- `whisper-large-v3-turbo`: faster and cheaper, good default for iterative editing
- `whisper-large-v3`: slower and more expensive, better when transcript accuracy matters more

After Claude Code writes `edl.json`, render:

```bash
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit
```

Default spoken-word processing during render:

- broadband denoise
- high-pass filter at `80Hz`
- low-pass filter at `13.5kHz`
- light compression
- `loudnorm` targeting podcast-style delivery

Disable pieces when needed:

```bash
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-denoise
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-compressor
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-normalize
```

Build subtitles:

```bash
uv run helpers/build_subtitles.py /path/to/audio.wav --edit-dir /path/to/edit
```

Generate a YouTube cover image with Gemini:

```bash
uv run helpers/generate_gemini_image.py \
  --prompt-file /path/to/edit/cover_prompt.md \
  --output /path/to/edit/cover.png
```

Render a static-image YouTube video:

```bash
uv run helpers/render_youtube_video.py /path/to/audio.wav \
  --edit-dir /path/to/edit \
  --image /path/to/cover.png \
  --burn-subtitles
```

Create metadata file skeletons:

```bash
uv run helpers/init_deliverables.py /path/to/audio.wav --edit-dir /path/to/edit
```

Create a reels plan:

```bash
uv run helpers/init_reels_plan.py --edit-dir /path/to/edit
```

Render reels with generated images:

```bash
uv run helpers/render_reels.py /path/to/audio.wav \
  --edit-dir /path/to/edit \
  --generate-images
```

Create a glossary template for names and jargon:

```bash
uv run helpers/init_glossary.py --edit-dir /path/to/edit
```

Then retranscribe with the glossary:

```bash
uv run helpers/transcribe_groq.py /path/to/audio.wav \
  --model whisper-large-v3 \
  --glossary /path/to/edit/glossary.txt \
  --force
```

## Edit output layout

```text
edit/
├── transcripts/
│   └── source.json
├── takes_packed.md
├── edl.json
├── glossary.txt
├── final.mp3
├── final.srt
├── final.mp4
├── show_notes.md
├── timestamps.txt
├── youtube_description.md
├── cover_prompt.md
├── reels_plan.json
└── reels/
```

## EDL format

`edl.json` is a JSON array:

```json
[
  {
    "source": "episode",
    "start": 1.20,
    "end": 7.80,
    "reason": "Clean opening line"
  }
]
```

## Cover image workflow

Two supported paths:

1. User-provided image
2. AI-generated image from a prompt produced by the skill

Recommended convention:

- Put the chosen image at `edit/cover.png` or `edit/cover.jpg`
- If the user wants AI generation, have Claude write `edit/cover_prompt.md` first

Before generating the cover image, ask:

- whether the user wants text baked into the image or artwork only
- what style direction they want

If the user has no style preference, propose 2 to 3 options based on the episode topic.

## Glossary workflow

For proper nouns, brand names, mixed-language terms, Taiwanese phrases, and guest names, keep:

- `edit/glossary.txt`

Put one term per line, for example:

```text
覓己
AnatoMee
陳璿丞
Claude Code
ChatGPT
Substack
```

Use glossary-driven retranscription for final episodes and subtitle passes.

## Gemini image generation

As of April 20, 2026, Google AI developer docs clearly document `gemini-2.5-flash-image` for Gemini image generation. This project also allows a configurable primary model before that fallback.

Default behavior in this repo:

- primary: `gemini-3.1-flash-image-preview`
- fallback: `gemini-2.5-flash-image`

If the primary model is unavailable, generation falls back automatically.

Official docs:

- https://ai.google.dev/gemini-api/docs/image-generation

## Reels workflow

Recommended conversation flow:

1. Ask whether the user wants reels
2. Ask how many, usually `3` to `5`
3. Propose `5` to `8` attractive candidate segments first
4. Let the user choose which `3` to `5` to make
5. Ask whether reel images should include text or be artwork only
6. Ask for a visual style, or propose 2-3 directions
7. Ask whether all reels should share one style or each reel can have a different style
8. Confirm that reels are vertical `9:16` outputs

Good default style directions:

- documentary editorial
- cinematic philosophical
- bold modern collage

Each reel entry can define:

- source audio
- start and end time
- title
- hook
- image prompt
- intro label
- style tag
- aspect ratio, usually `9:16`
- text in image or artwork only

`render_reels.py` will:

- extract the audio clip
- generate an image when requested
- build clip subtitles
- render a vertical `mp4`

## Publishing package

For a publish-ready episode, this skill should normally produce:

- `final.mp3`
- `final.srt`
- `final.mp4`
- `reels/`
- `show_notes.md`
- `timestamps.txt`
- `youtube_description.md`

Recommended order:

1. lock the edit
2. render final audio
3. build subtitles
4. create or collect cover art
5. render the YouTube video
6. choose reels and render them
7. write show notes, timestamps, and YouTube description

Suggested image prompt shape:

- topic and guest
- mood and visual direction
- composition for 16:9 YouTube frame
- text treatment guidance
- negative prompt guidance to avoid clutter or unreadable typography
