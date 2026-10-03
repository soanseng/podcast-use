"""Transcribe audio with the local Taigi ASR model (Breeze-ASR-26 via LiteLLM).

Output matches the `edit/transcripts/<stem>.json` cache shape used by
transcribe_groq.py so pack/build_subtitles work unchanged.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import local_llm


def merge_prompt_and_glossary(prompt: str | None, glossary: Path | None) -> str | None:
    parts: list[str] = []
    if prompt and prompt.strip():
        parts.append(prompt.strip())
    if glossary and glossary.exists():
        terms = [line.strip() for line in glossary.read_text().splitlines() if line.strip()]
        if terms:
            parts.append("Glossary: " + ", ".join(terms))
    return "\n\n".join(parts) if parts else None


def extract_words(payload: dict) -> list[dict]:
    words = payload.get("words")
    if isinstance(words, list):
        cleaned = [w for w in words if w.get("word") and w.get("start") is not None and w.get("end") is not None]
        if cleaned:
            return cleaned
    collected: list[dict] = []
    for segment in payload.get("segments") or []:
        for word in segment.get("words") or []:
            if word.get("word") and word.get("start") is not None and word.get("end") is not None:
                collected.append(word)
    return collected


def transcribe(
    client,
    audio_path: Path,
    *,
    model: str,
    language: str | None,
    prompt: str | None,
) -> dict:
    attempts = [
        {"response_format": "verbose_json", "timestamp_granularities": ["word", "segment"]},
        {"response_format": "verbose_json"},
        {"response_format": "json"},
    ]

    last_error: Exception | None = None
    for attempt in attempts:
        kwargs: dict = {"model": model, "temperature": 0.0, **attempt}
        if language:
            kwargs["language"] = language
        if prompt:
            kwargs["prompt"] = prompt
        try:
            with audio_path.open("rb") as file_obj:
                response = client.audio.transcriptions.create(
                    file=(audio_path.name, file_obj.read()),
                    **kwargs,
                )
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            message = str(exc)
            if "timestamp_granularities" in message or "response_format" in message:
                print(
                    f"warning: server rejected {sorted(attempt)}; retrying with a simpler request",
                    file=sys.stderr,
                )
                continue
            raise
    else:
        raise RuntimeError(f"transcription failed for model {model}: {last_error}")

    if hasattr(response, "model_dump"):
        payload = response.model_dump()
    else:
        payload = json.loads(response.model_dump_json())
    if not isinstance(payload, dict):
        payload = {"text": str(payload)}
    payload.setdefault("words", extract_words(payload))
    return payload


def transcode_for_upload(audio_path: Path, tmp_dir: Path) -> Path:
    """Downmix large inputs to 16 kHz mono mp3 (whisper resamples anyway)."""
    out_path = tmp_dir / f"{audio_path.stem}.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "48k",
            str(out_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"transcoded upload: {out_path} ({out_path.stat().st_size // (1024 * 1024)} MiB)")
    return out_path


def transcribe_one(
    audio_path: Path,
    edit_dir: Path,
    *,
    model: str,
    language: str | None,
    prompt: str | None,
    glossary: Path | None,
    base_url: str | None,
    force: bool,
) -> Path:
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcripts_dir / f"{audio_path.stem}.json"

    if out_path.exists() and not force:
        print(f"cached: {out_path}")
        return out_path

    client = local_llm.make_client(base_url_override=base_url)
    merged_prompt = merge_prompt_and_glossary(prompt, glossary)

    max_bytes = 48 * 1024 * 1024
    if audio_path.stat().st_size > max_bytes:
        with tempfile.TemporaryDirectory(prefix="podcast-use-local-asr-") as tmp:
            upload_path = transcode_for_upload(audio_path, Path(tmp))
            payload = transcribe(
                client,
                upload_path,
                model=model,
                language=language,
                prompt=merged_prompt,
            )
    else:
        payload = transcribe(
            client,
            audio_path,
            model=model,
            language=language,
            prompt=merged_prompt,
        )

    payload["source"] = audio_path.name
    payload["model"] = model
    payload["provider"] = "local-litellm"
    if not payload.get("words"):
        print(
            "warning: response has no word timestamps; build_subtitles.py needs "
            "transcripts/<stem>.json['words'] and will produce no cues for this source, "
            "and validate_edl.py will skip word-boundary checks. Re-run with a model/server "
            "that returns verbose_json words, or transcribe with transcribe_groq.py.",
            file=sys.stderr,
        )
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True))
    print(f"saved: {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcribe audio with the local Taigi ASR model (LiteLLM)"
    )
    parser.add_argument("audio", type=Path, help="Path to an audio file")
    parser.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="Output edit directory. Defaults to <audio_dir>/edit",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="ASR model. Defaults to PODCAST_ASR_MODEL or breeze-asr-26-taigi",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override LITELLM_BASE_URL, e.g. http://100.102.183.27:4000/v1",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Optional language hint (e.g. zh, en). Taigi is auto-detected by the model",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Optional vocabulary guidance for names or jargon",
    )
    parser.add_argument(
        "--glossary",
        type=Path,
        default=None,
        help="Optional glossary file with one term per line",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Retranscribe even if a cached transcript already exists",
    )
    args = parser.parse_args()

    audio_path = args.audio.resolve()
    if not audio_path.exists():
        sys.exit(f"audio not found: {audio_path}")

    edit_dir = (args.edit_dir or (audio_path.parent / "edit")).resolve()
    transcribe_one(
        audio_path=audio_path,
        edit_dir=edit_dir,
        model=args.model or local_llm.asr_model(),
        language=args.language,
        prompt=args.prompt,
        glossary=args.glossary,
        base_url=args.base_url,
        force=args.force,
    )


if __name__ == "__main__":
    main()
