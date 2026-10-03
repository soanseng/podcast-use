# Publishing package

Use only in `publish` mode or when the user explicitly asks for upload assets.

## Default deliverables

- `final.mp3`
- `final.srt`
- `final.mp4` (static cover + audio)
- `reels/` (if requested)
- `show_notes.md`
- `timestamps.txt`
- `youtube_description.md`
- `facebook_post.md` (~2000 chars, on request)
- `threads_post.md` (<=500 chars, on request)

## Order

1. Lock edit (`edl.approved.json`) and render final audio
2. Build subtitles
3. Cover art (YouTube 16:9; podcast 1:1 optional)
4. YouTube video
5. Reel candidates → user selection → render
6. Metadata files
7. Social posts: `facebook_post.md` (~2000 chars), `threads_post.md` (<=500 chars)

## Subtitles

```bash
uv run helpers/build_subtitles.py /path/to/audio.wav --edit-dir /path/to/edit
# local refinement (LiteLLM, qwen36-genesis):
uv run helpers/build_subtitles.py /path/to/audio.wav --edit-dir /path/to/edit --refine-local
# Groq refinement:
uv run helpers/build_subtitles.py /path/to/audio.wav --edit-dir /path/to/edit --refine-groq
```

Refinement rules:

- Keep cue count and timestamps unchanged
- Fix wording only
- Prefer glossary spellings
- zh-Hant projects: prefer Traditional Chinese
- If uncertain, leave original text

Optional standalone refine:

```bash
uv run helpers/refine_srt_local.py /path/to/edit/final.srt --edit-dir /path/to/edit
uv run helpers/refine_srt_groq.py /path/to/edit/final.srt --edit-dir /path/to/edit
```

Default models: local `qwen36-genesis` (`PODCAST_REFINE_MODEL`); Groq `qwen/qwen3-32b` with fallback `openai/gpt-oss-120b`.

`refine_srt_local.py` sends `chat_template_kwargs.enable_thinking=false` by default (`--thinking` to allow
reasoning) because qwen36-genesis otherwise spends its budget on `reasoning_content` and returns empty
`content`. `response_format=json_object` is off by default (`--json-mode` to enable); both settings degrade
automatically if the provider rejects them. Batch size auto-scales with episode length (80 cues per
request, or 160 above ~700 cues) unless `--batch-size` is set explicitly; truncated completions are
retried with a doubled budget.

Cue breakpoints: run `punctuate_words_local.py` on the transcript before `build_subtitles.py` — the
model appends punctuation at the word level (strict same-count/same-order contract), so cues break on
punctuation with exact word timestamps. `build_subtitles.py` also breaks at silence gaps
(`--max-gap`, default 0.35 s) and a duration cap (`--max-cue-seconds`, default 3.5 s); CJK tokens
are joined without spaces.

Cloud providers (commandcode etc.): thinking models reason on every request, and reasoning tokens grow
faster than the batch does — raising `--batch-words` to 600 measured 4x the latency for 1.5x the marks,
and 1200 words overflowed the completion budget outright. Keep batches at 300 and raise `--concurrency`
instead (default 4 in-flight calls; 4 batches measured 1.4x faster under heavy provider throttling,
3.5x when the provider is lightly loaded — it throttles per account, so the gain is bounded). Some models cannot
disable thinking at all (`z-ai/glm-5.3-flash` rejects both `none` and `off`); a rejected
`reasoning_effort` falls back to the cheapest effort the provider accepts rather than being dropped —
dropping it makes the model think and burn the whole budget on reasoning.

## Metadata guidance

### `show_notes.md`

- 1–2 paragraph summary
- key topics
- notable quotes / takeaways
- resources with placeholders if unknown

### `timestamps.txt`

- Output timeline, not source timeline
- Format: `00:00 Topic`

### `youtube_description.md`

1. Hook (first 1–2 lines must stand alone)
2. Short summary
3. Timestamps
4. Links / CTAs (placeholders OK; do not invent)

### `facebook_post.md`

- ~2000 characters (1800-2200), episode language
- First line must stand alone in feed preview
- Story-first: one thread of argument from the episode, not a summary dump
- 3-5 takeaways (timestamps optional), ends with one audience question + listen link placeholder
- No fabricated quotes

### `threads_post.md`

- <=500 characters including spaces, hashtags, and link — count the draft text only
- One idea only: the strongest hook from the episode
- 1-3 hashtags max; link placeholder at the end
- X free tier caps at 280 characters: keep a trimmed variant if the same post targets X

```bash
uv run helpers/init_deliverables.py /path/to/audio.wav --edit-dir /path/to/edit
```

## YouTube video

```bash
uv run helpers/render_youtube_video.py /path/to/audio.wav \
  --edit-dir /path/to/edit \
  --image /path/to/edit/cover.png \
  --burn-subtitles
```

## Reels

1. Ask how many (usually 3–5)
2. Propose 5–8 candidate segments with hooks
3. User picks
4. Confirm vertical 9:16, style, text-in-image preference
5. Fill `reels_plan.json` and render

```bash
uv run helpers/init_reels_plan.py --edit-dir /path/to/edit
uv run helpers/render_reels.py /path/to/audio.wav --edit-dir /path/to/edit --generate-images
```

Each reel should usually be 30–60s, one idea, strong opening hook, with subtitles.

## QA before “done”

- [ ] Approved EDL used for final audio
- [ ] Preview or final listened for clipped words
- [ ] Duration matches expectation
- [ ] Subtitles readable; glossary names correct
- [ ] Timestamps are output-relative
- [ ] No fabricated speaker labels or links
