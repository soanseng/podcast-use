# Editing playbook

Use with `takes_packed.md` and `analysis/*_suggestions.md`.

## Priority order

1. **Technical cleanup** — clicks, hard clips, extreme dead air, coughs that break flow
2. **False starts / retakes** — keep the cleanest complete take
3. **Filler** — only when it slows or distracts; not every token
4. **Content tighten** — digressions, repeated explanations
5. **Restructure** — only when user asks; explain narrative rationale first

## Keep / cut heuristics

### Prefer keeping

- Breaths that set up a punchline
- Thinking pauses that signal honesty or weight
- Soft laughter and human reactions
- Turn-taking gaps in interviews (unless huge)
- Proper names and glossary terms even if ASR is ugly — fix text, don't auto-delete audio without listening rationale

### Prefer cutting

- Dead air longer than ~1.0–1.5s with no conversational purpose
- “I'll start over” + abandoned attempt
- Exact repeated sentence when the second take is cleaner
- Obvious mic bumps / throat clears between ideas
- Long pre-roll silence and post-roll tails

### Cut carefully

- Filler words that are part of a speaker's character
- Pauses after emotional statements
- Overlaps in multi-speaker audio (no reliable diarization)

## Filler candidates (not auto-delete lists)

**Chinese (examples):** 嗯、啊、呃、那個、就是、然後、對對對  
**English (examples):** um, uh, like, you know, sort of, kind of, basically

Rule: treat analyzer hits as **candidates**. Delete only when the phrase still reads cleanly without them.

## Retakes

When analysis flags a retake cluster:

1. Read all variants in packed transcript
2. Prefer complete + least hesitation + clear ending
3. Note why in the segment `reason` field

## Multi-speaker episodes

- Edit for **content clarity**, not speaker labels
- Never invent “Host:” / “Guest:” as ground truth in show notes unless user confirms
- If attribution is required for publish, mark it provisional and ask for review

## Proposal language

Always split cuts into:

- **Safe** — cleanup almost everyone wants
- **Optional** — tighten for length/pace
- **Risky** — may remove nuance; needs explicit approval

## Cadence anti-patterns

- Deleting every silence under 400ms
- Making interviews sound like an ad read
- Joining sentences so tightly that breaths disappear
- Cutting the landing of a story to save 5 seconds
