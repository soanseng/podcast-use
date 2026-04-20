from __future__ import annotations

import argparse
import json
import os
import sys
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
) -> Path:
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcripts_dir / f"{audio_path.stem}.json"

    if out_path.exists():
        print(f"cached: {out_path}")
        return out_path

    client = Groq(api_key=load_api_key())
    with audio_path.open("rb") as file_obj:
        response = client.audio.transcriptions.create(
            file=(audio_path.name, file_obj.read()),
            model=model,
            language=language,
            prompt=prompt,
            response_format="verbose_json",
            temperature=0.0,
            timestamp_granularities=["word", "segment"],
        )

    payload = json.loads(response.model_dump_json())
    payload["source"] = audio_path.name
    payload["model"] = model
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True))
    print(f"saved: {out_path}")
    return out_path


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
    )


if __name__ == "__main__":
    main()
