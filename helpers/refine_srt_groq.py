from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from openai import OpenAI


def load_api_key() -> str:
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == "GROQ_API_KEY":
                    return value.strip().strip('"').strip("'")
    value = os.environ.get("GROQ_API_KEY", "").strip()
    if value:
        return value
    sys.exit("GROQ_API_KEY not found in .env or environment")


def parse_srt(path: Path) -> list[dict]:
    text = path.read_text().strip()
    if not text:
        return []
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    cues: list[dict] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            sys.exit(f"invalid SRT block in {path}: {block}")
        try:
            index = int(lines[0])
        except ValueError as exc:
            raise SystemExit(f"invalid SRT cue index in {path}: {lines[0]}") from exc
        cues.append(
            {
                "index": index,
                "timing": lines[1],
                "text": "\n".join(lines[2:]).strip(),
            }
        )
    return cues


def render_srt(cues: list[dict]) -> str:
    blocks: list[str] = []
    for cue in cues:
        blocks.append(f"{cue['index']}\n{cue['timing']}\n{cue['text']}")
    return "\n\n".join(blocks) + "\n"


def load_glossary(glossary_path: Path | None) -> list[str]:
    if not glossary_path:
        return []
    path = glossary_path.resolve()
    if not path.exists():
        sys.exit(f"glossary not found: {path}")
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def load_reference_context(edit_dir: Path | None, max_chars: int) -> str:
    if not edit_dir:
        return ""
    candidates = [
        edit_dir / "takes_packed.md",
        edit_dir / "glossary.txt",
    ]
    parts: list[str] = []
    for candidate in candidates:
        if candidate.exists():
            label = candidate.name
            content = candidate.read_text().strip()
            if content:
                parts.append(f"[{label}]\n{content}")
    merged = "\n\n".join(parts).strip()
    if not merged:
        return ""
    return merged[:max_chars]


def chunked(items: list[dict], batch_size: int) -> list[list[dict]]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def extract_json_object(text: str) -> dict:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(stripped[start : end + 1])


def reasoning_fallbacks(reasoning_effort: str | None, message: str) -> list[str]:
    """Effort values worth retrying after the provider rejects the requested one.

    Vocabularies differ: commandcode spells "no thinking" as "off". Dropping the
    parameter instead makes thinking models burn their whole budget on reasoning,
    so fall back to the cheapest effort they do accept first.
    """
    fallbacks: list[str] = []
    if reasoning_effort == "none" and "expected one of" in message and '"off"' in message:
        fallbacks.append("off")
    if reasoning_effort != "low":
        fallbacks.append("low")
    return fallbacks


def chat_json(
    client: OpenAI,
    model: str,
    messages: list[dict],
    *,
    json_mode: bool = True,
    disable_thinking: bool = False,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
) -> dict:
    """Chat completion parsed as JSON, tolerant of provider quirks.

    - drops response_format if the provider rejects it
    - drops the llama.cpp thinking toggle if the provider rejects it
    - drops reasoning_effort if the provider rejects it
    - retries plain-mode with a bigger budget on empty or truncated completions
    - retries once more with a doubled budget when JSON parsing still fails
    """

    def call(
        use_json_mode: bool,
        token_budget: int | None = None,
        disable_reasoning: bool | None = None,
        include_reasoning: bool = True,
        reasoning_override: str | None = None,
    ) -> object:
        kwargs: dict = {
            "model": model,
            "messages": messages,
            "temperature": 0.0,
        }
        budget = token_budget if token_budget is not None else max_tokens
        if budget:
            kwargs["max_tokens"] = budget
        if use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        reasoning_off = disable_thinking if disable_reasoning is None else disable_reasoning
        if reasoning_off:
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        effort = reasoning_override or reasoning_effort
        if effort and include_reasoning:
            kwargs["reasoning_effort"] = effort
        return client.chat.completions.create(**kwargs)

    def content_of(resp: object) -> str:
        try:
            return (resp.choices[0].message.content or "").strip()
        except (AttributeError, IndexError):
            return ""

    def truncated(resp: object) -> bool:
        try:
            return str(resp.choices[0].finish_reason) == "length"
        except (AttributeError, IndexError):
            return False


    try:
        response = call(json_mode)
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "response_format" in message:
            response = call(False)
        elif "reasoning_effort" in message or "reasoning" in message:
            response = None
            for effort in reasoning_fallbacks(reasoning_effort, message):
                try:
                    response = call(json_mode, reasoning_override=effort)
                    break
                except Exception:  # noqa: BLE001 - model may not support this effort either
                    response = None
            if response is None:
                response = call(json_mode, include_reasoning=False)
        elif "chat_template_kwargs" in message or "extra_body" in message or "unexpected keyword" in message:
            response = call(json_mode, disable_reasoning=False)
        else:
            raise
    content = content_of(response)
    if not content or truncated(response):
        response = call(False, max(max_tokens or 0, 4096) * 2, disable_reasoning=False)
        content = content_of(response)
    if not content:
        raise ValueError("model returned an empty completion")
    try:
        return extract_json_object(content)
    except json.JSONDecodeError:
        response = call(False, max(max_tokens or 0, 4096) * 4, disable_reasoning=False)
        content = content_of(response)
        if not content:
            raise ValueError("model returned an empty completion") from None
        return extract_json_object(content)



def refine_batch(
    *,
    client: OpenAI,
    model: str,
    fallback_model: str | None,
    cues: list[dict],
    language: str,
    glossary_terms: list[str],
    reference_context: str,
    json_mode: bool = True,
    disable_thinking: bool = False,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
) -> list[dict]:
    system_prompt = (
        "You refine subtitle text for spoken-word audio. "
        "Keep the same cue count, the same indexes, and the same timing outside the JSON output. "
        "Only rewrite the text field. "
        "Prioritize Traditional Chinese orthography when language is zh-Hant. "
        "Preserve mixed-language brand names, people names, Taiwanese, and code/product terms. "
        "Correct obvious ASR mistakes, punctuation, spacing, and wording only when confidence is high. "
        "If uncertain, preserve the original wording. "
        "Do not invent facts. "
        "Return valid JSON with shape {\"cues\":[{\"index\":1,\"text\":\"...\"}]}. "
        "Every returned index must match the input index exactly."
    )
    user_payload = {
        "language": language,
        "glossary_terms": glossary_terms,
        "reference_context": reference_context,
        "cues": [{"index": cue["index"], "text": cue["text"]} for cue in cues],
    }
    models = [model]
    if fallback_model and fallback_model != model:
        models.append(fallback_model)

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Refine the subtitle text only.\n"
                + json.dumps(user_payload, ensure_ascii=False, indent=2)
            ),
        },
    ]
    last_error: Exception | None = None
    for candidate_model in models:
        try:
            payload = chat_json(
                client,
                candidate_model,
                messages,
                json_mode=json_mode,
                disable_thinking=disable_thinking,
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
            refined = payload.get("cues")
            if not isinstance(refined, list) or len(refined) != len(cues):
                raise ValueError("model returned an invalid cue list")
            output: list[dict] = []
            for original, item in zip(cues, refined, strict=True):
                if int(item.get("index")) != original["index"]:
                    raise ValueError("model changed cue ordering or indexes")
                text = str(item.get("text", "")).strip()
                if not text:
                    text = original["text"]
                output.append({"index": original["index"], "timing": original["timing"], "text": text})
            return output
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    raise RuntimeError(f"subtitle refinement failed for models {models}: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Refine subtitle text with a Groq text model")
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
        default="qwen/qwen3.8-27b",
        help="Primary Groq text model for subtitle refinement",
    )
    parser.add_argument(
        "--fallback-model",
        default="openai/gpt-oss-120b",
        help="Fallback model when the primary model fails",
    )
    parser.add_argument(
        "--language",
        default="zh-Hant",
        help="Target subtitle language hint. Defaults to zh-Hant",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=80,
        help="Number of cues per model call",
    )
    parser.add_argument(
        "--reference-chars",
        type=int,
        default=12000,
        help="Maximum reference context chars loaded from the edit directory",
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

    client = OpenAI(api_key=load_api_key(), base_url="https://api.groq.com/openai/v1")
    glossary_terms = load_glossary(glossary_path)
    reference_context = load_reference_context(edit_dir, max_chars=max(0, args.reference_chars))

    refined_cues: list[dict] = []
    for batch in chunked(cues, batch_size=max(1, args.batch_size)):
        refined_cues.extend(
            refine_batch(
                client=client,
                model=args.model,
                fallback_model=args.fallback_model.strip() or None,
                cues=batch,
                language=args.language,
                glossary_terms=glossary_terms,
                reference_context=reference_context,
            )
        )

    output_path = (args.output or srt_path).resolve()
    output_path.write_text(render_srt(refined_cues))
    print(f"refined subtitles: {output_path}")


if __name__ == "__main__":
    main()
