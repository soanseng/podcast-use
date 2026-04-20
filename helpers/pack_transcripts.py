from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def format_time(seconds: float) -> str:
    return f"{seconds:06.2f}"


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remaining = seconds - minutes * 60
    return f"{minutes}m {remaining:04.1f}s"


def group_words(words: list[dict], silence_threshold: float) -> list[dict]:
    phrases: list[dict] = []
    current: list[dict] = []
    current_start: float | None = None
    prev_end: float | None = None

    def flush() -> None:
        nonlocal current, current_start
        if not current:
            return
        text = " ".join(item["word"].strip() for item in current if item.get("word", "").strip())
        text = text.replace(" ,", ",").replace(" .", ".").replace(" ?", "?").replace(" !", "!")
        if not text:
            current = []
            current_start = None
            return
        phrases.append(
            {
                "start": current_start,
                "end": current[-1]["end"],
                "text": text,
            }
        )
        current = []
        current_start = None

    for word in words:
        start = word.get("start")
        end = word.get("end")
        token = word.get("word", "")
        if start is None or end is None or not token:
            continue
        if prev_end is not None and start - prev_end >= silence_threshold:
            flush()
        if current_start is None:
            current_start = start
        current.append(word)
        prev_end = end

    flush()
    return phrases


def load_transcript(json_path: Path, silence_threshold: float) -> tuple[str, float, list[dict]]:
    payload = json.loads(json_path.read_text())
    words = payload.get("words", [])
    phrases = group_words(words, silence_threshold)
    if words:
        duration = float(words[-1]["end"]) - float(words[0]["start"])
    else:
        duration = 0.0
    return json_path.stem, duration, phrases


def render_markdown(entries: list[tuple[str, float, list[dict]]], silence_threshold: float) -> str:
    lines = [
        "# Packed transcripts",
        "",
        f"Phrase-level transcript grouped on silences >= {silence_threshold:.1f}s.",
        "Use these ranges when drafting edl.json.",
        "",
    ]
    for name, duration, phrases in entries:
        lines.append(f"## {name} (duration: {format_duration(duration)}, {len(phrases)} phrases)")
        if not phrases:
            lines.append("  _no speech detected_")
            lines.append("")
            continue
        for phrase in phrases:
            lines.append(
                f"  [{format_time(phrase['start'])}-{format_time(phrase['end'])}] {phrase['text']}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack Groq transcripts into takes_packed.md")
    parser.add_argument("--edit-dir", type=Path, required=True, help="Edit directory containing transcripts/")
    parser.add_argument(
        "--silence-threshold",
        type=float,
        default=0.5,
        help="Break phrases on silences >= this many seconds",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to <edit_dir>/takes_packed.md",
    )
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    transcripts_dir = edit_dir / "transcripts"
    if not transcripts_dir.is_dir():
        sys.exit(f"no transcripts directory at {transcripts_dir}")

    json_files = sorted(transcripts_dir.glob("*.json"))
    if not json_files:
        sys.exit(f"no .json files in {transcripts_dir}")

    entries = [load_transcript(path, args.silence_threshold) for path in json_files]
    markdown = render_markdown(entries, args.silence_threshold)
    output = args.output or (edit_dir / "takes_packed.md")
    output.write_text(markdown)
    print(f"packed {len(entries)} transcript(s) -> {output}")


if __name__ == "__main__":
    main()
