from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def format_srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000
    minutes = milliseconds // 60_000
    milliseconds %= 60_000
    secs = milliseconds // 1000
    milliseconds %= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def load_edl(edit_dir: Path, source_stem: str) -> list[dict]:
    edl_path = edit_dir / "edl.json"
    if not edl_path.exists():
        sys.exit(f"missing EDL: {edl_path}")
    payload = json.loads(edl_path.read_text())
    segments = []
    for item in payload:
        if item.get("source") != source_stem:
            continue
        start = float(item["start"])
        end = float(item["end"])
        if end > start:
            segments.append({"start": start, "end": end})
    if not segments:
        sys.exit(f"no EDL segments found for source '{source_stem}'")
    return segments


def load_words(edit_dir: Path, source_stem: str) -> list[dict]:
    transcript_path = edit_dir / "transcripts" / f"{source_stem}.json"
    if not transcript_path.exists():
        sys.exit(f"missing transcript: {transcript_path}")
    payload = json.loads(transcript_path.read_text())
    return payload.get("words", [])


def words_for_segment(words: list[dict], start: float, end: float) -> list[dict]:
    kept = []
    for word in words:
        word_text = (word.get("word") or "").strip()
        word_start = word.get("start")
        word_end = word.get("end")
        if not word_text or word_start is None or word_end is None:
            continue
        if word_start >= start and word_end <= end:
            kept.append({"word": word_text, "start": float(word_start), "end": float(word_end)})
    return kept


def chunk_words(words: list[dict], max_words: int) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for word in words:
        current.append(word)
        punctuation_break = word["word"].endswith((".", "!", "?", ","))
        if len(current) >= max_words or punctuation_break:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def build_cues(words: list[dict], edl: list[dict], max_words: int) -> list[dict]:
    cues: list[dict] = []
    output_offset = 0.0
    for segment in edl:
        kept_words = words_for_segment(words, segment["start"], segment["end"])
        for chunk in chunk_words(kept_words, max_words=max_words):
            if not chunk:
                continue
            start = output_offset + (chunk[0]["start"] - segment["start"])
            end = output_offset + (chunk[-1]["end"] - segment["start"])
            text = " ".join(item["word"] for item in chunk)
            text = text.replace(" ,", ",").replace(" .", ".").replace(" ?", "?").replace(" !", "!")
            cues.append({"start": start, "end": max(start + 0.2, end), "text": text})
        output_offset += segment["end"] - segment["start"]
    return cues


def write_srt(cues: list[dict], output_path: Path) -> None:
    lines: list[str] = []
    for index, cue in enumerate(cues, start=1):
        lines.append(str(index))
        lines.append(
            f"{format_srt_timestamp(cue['start'])} --> {format_srt_timestamp(cue['end'])}"
        )
        lines.append(cue["text"])
        lines.append("")
    output_path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build output-timeline subtitles from edl.json")
    parser.add_argument("audio", type=Path, help="Path to source audio")
    parser.add_argument("--edit-dir", type=Path, default=None, help="Defaults to <audio_dir>/edit")
    parser.add_argument("--max-words", type=int, default=6, help="Max words per subtitle cue")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Defaults to <edit_dir>/final.srt")
    args = parser.parse_args()

    audio_path = args.audio.resolve()
    if not audio_path.exists():
        sys.exit(f"audio not found: {audio_path}")
    edit_dir = (args.edit_dir or (audio_path.parent / "edit")).resolve()
    output_path = args.output or (edit_dir / "final.srt")

    edl = load_edl(edit_dir, audio_path.stem)
    words = load_words(edit_dir, audio_path.stem)
    cues = build_cues(words, edl, max_words=max(1, args.max_words))
    if not cues:
        sys.exit("no subtitle cues generated")
    write_srt(cues, output_path)
    print(f"wrote subtitles: {output_path}")


if __name__ == "__main__":
    main()
