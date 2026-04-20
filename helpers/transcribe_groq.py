from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from groq import Groq


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


def transcribe_one(
    audio_path: Path,
    edit_dir: Path,
    model: str,
    language: str | None = None,
    prompt: str | None = None,
    glossary: Path | None = None,
    force: bool = False,
) -> Path:
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcripts_dir / f"{audio_path.stem}.json"

    if out_path.exists() and not force:
        print(f"cached: {out_path}")
        return out_path

    client = Groq(api_key=load_api_key())
    merged_prompt = merge_prompt_and_glossary(prompt, glossary)
    payload = transcribe_with_chunking(
        client=client,
        audio_path=audio_path,
        model=model,
        language=language,
        prompt=merged_prompt,
    )
    payload["source"] = audio_path.name
    payload["model"] = model
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True))
    print(f"saved: {out_path}")
    return out_path


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def maybe_transcode_audio(audio_path: Path, out_path: Path, codec: str) -> None:
    codec_args = {
        "flac": ["-c:a", "flac"],
        "mp3": ["-c:a", "libmp3lame", "-b:a", "32k"],
    }
    if codec not in codec_args:
        sys.exit(f"unsupported codec: {codec}")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        *codec_args[codec],
        str(out_path),
    ]
    run(cmd)


def get_audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def build_upload_candidate(audio_path: Path, temp_dir: Path, codec: str) -> Path:
    out_path = temp_dir / f"{audio_path.stem}.{codec}"
    maybe_transcode_audio(audio_path, out_path, codec=codec)
    return out_path


def prepare_upload_audio(audio_path: Path) -> tuple[Path, str, Path]:
    max_bytes = 24 * 1024 * 1024
    if audio_path.stat().st_size <= max_bytes:
        return audio_path, audio_path.name, audio_path.parent

    temp_dir = Path(tempfile.mkdtemp(prefix="podcast-use-transcribe-"))
    flac_path = build_upload_candidate(audio_path, temp_dir, "flac")
    if flac_path.stat().st_size <= max_bytes:
        print(f"transcoded upload: {flac_path}")
        return flac_path, flac_path.name, temp_dir

    mp3_path = build_upload_candidate(audio_path, temp_dir, "mp3")
    if mp3_path.stat().st_size <= max_bytes:
        print(f"transcoded upload: {mp3_path}")
        return mp3_path, mp3_path.name, temp_dir

    return mp3_path, mp3_path.name, temp_dir


def transcribe_payload(
    client: Groq,
    upload_path: Path,
    model: str,
    language: str | None,
    prompt: str | None,
) -> dict:
    with upload_path.open("rb") as file_obj:
        response = client.audio.transcriptions.create(
            file=(upload_path.name, file_obj.read()),
            model=model,
            language=language,
            prompt=prompt,
            response_format="verbose_json",
            temperature=0.0,
            timestamp_granularities=["word", "segment"],
        )
    return json.loads(response.model_dump_json())


def offset_items(items: list[dict], offset: float) -> list[dict]:
    adjusted: list[dict] = []
    for item in items:
        clone = dict(item)
        if clone.get("start") is not None:
            clone["start"] = float(clone["start"]) + offset
        if clone.get("end") is not None:
            clone["end"] = float(clone["end"]) + offset
        adjusted.append(clone)
    return adjusted


def chunk_audio(audio_path: Path, temp_dir: Path, chunk_seconds: int, overlap_seconds: int) -> list[dict]:
    duration = get_audio_duration(audio_path)
    chunks: list[dict] = []
    start = 0.0
    index = 0
    while start < duration:
        chunk_start = max(0.0, start)
        chunk_duration = min(chunk_seconds, duration - chunk_start)
        chunk_path = temp_dir / f"{audio_path.stem}_chunk_{index:04d}.flac"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{chunk_start:.3f}",
            "-t",
            f"{chunk_duration:.3f}",
            "-i",
            str(audio_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "flac",
            str(chunk_path),
        ]
        run(cmd)
        chunks.append(
            {
                "path": chunk_path,
                "start": chunk_start,
                "end": chunk_start + chunk_duration,
            }
        )
        if chunk_start + chunk_duration >= duration:
            break
        start += chunk_seconds - overlap_seconds
        index += 1
    return chunks


def dedupe_words(words: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[tuple[str, int, int]] = set()
    for word in sorted(words, key=lambda item: (item.get("start", 0.0), item.get("end", 0.0))):
        token = str(word.get("word", "")).strip()
        start_ms = int(round(float(word.get("start", 0.0)) * 1000))
        end_ms = int(round(float(word.get("end", 0.0)) * 1000))
        key = (token, start_ms, end_ms)
        if not token or key in seen:
            continue
        seen.add(key)
        deduped.append(word)
    return deduped


def dedupe_segments(segments: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[tuple[str, int, int]] = set()
    for segment in sorted(
        segments,
        key=lambda item: (item.get("start", 0.0), item.get("end", 0.0)),
    ):
        text = str(segment.get("text", "")).strip()
        start_ms = int(round(float(segment.get("start", 0.0)) * 1000))
        end_ms = int(round(float(segment.get("end", 0.0)) * 1000))
        key = (text, start_ms, end_ms)
        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(segment)
    return deduped


def merge_prompt_and_glossary(prompt: str | None, glossary: Path | None) -> str | None:
    parts: list[str] = []
    if prompt:
        parts.append(prompt.strip())
    if glossary:
        glossary_path = glossary.resolve()
        if not glossary_path.exists():
            sys.exit(f"glossary not found: {glossary_path}")
        terms = [
            line.strip()
            for line in glossary_path.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if terms:
            parts.append(
                "請優先正確辨識以下專有名詞、術語與混語詞彙，保留原語言，不要任意替換成相近但錯誤的詞：\n"
                + "\n".join(terms)
            )
    if not parts:
        return None
    return "\n\n".join(parts)


def combine_chunk_payloads(chunk_payloads: list[dict]) -> dict:
    words: list[dict] = []
    segments: list[dict] = []
    texts: list[str] = []
    for chunk in chunk_payloads:
        payload = chunk["payload"]
        offset = float(chunk["offset"])
        words.extend(offset_items(payload.get("words", []), offset))
        segments.extend(offset_items(payload.get("segments", []), offset))
        text = str(payload.get("text", "")).strip()
        if text:
            texts.append(text)

    return {
        "text": " ".join(texts).strip(),
        "words": dedupe_words(words),
        "segments": dedupe_segments(segments),
        "chunk_count": len(chunk_payloads),
    }


def transcribe_with_chunking(
    client: Groq,
    audio_path: Path,
    model: str,
    language: str | None,
    prompt: str | None,
) -> dict:
    upload_path, _, temp_dir = prepare_upload_audio(audio_path)
    max_bytes = 24 * 1024 * 1024
    if upload_path.stat().st_size <= max_bytes:
        return transcribe_payload(client, upload_path, model, language, prompt)

    chunk_seconds = 8 * 60
    overlap_seconds = 2
    chunks = chunk_audio(audio_path, temp_dir, chunk_seconds=chunk_seconds, overlap_seconds=overlap_seconds)
    chunk_payloads: list[dict] = []
    for chunk in chunks:
        chunk_path = chunk["path"]
        if chunk_path.stat().st_size > max_bytes:
            sys.exit(
                f"chunk still exceeds Groq upload limit: {chunk_path} ({chunk_path.stat().st_size} bytes)"
            )
        print(f"transcribing chunk: {chunk_path.name} @ {chunk['start']:.2f}s")
        payload = transcribe_payload(client, chunk_path, model, language, prompt)
        chunk_payloads.append({"offset": chunk["start"], "payload": payload})
    return combine_chunk_payloads(chunk_payloads)


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe audio with Groq Whisper")
    parser.add_argument("audio", type=Path, help="Path to an audio file")
    parser.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="Output edit directory. Defaults to <audio_dir>/edit",
    )
    parser.add_argument(
        "--model",
        default="whisper-large-v3-turbo",
        help="Groq speech-to-text model",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Optional ISO-639-1 language code",
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
        model=args.model,
        language=args.language,
        prompt=args.prompt,
        glossary=args.glossary,
        force=args.force,
    )


if __name__ == "__main__":
    main()
