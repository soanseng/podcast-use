"""Add punctuation at the word level via the local LiteLLM model.

Reads ``transcripts/<stem>.json`` and writes ``transcripts/<stem>.punct.json``
with the identical word count, order, and timings — the model only marks which
tokens need a trailing punctuation mark. ``build_subtitles.py`` automatically
prefers the ``.punct.json`` variant, so cues break on punctuation with exact
word timestamps (no interpolation).

Progress is checkpointed to ``<stem>.punct.partial.json`` after every batch and
resumed automatically on the next run.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import local_llm
from refine_srt_groq import chat_json

ALLOWED_MARKS = set("，。、！？；：")

SYSTEM_PROMPT = (
    "You mark trailing punctuation for spoken-word ASR tokens. "
    "The user message contains a JSON array of tokens. "
    "Return JSON with shape {\"punct\":[{\"i\":<token index>,\"p\":\"<mark>\"}]} listing ONLY "
    "the tokens that need a trailing punctuation mark appended. "
    "p must be exactly one of: ， 。 、 ！ ？ ； ： "
    "Use 。 or ！ or ？ at sentence ends, ， at clause pauses, 、 inside lists. "
    "Do not rewrite, merge, split, or translate tokens. "
    "Do not mark tokens that already end with punctuation. "
    "When unsure, omit the token."
)


def apply_marks(words: list[dict], marks: list) -> list[dict]:
    """Append marked punctuation to tokens; ignore anything invalid or risky."""
    out = [dict(word) for word in words]
    for item in marks:
        if not isinstance(item, dict):
            continue
        try:
            position = int(item.get("i"))
        except (TypeError, ValueError):
            continue
        mark = str(item.get("p", ""))
        if position < 0 or position >= len(words) or mark not in ALLOWED_MARKS:
            continue
        token = out[position]["word"].rstrip()
        if not token or token[-1] in ALLOWED_MARKS or token[-1] in ".,!?;:":
            continue
        out[position]["word"] = token + mark
    return out


def punctuate_batch(
    client,
    model: str,
    words: list[dict],
    *,
    json_mode: bool,
    disable_thinking: bool,
    max_tokens: int | None,
    reasoning_effort: str | None = None,
    attempts: int = 3,
) -> list[dict]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Mark the tokens that need trailing punctuation.\n"
            + json.dumps({"tokens": [word["word"] for word in words]}, ensure_ascii=False),
        },
    ]

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            payload = chat_json(
                client,
                model,
                messages,
                json_mode=json_mode,
                disable_thinking=disable_thinking,
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
        except Exception as exc:  # noqa: BLE001 - transient empty/5xx responses
            last_error = exc
            print(f"  batch retry {attempt}/{attempts}: {exc}", file=sys.stderr)
            continue
        marks = payload.get("punct")
        if isinstance(marks, list) and len(marks) <= len(words):
            return apply_marks(words, marks)
        got = len(marks) if isinstance(marks, list) else type(marks).__name__
        last_error = ValueError(f"invalid punct list: {got} entries for {len(words)} tokens")
        print(f"  batch retry {attempt}/{attempts}: {last_error}", file=sys.stderr)
    raise RuntimeError(f"punctuation batch failed after {attempts} attempts: {last_error}")



def write_partial(path: Path, payload: dict, punctuated: list[dict]) -> None:
    payload = dict(payload)
    payload["words"] = punctuated
    path.write_text(json.dumps(payload, ensure_ascii=False))

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Word-level punctuation pass (local LiteLLM) for punctuation-aligned cues"
    )
    parser.add_argument("transcript", type=Path, help="Path to transcripts/<stem>.json")
    parser.add_argument(
        "--model",
        default=None,
        help="Local model. Defaults to PODCAST_REFINE_MODEL or qwen36-genesis",
    )
    parser.add_argument(
        "--reasoning",
        default=None,
        choices=["none", "off", "low", "medium", "high", "xhigh", "max"],
        help="reasoning_effort for cloud models. Default: none (PODCAST_REFINE_REASONING overrides)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override LITELLM_BASE_URL, e.g. http://100.102.183.27:4000/v1",
    )
    parser.add_argument(
        "--batch-words",
        type=int,
        default=300,
        help="Tokens per model call (default: 300). Keep it: cloud models reason per call "
        "and reasoning tokens grow faster than the batch (600 words = 4x latency)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Model calls in flight at once (default: 4). Provider throttling caps the gain: "
        "measured 1.4x-3.5x",
    )
    parser.add_argument(
        "--json-mode",
        action="store_true",
        help="Send response_format=json_object (off by default)",
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="Allow model reasoning. Off by default",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Completion budget per batch. Default: scaled to batch size",
    )
    parser.add_argument("-o", "--output", type=Path, default=None, help="Default: <stem>.punct.json")
    parser.add_argument("--force", action="store_true", help="Ignore cache/partial and start over")
    args = parser.parse_args()

    transcript_path = args.transcript.resolve()
    if not transcript_path.exists():
        sys.exit(f"transcript not found: {transcript_path}")
    output_path = (args.output or transcript_path.with_suffix(".punct.json")).resolve()
    partial_path = transcript_path.with_suffix(".punct.partial.json")
    if output_path.exists() and not args.force:
        print(f"cached: {output_path}")
        return

    payload = json.loads(transcript_path.read_text())
    words = payload.get("words") or []
    if not words:
        sys.exit(f"no words in {transcript_path}; run transcribe first")

    punctuated: list[dict] = []
    if partial_path.exists() and not args.force:
        partial = json.loads(partial_path.read_text())
        punctuated = partial.get("words") or []
        if punctuated and len(punctuated) <= len(words):
            print(f"resuming from partial: {len(punctuated)}/{len(words)} words", file=sys.stderr)
        else:
            punctuated = []

    client = local_llm.make_refine_client(base_url_override=args.base_url)
    model = args.model or local_llm.refine_model()
    batch_words = max(1, args.batch_words)
    max_tokens = args.max_tokens or max(4096, batch_words // 2)
    disable_thinking = not args.thinking and local_llm.thinking_toggle_supported(args.base_url)
    reasoning_effort = args.reasoning or local_llm.refine_reasoning(args.base_url)
    remaining = words[len(punctuated) :]
    batches = [
        remaining[start : start + batch_words] for start in range(0, len(remaining), batch_words)
    ]
    total_batches = len(batches)

    def run_batch(batch: list[dict]) -> list[dict]:
        return punctuate_batch(
            client,
            model,
            batch,
            json_mode=args.json_mode,
            disable_thinking=disable_thinking,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )

    # Batches are independent; each one is slow only because cloud models think. Run
    # several at once and keep the checkpoint a contiguous prefix so resume still works.
    completed: list[list[dict] | None] = [None] * total_batches
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {pool.submit(run_batch, batch): index for index, batch in enumerate(batches)}
        for count, future in enumerate(as_completed(futures), start=1):
            completed[futures[future]] = future.result()
            prefix: list[dict] = []
            for part in completed:
                if part is None:
                    break
                prefix.extend(part)
            write_partial(partial_path, payload, punctuated + prefix)
            print(
                f"batch {count}/{total_batches}: {len(punctuated) + len(prefix)}/{len(words)} words",
                file=sys.stderr,
            )

    for part in completed:
        punctuated.extend(part or [])

    payload["words"] = punctuated
    payload["punctuated_by"] = model
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    partial_path.unlink(missing_ok=True)
    print(f"saved: {output_path}")


if __name__ == "__main__":
    main()
