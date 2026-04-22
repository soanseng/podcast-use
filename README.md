# podcast-use

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![uv](https://img.shields.io/badge/package%20manager-uv-5C5CFF.svg)](https://github.com/astral-sh/uv)
[![ffmpeg](https://img.shields.io/badge/audio-ffmpeg-007808.svg)](https://ffmpeg.org/)
[![Groq Whisper](https://img.shields.io/badge/STT-Groq%20Whisper-F55036.svg)](https://console.groq.com/docs/speech-to-text)
[![Gemini Image](https://img.shields.io/badge/images-Gemini-4285F4.svg)](https://ai.google.dev/gemini-api/docs/image-generation)
[![OpenAI Image](https://img.shields.io/badge/images-OpenAI-412991.svg)](https://developers.openai.com/api/docs/models/gpt-image-2)

[繁體中文 README](README.zh-TW.md)

License: [MIT](LICENSE)

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
- In Codex, prefers built-in image generation for cover art; local helpers default to OpenAI `gpt-image-2`
- Generates square podcast cover art
- Renders vertical reels with subtitles and generated visuals
- Produces packaging artifacts for show notes, timestamps, and YouTube description

## Current limitations

- Groq Whisper does not provide true speaker diarization in this workflow.
- Two-person or multi-person conversations can still be transcribed and edited by content.
- Speaker labels are not reliable enough to present as ground truth.
- Do not assume the skill can safely output formal `Speaker A / Speaker B` attribution without human review.
- For interviews or conversations with multiple speakers, use this skill for transcript-driven editing, not authoritative speaker labeling.
- If you need publication-grade speaker attribution, plan for manual review.

## Prerequisites

You need:

- `ffmpeg`
- Python `3.10+`
- `uv`

Platform setup:

Ubuntu / Debian:

```bash
sudo apt update
sudo apt install -y ffmpeg python3 python3-pip
curl -LsSf https://astral.sh/uv/install.sh | sh
```

macOS:

```bash
brew install ffmpeg python uv
```

Windows:

- install `ffmpeg` and add it to `PATH`
- install Python `3.10+`
- install `uv` from https://docs.astral.sh/uv/getting-started/installation/

Arch Linux:

```bash
sudo pacman -S ffmpeg python uv
```

Then set up the repo:

```bash
git clone https://github.com/soanseng/podcast-use.git
cd podcast-use
uv sync
cp .env.example .env
```

Configure API keys in `.env`:

```bash
$EDITOR .env
```

Default key requirements:

- `GROQ_API_KEY` is required for transcription
- `OPENAI_API_KEY` is needed only if you use local OpenAI image helpers
- `GEMINI_API_KEY` is optional and only needed if you choose the Gemini image workflow
- In Codex sessions, you can often generate images with Codex directly and save them into the edit directory

## Install as a skill

### Install by chat

If you want chat-first installation, copy one of these prompts into your client:

- Claude Code, English: [prompts/install_claude_code_en.txt](prompts/install_claude_code_en.txt)
- Claude Code, zh-TW: [prompts/install_claude_code_zh-TW.txt](prompts/install_claude_code_zh-TW.txt)
- Codex, English: [prompts/install_codex_en.txt](prompts/install_codex_en.txt)
- Codex, zh-TW: [prompts/install_codex_zh-TW.txt](prompts/install_codex_zh-TW.txt)

This is the intended "one-shot" flow for users who prefer to install by conversation instead of manual shell steps.

### Install by shell

Paste one of these into your client shell after cloning the repo.

Claude Code:

```bash
./scripts/install_skill.sh claude
```

Codex:

```bash
./scripts/install_skill.sh codex
```

If you want the full clone-and-install flow in one paste:

Claude Code:

```bash
git clone https://github.com/soanseng/podcast-use.git && cd podcast-use && ./scripts/install_skill.sh claude
```

Codex:

```bash
git clone https://github.com/soanseng/podcast-use.git && cd podcast-use && ./scripts/install_skill.sh codex
```

Manual Claude Code install:

```bash
ln -s "$(pwd)" ~/.claude/skills/podcast-use
```

Manual Codex install:

```bash
ln -s "$(pwd)" "${CODEX_HOME:-$HOME/.codex}/skills/podcast-use"
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
- speech leveling before compression
- high-pass filter at `80Hz`
- low-pass filter at `13.5kHz`
- spoken-word equalizer shaping
- light compression
- `loudnorm` targeting podcast-style delivery
- light post-processing denoise
- final limiter for peak control

This is intended to approximate a practical Audacity-style speech chain:

- denoise
- normalize
- equalizer
- compress
- normalize
- denoise
- limiter

It is not a bit-for-bit match for Audacity effects, but the processing intent is close and is tuned for spoken-word delivery.

Disable pieces when needed:

```bash
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-denoise
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-leveler
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-eq
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-compressor
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-normalize
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-post-denoise
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-limiter
```

Build subtitles:

```bash
uv run helpers/build_subtitles.py /path/to/audio.wav --edit-dir /path/to/edit
```

In Codex, the default next step should be to review and refine `edit/final.srt` using the transcript, glossary, and context from the episode. The preferred rule is:

- keep the same cue count
- keep the same cue timing
- refine text only
- prefer Traditional Chinese for zh-Hant projects
- preserve mixed-language names and glossary terms

If you want a scripted post-pass, use the optional Groq helper:

```bash
uv run helpers/refine_srt_groq.py /path/to/edit/final.srt --edit-dir /path/to/edit
```

Defaults for the helper:

- primary model: `qwen/qwen3-32b`
- fallback model: `openai/gpt-oss-120b`
- language hint: `zh-Hant`

In Codex, prefer the built-in image tool first and save the result to `edit/cover.png`.

If you need a local helper, generate a YouTube cover image with the default OpenAI path:

```bash
uv run helpers/generate_image.py \
  --prompt-file /path/to/edit/cover_prompt.md \
  --output /path/to/edit/cover.png
```

Explicit OpenAI `gpt-image-2`:

```bash
uv run helpers/generate_image.py \
  --provider openai \
  --model gpt-image-2 \
  --prompt-file /path/to/edit/cover_prompt.md \
  --output /path/to/edit/cover.png
```

Gemini compatibility path:

```bash
uv run helpers/generate_gemini_image.py \
  --prompt-file /path/to/edit/cover_prompt.md \
  --output /path/to/edit/cover.png
```

Generate a podcast cover image:

- recommended aspect ratio: `1:1`
- recommended minimum size: `1400 x 1400`
- suggested path: `edit/podcast_cover.png`

If you want both formats, treat them separately:

- YouTube cover: `16:9`
- podcast cover: `1:1`, at least `1400 x 1400`

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

This default reel helper path uses OpenAI `gpt-image-2`.

Render reels with Gemini-generated images:

```bash
uv run helpers/render_reels.py /path/to/audio.wav \
  --edit-dir /path/to/edit \
  --generate-images \
  --image-provider gemini \
  --image-model gemini-3.1-flash-image-preview
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
├── podcast_cover_prompt.md
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
- Put the podcast cover at `edit/podcast_cover.png` or `edit/podcast_cover.jpg`
- If the user wants AI generation, have Claude write `edit/cover_prompt.md` first

Podcast cover suggestions:

- aspect ratio: `1:1`
- at least `1400 x 1400`
- avoid tiny text or edge-cropped details
- default to single-episode cover art unless the user explicitly wants show-level branding

If the user wants a podcast cover, write a separate `edit/podcast_cover_prompt.md` tuned for square framing instead of reusing a 16:9 YouTube prompt unchanged.

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

## Image generation providers

Default behavior in this repo:

- Codex sessions: prefer Codex built-in image generation first
- local helper provider: `openai`
- local helper primary model: `gpt-image-2`
- no local helper fallback by default

Optional OpenAI behavior:

- local helper provider: `gemini`
- local helper primary model: `gemini-3.1-flash-image-preview`
- local helper fallback model: `gemini-2.5-flash-image`

Provider notes:

- Codex can generate images interactively in-session and that is the preferred path when the skill is running inside Codex
- Local helper scripts default to OpenAI `gpt-image-2`
- Gemini remains available when you explicitly pass `--provider gemini` or `--image-provider gemini`
- `helpers/generate_gemini_image.py` remains available as a compatibility wrapper
- Codex built-in image generation is not a stable backend for these local helper scripts

Official docs:

- Gemini: https://ai.google.dev/gemini-api/docs/image-generation
- OpenAI: https://developers.openai.com/api/docs/models/gpt-image-2

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
