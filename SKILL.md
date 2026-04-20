---
name: podcast-use
description: Edit spoken-word audio and podcasts by conversation. Use this when the user wants transcript-driven audio editing, filler removal, dead-air trimming, take selection, or podcast cleanup with Groq Whisper and ffmpeg. Produces transcripts, packed transcript views, EDL JSON, and rendered audio outputs.
---

# Podcast Use

## Purpose

This skill edits spoken-word audio with an audio-first workflow:

1. Transcribe source audio with Groq Whisper
2. Pack transcripts into a compact markdown reading view
3. Reason about structure, filler, mistakes, pacing, and cut points
4. Produce `edl.json`
5. Render final audio with `ffmpeg`
6. Build subtitles and YouTube packaging assets when requested

Do not introduce video-specific logic. This skill is for podcasts, interviews, monologues, voice notes, and other spoken audio.

## Hard Rules

1. Ask for editing intent before cutting. Confirm whether the goal is cleanup, shortening, clip extraction, or restructuring.
2. Never cut inside a word. All cuts must align to word timestamps from the transcript.
3. Pad cut edges slightly. Use a working window around 30-150ms to avoid clipped consonants and timestamp drift.
4. Cache transcripts per source file in `edit/transcripts/`. Do not retranscribe unchanged files.
5. Keep all generated artifacts in the source file's `edit/` directory.
6. For multi-speaker audio, explicitly warn that Groq Whisper timestamps do not provide true diarization. Do not pretend speaker labels are reliable unless another diarization tool is added.
7. Render a preview or final output only from an approved EDL.
8. If the requested cut would destroy meaning or cadence, say so and propose a safer alternative.
9. If the user wants a YouTube package, produce all requested deliverables together: audio, subtitles, cover-image path or prompt, timestamps, show notes, and YouTube description.
10. If the material includes proper nouns, guest names, mixed-language speech, or Taiwanese, ask the user for glossary terms before final transcription.
11. If the user wants a YouTube cover image, prefer generating `edit/cover.png` from `cover_prompt.md` with Gemini unless they already have artwork.
12. If the user wants reels, ask how many they want, usually 3-5, and discuss a visual style before generating images.

## Required Tools

- `ffmpeg`
- `ffprobe`
- `uv`
- `GROQ_API_KEY` in environment or repo `.env`

## Directory Layout

```text
source_dir/
├── episode.wav
└── edit/
    ├── transcripts/
    │   └── episode.json
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

## Process

### 1. Inventory

- Check audio duration with `ffprobe`
- Identify whether the material is single-speaker or multi-speaker
- Ask the user what kind of edit they want

### 2. Transcribe

Run:

```bash
uv run helpers/transcribe_groq.py /path/to/audio.wav
```

This writes `edit/transcripts/<stem>.json`.

If the user has special names or jargon, initialize a glossary and use it:

```bash
uv run helpers/init_glossary.py --edit-dir /path/to/edit
uv run helpers/transcribe_groq.py /path/to/audio.wav --glossary /path/to/edit/glossary.txt --force
```

Glossary rules:

- one term per line
- include people, products, project names, brand names, publication names, and repeated Taiwanese terms
- use glossary-driven retranscription for final output
- do not assume ASR got mixed-language names correct

Before transcribing, ask whether the user prefers:

- `whisper-large-v3-turbo` for faster and cheaper iteration
- `whisper-large-v3` for higher accuracy

If the user does not specify, default to `whisper-large-v3-turbo`.

Explicit model selection:

```bash
uv run helpers/transcribe_groq.py /path/to/audio.wav --model whisper-large-v3-turbo
uv run helpers/transcribe_groq.py /path/to/audio.wav --model whisper-large-v3
```

### 3. Pack Transcript

Run:

```bash
uv run helpers/pack_transcripts.py --edit-dir /path/to/edit
```

Read `takes_packed.md` as the primary editing surface.

### 4. Plan

Summarize what is in the audio and propose a cut strategy in plain English. Wait for confirmation before producing or changing `edl.json`.

### 5. Build EDL

Write `edl.json` as a JSON array with:

```json
[
  {
    "source": "episode",
    "start": 12.34,
    "end": 18.91,
    "reason": "Clean explanation without hesitation"
  }
]
```

Rules:

- `source` must match the transcript stem
- `start` and `end` must fall on word boundaries
- Keep segments chronological unless the user explicitly wants restructuring
- If restructuring, explain the narrative rationale first

### 6. Render

Run:

```bash
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit
```

This renders `edit/final.mp3` by default.

Default render processing is tuned for spoken-word audio:

- broadband denoise
- high-pass filtering for low rumble
- low-pass filtering for hiss control
- light compression for level consistency
- loudness normalization for podcast playback

If the source is already mastered, disable filters selectively rather than stacking unnecessary processing.

### 7. Subtitles

If the user wants subtitles or a YouTube package, run:

```bash
uv run helpers/build_subtitles.py /path/to/audio.wav --edit-dir /path/to/edit
```

This writes `edit/final.srt` aligned to the rendered output timeline.

### 8. Cover Image

If the user already has art, ask them where the image lives and use it.

Recommended paths:

- `edit/cover.png`
- `edit/cover.jpg`

If the user wants AI-generated art:

- Write `edit/cover_prompt.md`
- Make it specific to the episode
- Optimize for 16:9 YouTube framing
- Include title treatment guidance only if the image model can handle text well; otherwise recommend adding text later in a design tool

Generate the image:

```bash
uv run helpers/generate_gemini_image.py --prompt-file /path/to/edit/cover_prompt.md --output /path/to/edit/cover.png
```

Notes:

- This repo defaults to a configurable primary Gemini image model with fallback to `gemini-2.5-flash-image`
- If the primary model is unavailable, it should fall back automatically
- The final saved image is cropped and resized for the target frame

### 9. Static YouTube Video

If the user wants an upload-ready video, run:

```bash
uv run helpers/render_youtube_video.py /path/to/audio.wav --edit-dir /path/to/edit --image /path/to/cover.png --burn-subtitles
```

This writes `edit/final.mp4`.

### 9A. Reels

If the user wants reels:

1. Ask how many reels they want, usually `3` to `5`
2. Ask whether they have a visual style in mind
3. If not, propose a few styles such as documentary editorial, cinematic philosophical, or bold modern collage
4. Initialize `reels_plan.json`
5. Fill in clips, hook lines, titles, and image prompts
6. Render with generated images and subtitles

Commands:

```bash
uv run helpers/init_reels_plan.py --edit-dir /path/to/edit
uv run helpers/render_reels.py /path/to/audio.wav --edit-dir /path/to/edit --generate-images
```

Each reel should usually:

- be 30 to 60 seconds
- focus on one strong idea
- have a clear hook in the first seconds
- use a mobile-first vertical image
- include subtitles

### 10. Metadata Deliverables

When requested, write these files in `edit/`:

- `show_notes.md`
- `timestamps.txt`
- `youtube_description.md`
- `cover_prompt.md` when image generation is needed

Use the packed transcript and approved edit strategy to draft them.

You may initialize the file set first:

```bash
uv run helpers/init_deliverables.py /path/to/audio.wav --edit-dir /path/to/edit
```

Rules:

- `timestamps.txt` should use output-timeline times, not original source times
- `youtube_description.md` should start with a clean hook and episode summary, then timestamps, then links or placeholders
- `show_notes.md` should be more detailed than the YouTube description
- If links, sponsors, or CTAs are unknown, leave clear placeholders rather than inventing them

## Editing Guidance

- Prefer removing dead air, repeated starts, verbal slips, and obvious throat-clearing first
- Preserve punchlines, emotional beats, and breaths that support cadence
- For podcasts, do not over-tighten everything into ad-read pacing
- For clip extraction, optimize for a complete thought and a clean ending
- If the user wants publication-ready output, recommend a separate mastering pass after structural editing
- For YouTube uploads, recommend checking subtitle readability and cover-image legibility before publishing

## Metadata Writing Guidance

### `show_notes.md`

- 1-2 paragraph summary
- key topics
- important quotes or takeaways
- optional action items or resources

### `timestamps.txt`

- one topic per line
- format `00:00 Topic`
- based on the edited output order

### `youtube_description.md`

- first 2 lines should stand on their own
- then a concise summary
- then timestamps
- then optional resource links or placeholders

### `cover_prompt.md`

Include:

- episode title or working title
- guest or host identity
- visual mood
- 16:9 composition guidance
- background elements
- typography instructions if desired
- negative prompt

## Notes On Groq Whisper

- `whisper-large-v3-turbo` is good for fast, low-cost transcript-driven editing
- If transcript accuracy matters more than speed, consider `whisper-large-v3`
- Word timestamps are available
- Native speaker diarization is not
