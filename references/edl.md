# EDL format and validation

## Files

| File | Role |
|------|------|
| `edl.draft.json` | Working edit; safe to revise |
| `edl.approved.json` | User-approved; use for final render |
| `edl.json` | Compatibility alias of approved (written by `approve_edl.py`) |

Resolution order for render/subtitles when `--edl` is omitted:

1. `edl.approved.json`
2. `edl.json`
3. `edl.draft.json`

## Schema

JSON array of segments:

```json
[
  {
    "source": "episode",
    "start": 12.34,
    "end": 18.91,
    "pad_in": 0.05,
    "pad_out": 0.08,
    "reason": "Clean explanation without hesitation"
  }
]
```

| Field | Required | Notes |
|-------|----------|-------|
| `source` | yes | Transcript/audio stem (filename without extension) |
| `start` | yes | Seconds, word-boundary aligned |
| `end` | yes | Seconds, `end > start` |
| `reason` | recommended | Short human rationale |
| `pad_in` | no | Extra seconds before start |
| `pad_out` | no | Extra seconds after end |

## Rules

- Keep segments chronological unless the user wants restructuring
- Align to word timestamps from `edit/transcripts/<source>.json`
- Prefer slight edge padding over tight word-clipped cuts
- Global render pad: `render_audio.py --edge-pad-ms 40` (default)
- Multi-source takes: `source` must match each audio stem

## Commands

```bash
# Validate draft
uv run helpers/validate_edl.py --edit-dir /path/to/edit --edl /path/to/edit/edl.draft.json

# Strict mode (boundary issues become errors)
uv run helpers/validate_edl.py --edit-dir /path/to/edit --strict

# Preview from draft
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit \
  --edl /path/to/edit/edl.draft.json --preview

# Single segment check
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit \
  --edl /path/to/edit/edl.draft.json --preview --only-segment 3

# Approve + final
uv run helpers/approve_edl.py --edit-dir /path/to/edit
uv run helpers/render_audio.py /path/to/audio.wav --edit-dir /path/to/edit
```

`validate_edl.py` writes `edit/edl_validation.json` with duration estimates, warnings, and largest dropped gaps.

## Approval policy

- Agents may write/update `edl.draft.json` after user agrees on strategy
- Agents must **not** silently replace `edl.approved.json`
- Final `final.mp3` should come from approved EDL (or explicit user override)
