# podcast-use

Conversation-driven podcast editing skill for Claude Code.

This project is an audio-first fork concept inspired by `browser-use/video-use`, adapted for podcast and spoken-word editing workflows.

## What it does

- Transcribes audio with Groq Whisper
- Packs word timestamps into a compact markdown view
- Lets Claude Code reason over the transcript and produce an edit decision list
- Renders a clean audio edit with ffmpeg
- Builds subtitles as `.srt`
- Creates a static-image YouTube `.mp4`
- Produces packaging artifacts for show notes, timestamps, and YouTube description

## Arch Linux setup

Install system packages:

```bash
sudo pacman -S ffmpeg python python-pip
```

Create a virtualenv and install Python deps:

```bash
cd podcast-use
python -m venv .venv
source .venv/bin/activate
pip install -e .
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
python helpers/transcribe_groq.py /path/to/audio.wav
python helpers/pack_transcripts.py --edit-dir /path/to/edit
```

Choose a model explicitly when needed:

```bash
python helpers/transcribe_groq.py /path/to/audio.wav --model whisper-large-v3-turbo
python helpers/transcribe_groq.py /path/to/audio.wav --model whisper-large-v3
```

Model guidance:

- `whisper-large-v3-turbo`: faster and cheaper, good default for iterative editing
- `whisper-large-v3`: slower and more expensive, better when transcript accuracy matters more

After Claude Code writes `edl.json`, render:

```bash
python helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit
```

Build subtitles:

```bash
python helpers/build_subtitles.py /path/to/audio.wav --edit-dir /path/to/edit
```

Render a static-image YouTube video:

```bash
python helpers/render_youtube_video.py /path/to/audio.wav \
  --edit-dir /path/to/edit \
  --image /path/to/cover.png \
  --burn-subtitles
```

Create metadata file skeletons:

```bash
python helpers/init_deliverables.py /path/to/audio.wav --edit-dir /path/to/edit
```

## Edit output layout

```text
edit/
├── transcripts/
│   └── source.json
├── takes_packed.md
├── edl.json
├── final.mp3
├── final.srt
├── final.mp4
├── show_notes.md
├── timestamps.txt
├── youtube_description.md
└── cover_prompt.md
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

Suggested image prompt shape:

- topic and guest
- mood and visual direction
- composition for 16:9 YouTube frame
- text treatment guidance
- negative prompt guidance to avoid clutter or unreadable typography
