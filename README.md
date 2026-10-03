# podcast-use

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![uv](https://img.shields.io/badge/package%20manager-uv-5C5CFF.svg)](https://github.com/astral-sh/uv)
[![ffmpeg](https://img.shields.io/badge/audio-ffmpeg-007808.svg)](https://ffmpeg.org/)
[![Groq Whisper](https://img.shields.io/badge/STT-Groq%20Whisper-F55036.svg)](https://console.groq.com/docs/speech-to-text)

[繁體中文 README](README.zh-TW.md)

License: [MIT](LICENSE)

Conversation-driven podcast editing skill for **Grok**, **Claude Code**, and **Codex**.

**Edit first. Package later.**

This project is an audio-first fork concept inspired by `browser-use/video-use`, adapted for podcast and spoken-word editing.

## What it does

- Transcribes spoken audio with Groq Whisper (word timestamps, cached)
- Packs transcripts into a readable editing surface (`takes_packed.md`)
- Analyzes silence, filler candidates, and possible retakes
- Helps an agent propose tiered cuts (safe / optional / risky)
- Builds a validated edit decision list (`edl.draft.json` → `edl.approved.json`)
- Renders preview and final audio with ffmpeg + spoken-word processing
- Optionally builds subtitles, YouTube video, reels, and publish metadata

## Design principles

1. **Mode-first** — cleanup, shorten, clip, takes, review-only, or publish
2. **Approve before final render** — draft EDL, preview, then approve
3. **Never cut mid-word** — align to transcript word boundaries
4. **No fake diarization** — multi-speaker content is edited by meaning, not unreliable speaker labels
5. **Packaging is stage two** — covers/reels/show notes after the edit is locked

## Current limitations

- Groq Whisper does not provide true speaker diarization in this workflow
- Multi-person conversations can still be transcribed and content-edited
- Do not treat `Speaker A / B` labels as publication-grade attribution
- Filler/retake analysis is heuristic — always review before cutting
- Not a DAW replacement for music beds, multi-track mix, or complex sound design

---

## Quick start (how to use)

### 1. One-time setup

```bash
git clone https://github.com/soanseng/podcast-use.git
cd podcast-use
uv sync
cp .env.example .env
# put GROQ_API_KEY in .env
```

Requirements: `ffmpeg`, `ffprobe`, Python `3.10+`, `uv`, and `GROQ_API_KEY`.

Optional keys:

- `OPENAI_API_KEY` — local cover/reel image helpers
- `GEMINI_API_KEY` / `GOOGLE_API_KEY` — Gemini image path

### 2. Install the skill into your agent

```bash
# Grok
./scripts/install_skill.sh grok

# Claude Code
./scripts/install_skill.sh claude

# Codex
./scripts/install_skill.sh codex
```

This symlinks the repo into the client skills directory and runs `uv sync`.

| Client | Skill path |
|--------|------------|
| Grok | `~/.grok/skills/podcast-use` |
| Claude Code | `~/.claude/skills/podcast-use` |
| Codex | `~/.codex/skills/podcast-use` |

Restart the client or open a **new session** so the skill is discovered.

### 3. Put your audio somewhere

```text
my-episode/
└── episode.wav    # or .mp3 / .m4a / .flac
```

Artifacts will be written to `my-episode/edit/`.

### 4. Talk to the agent (recommended)

Open Grok / Claude Code / Codex in that folder (or point it at the audio path) and say things like:

```text
Use podcast-use. Clean up this podcast: remove fillers and dead air.
/path/to/my-episode/episode.wav
```

Other useful prompts:

```text
Use podcast-use in shorten mode. Cut this to about 25 minutes.

Use podcast-use. Review only first — summarize structure and suggest cuts, don't render yet.

Use podcast-use. Extract 3 clip candidates for Shorts from this episode.

Use podcast-use in publish mode after the edit is locked.
```

You can also invoke it as a slash command in Grok when the skill is installed: `/podcast-use`.

### 5. What a normal conversation looks like

1. **Mode** — agent asks cleanup / shorten / clip / takes / review-only / publish
2. **Glossary** — optional names/brands for better ASR
3. **Transcribe + pack + analyze**
4. **Cut proposal** — safe / optional / risky tiers + estimated duration
5. **You approve a tier**
6. Agent writes `edit/edl.draft.json`
7. **Validate + preview** (`edit/preview.mp3`)
8. You listen and request changes if needed
9. **Approve EDL → final render** (`edit/final.mp3`)
10. Optional packaging: subtitles, covers, YouTube video, reels, show notes, social posts (Facebook ~2000 chars, Threads/X <=500 chars)

**Do not skip approval.** Final audio should come from an approved EDL.

### Modes

| Mode | Goal | Typical outputs |
|------|------|-----------------|
| `cleanup` | fillers, dead air, slips | `final.mp3` |
| `shorten` | hit a shorter target length | `final.mp3` + cut rationale |
| `clip` | extract stand-alone clips | clip audio (+ srt optional) |
| `takes` | choose best takes across files | merged EDL + `final.mp3` |
| `review-only` | advice only | brief + suggestions, no render |
| `publish` | full upload package after edit is locked | audio + srt + video/reels/metadata |

---

## Install details

### Install by chat

Paste one of these into your agent:

- Grok, English: [prompts/install_grok_en.txt](prompts/install_grok_en.txt)
- Grok, zh-TW: [prompts/install_grok_zh-TW.txt](prompts/install_grok_zh-TW.txt)
- Claude Code, English: [prompts/install_claude_code_en.txt](prompts/install_claude_code_en.txt)
- Claude Code, zh-TW: [prompts/install_claude_code_zh-TW.txt](prompts/install_claude_code_zh-TW.txt)
- Codex, English: [prompts/install_codex_en.txt](prompts/install_codex_en.txt)
- Codex, zh-TW: [prompts/install_codex_zh-TW.txt](prompts/install_codex_zh-TW.txt)

### Manual install

```bash
# Grok
ln -sfn "$(pwd)" ~/.grok/skills/podcast-use

# Claude Code
ln -sfn "$(pwd)" ~/.claude/skills/podcast-use

# Codex
ln -sfn "$(pwd)" "${CODEX_HOME:-$HOME/.codex}/skills/podcast-use"
```

### Platform packages

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

---

## Manual helper workflow

Use this if you prefer shell commands, or to understand what the skill runs under the hood.

From the `podcast-use` repo (or any cwd if you pass absolute paths):

```bash
AUDIO=/path/to/episode.wav
EDIT=/path/to/edit          # usually <audio_dir>/edit

# 0) session tracker
uv run helpers/init_status.py --edit-dir "$EDIT"

# 1) optional glossary for names / jargon
uv run helpers/init_glossary.py --edit-dir "$EDIT"
$EDITOR "$EDIT/glossary.txt"

# 2) transcribe (local Taigi ASR, or Groq Whisper)
# local needs LITELLM_MASTER_KEY in .env; model default breeze-asr-26-taigi
uv run helpers/transcribe_local.py "$AUDIO" --edit-dir "$EDIT" \
  --glossary "$EDIT/glossary.txt"

uv run helpers/transcribe_groq.py "$AUDIO" --edit-dir "$EDIT"
uv run helpers/transcribe_groq.py "$AUDIO" --edit-dir "$EDIT" \
  --model whisper-large-v3 \
  --glossary "$EDIT/glossary.txt" \
  --force

# 3) pack + analyze
uv run helpers/pack_transcripts.py --edit-dir "$EDIT"
uv run helpers/analyze_audio.py "$AUDIO" --edit-dir "$EDIT"

# 4) after writing edl.draft.json (or let the agent write it)
uv run helpers/validate_edl.py --edit-dir "$EDIT" --edl "$EDIT/edl.draft.json"
uv run helpers/render_audio.py "$AUDIO" --edit-dir "$EDIT" \
  --edl "$EDIT/edl.draft.json" --preview

# 5) approve + final
uv run helpers/approve_edl.py --edit-dir "$EDIT"
uv run helpers/render_audio.py "$AUDIO" --edit-dir "$EDIT"
```

### Packaging (only after the edit is locked)

```bash
# word-level punctuation pass (punctuation-aligned cue breaks):
uv run helpers/punctuate_words_local.py "$EDIT/transcripts/episode.json"

uv run helpers/build_subtitles.py "$AUDIO" --edit-dir "$EDIT"
uv run helpers/build_subtitles.py "$AUDIO" --edit-dir "$EDIT" --refine-local
uv run helpers/build_subtitles.py "$AUDIO" --edit-dir "$EDIT" --refine-groq

uv run helpers/init_deliverables.py "$AUDIO" --edit-dir "$EDIT"

uv run helpers/render_youtube_video.py "$AUDIO" \
  --edit-dir "$EDIT" \
  --image "$EDIT/cover.png" \
  --burn-subtitles

uv run helpers/init_reels_plan.py --edit-dir "$EDIT"
uv run helpers/render_reels.py "$AUDIO" --edit-dir "$EDIT" --generate-images
```

---

## Edit directory layout

```text
edit/
├── STATUS.md
├── transcripts/
│   └── episode.json
├── analysis/
│   ├── episode_analysis.json
│   └── episode_suggestions.md
├── takes_packed.md
├── cut_proposal.md
├── edl.draft.json
├── edl.approved.json
├── edl.json                 # alias of approved
├── edl_validation.json
├── glossary.txt
├── preview.mp3
├── final.mp3
├── final.srt
├── final.mp4
├── show_notes.md
├── timestamps.txt
├── youtube_description.md
├── facebook_post.md
├── threads_post.md
├── cover_prompt.md
├── podcast_cover_prompt.md
├── reels_plan.json
└── reels/
```

## EDL format

```json
[
  {
    "source": "episode",
    "start": 1.20,
    "end": 7.80,
    "pad_in": 0.05,
    "pad_out": 0.08,
    "reason": "Clean opening line"
  }
]
```

- `source` must match the audio/transcript stem
- cuts should sit on word boundaries
- write drafts to `edl.draft.json`, promote with `approve_edl.py`

Resolution order when `--edl` is omitted: `edl.approved.json` → `edl.json` → `edl.draft.json`.

## Audio processing

Default final chain (spoken-word oriented):

1. broadband denoise
2. speech leveling
3. high-pass / low-pass
4. mild EQ
5. light compression
6. loudness normalize (`-16 LUFS` target)
7. light post denoise
8. limiter

Preview mode (`--preview`) skips heavy processing and writes `edit/preview.mp3` for faster iteration.

```bash
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --preview
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --edge-pad-ms 60
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --only-segment 2 --preview

# disable stages on already-mastered sources
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --no-denoise --no-eq
```

## Images

- Prefer runtime built-in image tools when available (e.g. Codex / Grok image tools)
- Local default: OpenAI `gpt-image-2` via `helpers/generate_image.py`
- Gemini remains an optional path

See [references/images.md](references/images.md) and [references/publishing.md](references/publishing.md).

## Skill architecture

```text
SKILL.md                     # short agent instructions (modes, checkpoints, hard rules)
references/
  modes.md                   # cleanup / shorten / clip / takes / review / publish
  editing-playbook.md        # keep vs cut judgment
  edl.md                     # EDL schema + validation
  publishing.md              # subtitles, metadata, reels order
  images.md                  # covers and image providers
helpers/                     # executable tools
```

## Helper index

| Helper | Purpose |
|--------|---------|
| `init_status.py` | Create `STATUS.md` session tracker |
| `init_glossary.py` | Glossary template |
| `transcribe_groq.py` | Groq Whisper transcription |
| `transcribe_local.py` | Taigi ASR via local LiteLLM proxy |
| `pack_transcripts.py` | Packed markdown + quick stats |
| `analyze_audio.py` | Silence / filler / retake hints |
| `validate_edl.py` | Validate cuts + duration report |
| `approve_edl.py` | Promote draft EDL to approved |
| `render_audio.py` | Preview/final audio render |
| `build_subtitles.py` | Output-timeline SRT |
| `refine_srt_groq.py` | Optional SRT wording refine (Groq) |
| `refine_srt_local.py` | Optional SRT wording refine (local LiteLLM) |
| `punctuate_words_local.py` | Word-level punctuation pass for cue breaks |
| `render_youtube_video.py` | Static-image YouTube MP4 |
| `init_reels_plan.py` | Reels plan skeleton |
| `render_reels.py` | Vertical short videos |
| `generate_image.py` | Local image generation |
| `init_deliverables.py` | Show notes / timestamps skeletons |

Every helper supports `--help`.

## Tests

```bash
uv sync --group dev
uv run pytest
```

## Glossary

For people, brands, mixed-language terms, and local phrases:

```bash
uv run helpers/init_glossary.py --edit-dir /path/to/edit
```

One term per line in `edit/glossary.txt`, then retranscribe with `--glossary` and `--force` for final accuracy.

## Related

If you care about content, reflection, and self-understanding tools, see [AnatoMee](https://anatomee.app/).  
`podcast-use` focuses on audio editing and publishing workflow; AnatoMee focuses on self-exploration.
