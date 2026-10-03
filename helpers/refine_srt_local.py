"""Refine subtitle wording with the local LiteLLM text model (qwen36-genesis).

Reuses the parsing, batching, and prompt logic from refine_srt_groq.py; only the
client (local proxy) and default model differ.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import local_llm
from refine_srt_groq import (
    chunked,
    load_glossary,
    load_reference_context,
    parse_srt,
    refine_batch,
    render_srt,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refine subtitle text with the local LiteLLM text model"
    )
    parser.add_argument("srt", type=Path, help="Input SRT path")
    parser.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="Optional edit directory for glossary and reference context",
    )
    parser.add_argument(
        "--glossary",
        type=Path,
        default=None,
        help="Optional glossary file with one term per line",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Local text model. Defaults to PODCAST_REFINE_MODEL or qwen36-genesis",
    )
    parser.add_argument(
        "--fallback-model",
        default="",
        help="Optional fallback local model",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override LITELLM_BASE_URL, e.g. http://100.102.183.27:4000/v1",
    )
    parser.add_argument(
        "--language",
        default="zh-Hant",
        help="Target subtitle language hint. Defaults to zh-Hant",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Cues per model call. Default: auto (80, or 160 above 700 cues)",
    )
    parser.add_argument(
        "--reference-chars",
        type=int,
        default=12000,
        help="Maximum reference context chars loaded from the edit directory",
    )
    parser.add_argument(
        "--json-mode",
        action="store_true",
        help="Send response_format=json_object (off by default; llama.cpp backends may starve on it)",
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="Allow model reasoning. Off by default: reasoning-only replies break JSON refinement",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Completion budget per batch. Default: max(4096, 32 x batch)",
    )
    parser.add_argument(
        "--reasoning",
        default=None,
        choices=["none", "off", "low", "medium", "high", "xhigh", "max"],
        help="reasoning_effort for cloud models. Default: none (PODCAST_REFINE_REASONING overrides)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Defaults to overwriting the input SRT",
    )
    args = parser.parse_args()

    srt_path = args.srt.resolve()
    if not srt_path.exists():
        sys.exit(f"srt not found: {srt_path}")
    cues = parse_srt(srt_path)
    if not cues:
        sys.exit(f"no cues found in {srt_path}")

    edit_dir = args.edit_dir.resolve() if args.edit_dir else None
    glossary_path = args.glossary
    if not glossary_path and edit_dir:
        candidate = edit_dir / "glossary.txt"
        if candidate.exists():
            glossary_path = candidate

    client = local_llm.make_refine_client(base_url_override=args.base_url)
    model = args.model or local_llm.refine_model()
    fallback_model = args.fallback_model.strip() or None
    if fallback_model == model:
        fallback_model = None
    glossary_terms = load_glossary(glossary_path)
    reference_context = load_reference_context(edit_dir, max_chars=max(0, args.reference_chars))

    if args.batch_size:
        batch_size = max(1, args.batch_size)
    else:
        # Long episodes amortize per-request overhead with bigger batches.
        batch_size = 160 if len(cues) > 700 else 80
        print(f"auto batch size: {batch_size} ({len(cues)} cues)", file=sys.stderr)
    max_tokens = max(1, args.max_tokens) if args.max_tokens else max(4096, batch_size * 32)

    refined_cues: list[dict] = []
    for batch in chunked(cues, batch_size=batch_size):
        refined_cues.extend(
            refine_batch(
                client=client,
                model=model,
                fallback_model=fallback_model,
                cues=batch,
                language=args.language,
                glossary_terms=glossary_terms,
                reference_context=reference_context,
                json_mode=args.json_mode,
                disable_thinking=not args.thinking and local_llm.thinking_toggle_supported(args.base_url),
                reasoning_effort=args.reasoning or local_llm.refine_reasoning(args.base_url),
            )
        )

    output_path = (args.output or srt_path).resolve()
    output_path.write_text(render_srt(refined_cues))
    print(f"refined subtitles: {output_path}")


if __name__ == "__main__":
    main()
