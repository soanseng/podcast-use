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
7. Refine subtitle wording after `final.srt` is generated when subtitle quality matters

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
11. If the user wants a YouTube cover image and you are running inside Codex, prefer using Codex's built-in image generation first and save the result to `edit/cover.png`. If local helper scripts are needed, default to OpenAI `gpt-image-2`. Gemini remains an optional fallback or compatibility path.
11A. If the user wants podcast cover art, treat it as a separate deliverable from the YouTube cover. Default to a square `1:1` image, at least `1400 x 1400`, and keep its prompt in `edit/podcast_cover_prompt.md`. Unless the user explicitly says they want show-level branding, assume this is episode-specific cover art for a single episode, not the master cover for the whole podcast.
12. If the user wants reels, ask how many they want, usually 3-5, and discuss a visual style before generating images.
13. Before creating reels, propose attractive candidate segments first. Do not silently choose all reel clips without user review unless the user explicitly delegates the choice.
14. Before generating any image, explicitly ask whether the user wants text baked into the image. Do not assume they want text on the image.
15. Before generating any cover or reel image, explicitly ask for the desired visual style. If the user has no preference, propose 2 to 3 style directions based on the episode topic and ask them to choose.
16. When the user is preparing to publish, default to offering the full publishing package: long-form YouTube video, reels, `show_notes.md`, `timestamps.txt`, and `youtube_description.md`.
17. For two-person or multi-person conversations, default to content editing and transcript packaging, not authoritative speaker attribution. Do not present speaker labels as reliable ground truth unless the user explicitly accepts manual review.
18. After generating `final.srt`, if you are running inside Codex, default to refining the subtitle text using `final.srt`, transcript files, and `glossary.txt`. Do not change cue count or timestamps unless the user explicitly asks for subtitle re-timing.

## Required Tools

- `ffmpeg`
- `ffprobe`
- `uv`
- `GROQ_API_KEY` in environment or repo `.env`
- `OPENAI_API_KEY` only if using local OpenAI image helpers
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` only if using the optional Gemini image workflow

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
    ├── podcast_cover_prompt.md
    ├── reels_plan.json
    └── reels/
```

## Process

### 1. Inventory

- Check audio duration with `ffprobe`
- Identify whether the material is single-speaker or multi-speaker
- Ask the user what kind of edit they want
- If the material is multi-speaker, warn that this workflow does not provide true diarization and that speaker attribution should be treated as provisional at best

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
- speech leveling before compression
- high-pass filtering for low rumble
- low-pass filtering for hiss control
- spoken-word equalizer shaping
- light compression for level consistency
- loudness normalization for podcast playback
- a light post-processing denoise pass
- final limiting for peak safety

This chain is meant to approximate the practical intent of an Audacity-style flow such as:

- noise reduction
- normalize
- equalizer
- compress
- normalize
- noise reduction
- limiter

If the source is already mastered, disable filters selectively rather than stacking unnecessary processing.

### 7. Subtitles

If the user wants subtitles or a YouTube package, run:

```bash
uv run helpers/build_subtitles.py /path/to/audio.wav --edit-dir /path/to/edit
```

This writes `edit/final.srt` aligned to the rendered output timeline.

If subtitle wording quality matters, the default Codex step after this is:

- read `edit/final.srt`
- read `edit/transcripts/*.json`
- read `edit/glossary.txt` if present
- refine wording only
- keep cue count and timestamps unchanged
- prefer Traditional Chinese for zh-Hant projects
- preserve names, brands, Taiwanese, and mixed-language terms
- if uncertain, leave the original wording

Optional automated post-pass with Groq:

```bash
uv run helpers/refine_srt_groq.py /path/to/edit/final.srt --edit-dir /path/to/edit
```

Default helper models:

- primary: `qwen/qwen3-32b`
- fallback: `openai/gpt-oss-120b`

### 8. Cover Image

If the user already has art, ask them where the image lives and use it.

Recommended paths:

- `edit/cover.png`
- `edit/cover.jpg`
- `edit/podcast_cover.png`
- `edit/podcast_cover.jpg`

If the user wants AI-generated art:

- Write `edit/cover_prompt.md`
- Make it specific to the episode
- Optimize for 16:9 YouTube framing
- Include title treatment guidance only if the image model can handle text well; otherwise recommend adding text later in a design tool
- Ask whether they want text baked into the image or a clean artwork-only image
- Ask what style they want
- If they do not know, propose 2 to 3 directions based on the topic

Suggested questions before cover generation:

- Do you want text inside the image, or artwork only?
- What style do you want for the cover?

If the user also wants podcast cover art:

- write a separate `edit/podcast_cover_prompt.md`
- optimize for square `1:1` framing
- target at least `1400 x 1400`
- default to episode-specific art, not whole-show brand art
- avoid reusing a 16:9 YouTube composition unchanged

If the user has no style preference, propose options such as:

- documentary editorial
- cinematic philosophical
- bold modern collage
- minimal high contrast

In Codex, prefer the built-in image tool first and save the chosen output to `edit/cover.png`.

If a local helper is needed, generate the image with the default OpenAI path:

```bash
uv run helpers/generate_image.py --prompt-file /path/to/edit/cover_prompt.md --output /path/to/edit/cover.png
```

Or explicitly with OpenAI `gpt-image-2`:

```bash
uv run helpers/generate_image.py --provider openai --model gpt-image-2 --prompt-file /path/to/edit/cover_prompt.md --output /path/to/edit/cover.png
```

Gemini compatibility path:

```bash
uv run helpers/generate_gemini_image.py --prompt-file /path/to/edit/cover_prompt.md --output /path/to/edit/cover.png
```

Notes:

- In Codex sessions, prefer built-in image generation before local helpers
- Local helper scripts default to OpenAI `gpt-image-2`
- Gemini is available as an optional compatibility path with fallback to `gemini-2.5-flash-image`
- The final saved image is cropped and resized for the target frame
- Codex built-in image generation is not a stable backend for `uv run ...` helper automation, so scripted flows must still call a provider API directly

### 9. Static YouTube Video

If the user wants an upload-ready video, run:

```bash
uv run helpers/render_youtube_video.py /path/to/audio.wav --edit-dir /path/to/edit --image /path/to/cover.png --burn-subtitles
```

This writes `edit/final.mp4`.

### 9A. Reels

If the user wants reels:

1. Ask how many reels they want, usually `3` to `5`
2. Read the transcript and propose `5` to `8` attractive candidate segments first
3. For each candidate, include:
   - source file
   - start and end time
   - a short hook title
   - why it works as a reel
4. Ask the user to choose which segments to turn into reels
5. Ask whether they have a visual style in mind
6. If not, propose a few styles such as documentary editorial, cinematic philosophical, or bold modern collage
7. Make sure the user understands reels are vertical `9:16` outputs
8. Ask whether they want text baked into the reel images or clean artwork-only images
9. If they want different reel images to have different styles, plan that explicitly
10. Initialize `reels_plan.json`
11. Fill in clips, hook lines, titles, image prompts, and style tags
12. Render with generated images and subtitles

Commands:

```bash
uv run helpers/init_reels_plan.py --edit-dir /path/to/edit
uv run helpers/render_reels.py /path/to/audio.wav --edit-dir /path/to/edit --generate-images
```

The default reel helper path uses OpenAI `gpt-image-2`.

Gemini reel images:

```bash
uv run helpers/render_reels.py /path/to/audio.wav --edit-dir /path/to/edit --generate-images --image-provider gemini --image-model gemini-3.1-flash-image-preview
```

Each reel should usually:

- be 30 to 60 seconds
- focus on one strong idea
- have a clear hook in the first seconds
- use a mobile-first vertical `9:16` image
- include subtitles

When discussing reel imagery, ask about:

- style direction
- whether the user wants text baked into the image or clean artwork only
- whether the look should be photographic, illustrative, editorial, collage, or minimal
- whether all reels should share one style or each reel can use a different style

If the user has no preference, propose 2 to 3 concrete style directions and recommend one.

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
- For multi-speaker episodes, avoid fabricating confident speaker labels in show notes or descriptions

### 11. Publishing Package

If the user wants a publish-ready package, the default output set should be:

- `final.mp3`
- `final.srt`
- `final.mp4`
- `reels/` short videos
- `show_notes.md`
- `timestamps.txt`
- `youtube_description.md`

Recommended order:

1. lock the edit
2. render final audio
3. build subtitles
4. generate or collect cover art
5. render the YouTube video
6. propose reel candidates and render the selected reels
7. write show notes, timestamps, and YouTube description

## Editing Guidance

- Prefer removing dead air, repeated starts, verbal slips, and obvious throat-clearing first
- Preserve punchlines, emotional beats, and breaths that support cadence
- For podcasts, do not over-tighten everything into ad-read pacing
- For clip extraction, optimize for a complete thought and a clean ending
- If the user wants publication-ready output, recommend a separate mastering pass after structural editing
- For YouTube uploads, recommend checking subtitle readability and cover-image legibility before publishing
- For multi-speaker conversations, optimize for content clarity, not false precision around who said each line

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
