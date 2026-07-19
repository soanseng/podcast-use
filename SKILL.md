---
name: podcast-use
description: >
  Use when the user wants to edit a podcast, interview, monologue, or voice note:
  cleanup, shorten, pick takes, remove fillers/dead air, extract clips, or prepare
  publish-ready audio, subtitles, show notes, YouTube video, or reels from spoken-word
  recordings with transcript-driven cuts.
---

# Podcast Use

Conversation-driven **spoken-word editing assistant**.  
Core job: help the user cut better audio. Packaging (YouTube, reels, covers) is a second stage.

**Edit first. Package later.**

## When NOT to use

- Frame-accurate video / multi-cam film edit
- Full multi-track music production or complex sound design
- Publication-grade speaker attribution without human review
- Simple format conversion with no editorial decisions

## Hard rules

1. **Mode first.** Ask editing intent before cutting. Lock a mode before heavy work.
2. **Never cut mid-word.** Align cuts to word timestamps.
3. **Pad cut edges** (~30–150ms, default render pad 40ms) to avoid clipped consonants.
4. **Cache transcripts** in `edit/transcripts/`. Do not retranscribe unchanged files.
5. **Keep artifacts in `edit/`** next to the source audio.
6. **No fake diarization.** Groq Whisper has no reliable speaker labels. Multi-speaker edits are content-based only.
7. **No final render from an unapproved EDL.** Draft → user approve → `edl.approved.json` → render.
8. **Warn before destructive cuts** that harm meaning, jokes, emotion, or cadence. Propose a safer alternative.
9. **Glossary before final ASR** when names, brands, mixed language, or Taiwanese terms matter.
10. **Packaging is opt-in** unless mode is `publish` or the user asks.

## Modes

| Mode | User intent | Default outputs |
|------|-------------|-----------------|
| `cleanup` | remove fillers, dead air, slips | `final.mp3` |
| `shorten` | tighten length | `final.mp3` + cut rationale |
| `clip` | extract one or more clips | clip audio (+ srt optional) |
| `takes` | choose best of multiple takes | merged EDL + `final.mp3` |
| `review-only` | advise only | brief + suggestions, no EDL/render |
| `publish` | ship-ready package | audio + srt + video/reels/metadata |

If unclear, offer A/B/C choices rather than a long questionnaire.

Details: [references/modes.md](references/modes.md)

## Checkpoint workflow

```text
1. Inventory + lock mode → edit/STATUS.md
2. Glossary? (names / jargon)
3. Transcribe → pack → analyze
4. Content brief (short)
5. Cut proposal (safe / optional / risky)
6. User approve → write edl.draft.json
7. validate_edl → preview render
8. Revise from feedback
9. approve_edl → final render
10. Optional packaging (only if requested or mode=publish)
```

Update `edit/STATUS.md` after each phase.

### 1. Inventory

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 /path/to/audio.wav
uv run helpers/init_status.py --edit-dir /path/to/edit
```

Ask: single vs multi speaker, target length, cleanup vs restructure, publish or not.

### 2. Transcribe + pack + analyze

```bash
uv run helpers/init_glossary.py --edit-dir /path/to/edit   # if needed
uv run helpers/transcribe_groq.py /path/to/audio.wav
# optional final pass:
uv run helpers/transcribe_groq.py /path/to/audio.wav --glossary /path/to/edit/glossary.txt --model whisper-large-v3 --force

uv run helpers/pack_transcripts.py --edit-dir /path/to/edit
uv run helpers/analyze_audio.py /path/to/audio.wav --edit-dir /path/to/edit
```

Default model: `whisper-large-v3-turbo`. Use `whisper-large-v3` when accuracy matters more.

Primary reading surfaces:

- `edit/takes_packed.md`
- `edit/analysis/*_suggestions.md`

### 3. Propose cuts (required format)

```markdown
## Mode
cleanup

## Source
- file: episode.wav
- duration: 48m12s
- speakers: likely 2 (no reliable diarization)

## Strategy
1. ...
2. ...

## Estimated result
~48m → ~36–38m

## Cut tiers
- Safe: ...
- Optional: ...
- Risky: ...

## Risks
- ...

## Next
Approve A (safe) / B (safe+optional) / custom notes?
```

Do **not** write EDL until the user confirms a tier or gives notes.

Editing judgment: [references/editing-playbook.md](references/editing-playbook.md)

### 4. Build EDL

Write `edit/edl.draft.json`:

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

Optional per-segment pads: `pad_in`, `pad_out` (seconds).

```bash
uv run helpers/validate_edl.py --edit-dir /path/to/edit --edl /path/to/edit/edl.draft.json
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit --edl /path/to/edit/edl.draft.json --preview
```

After user accepts:

```bash
uv run helpers/approve_edl.py --edit-dir /path/to/edit
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit
```

EDL schema + validation: [references/edl.md](references/edl.md)

### 5. Final audio notes

Default spoken-word chain: denoise → level → HPF/LPF → EQ → compress → loudnorm → light denoise → limiter.

- Already mastered source → disable stages selectively (`--no-denoise`, etc.)
- Preview skips heavy processing and writes `edit/preview.mp3`
- Global edge pad: `--edge-pad-ms` (default 40)

### 6. Packaging (second stage)

Only when mode is `publish` or user asks. Order:

1. Lock edit / final audio
2. Subtitles (`final.srt`)
3. Cover art (ask text-in-image + style first)
4. YouTube static video
5. Reels candidates → user pick → render
6. `show_notes.md`, `timestamps.txt`, `youtube_description.md`

```bash
uv run helpers/build_subtitles.py /path/to/audio.wav --edit-dir /path/to/edit
# optional auto refine:
uv run helpers/build_subtitles.py /path/to/audio.wav --edit-dir /path/to/edit --refine-groq
```

After `final.srt`, refine wording only (keep cue count + timestamps). Prefer glossary terms; for zh-Hant projects prefer Traditional Chinese.

Details:

- [references/publishing.md](references/publishing.md)
- [references/images.md](references/images.md)

## Directory layout

```text
source_dir/
├── episode.wav
└── edit/
    ├── STATUS.md
    ├── transcripts/
    ├── analysis/
    ├── takes_packed.md
    ├── cut_proposal.md
    ├── edl.draft.json
    ├── edl.approved.json
    ├── edl.json              # alias of approved (compat)
    ├── glossary.txt
    ├── preview.mp3
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

## Common mistakes

- Starting cover/reels questions before the edit is locked
- Treating packed phrase boundaries as the only legal cut points (word-level is source of truth)
- Over-tightening into ad-read pacing
- Writing timestamps on source timeline instead of output timeline
- Confident speaker labels without diarization or manual review
- Final render from `edl.draft.json` without approval
- Inventing sponsor links / CTAs

## Red flags — stop and re-center

- Jumping to packaging during cleanup
- Cutting without a stated mode
- Silent EDL changes after user approval
- Mid-word cut points
- “Speaker A said…” presented as ground truth

## Helper index

| Helper | Purpose |
|--------|---------|
| `transcribe_groq.py` | ASR + word timestamps |
| `pack_transcripts.py` | Readable packed transcript |
| `analyze_audio.py` | Silence / filler / retake hints |
| `validate_edl.py` | Boundary + duration checks |
| `approve_edl.py` | draft → approved |
| `render_audio.py` | Preview/final audio from EDL |
| `build_subtitles.py` | Output-timeline SRT |
| `refine_srt_groq.py` | Optional SRT wording pass |
| `render_youtube_video.py` | Static-image MP4 |
| `init_reels_plan.py` / `render_reels.py` | Shorts/reels |
| `generate_image.py` | Local cover/reel images |
| `init_deliverables.py` | Metadata skeletons |
| `init_glossary.py` / `init_status.py` | Session setup |

Run any helper with `--help` for flags. Prefer that over inventing options.
