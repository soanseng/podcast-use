from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from edl_io import effective_range, load_segments, resolve_edl_path, segment_duration
from render_audio import probe_duration


def format_srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000
    minutes = milliseconds // 60_000
    milliseconds %= 60_000
    secs = milliseconds // 1000
    milliseconds %= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def load_words(edit_dir: Path, source_stem: str) -> list[dict]:
    transcripts = edit_dir / "transcripts"
    punct_path = transcripts / f"{source_stem}.punct.json"
    transcript_path = transcripts / f"{source_stem}.json"
    if not transcript_path.exists() and not punct_path.exists():
        sys.exit(f"missing transcript: {transcript_path}")
    payload = json.loads((punct_path if punct_path.exists() else transcript_path).read_text())
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


PUNCTUATION = (".", "!", "?", ",", "，", "。", "！", "？", "、", "；", "：")
DEFAULT_MAX_GAP = 0.35
DEFAULT_MAX_CUE_SECONDS = 3.5


def chunk_words(
    words: list[dict],
    max_words: int,
    *,
    max_gap: float = DEFAULT_MAX_GAP,
    max_cue_seconds: float | None = DEFAULT_MAX_CUE_SECONDS,
) -> list[list[dict]]:
    """Group words into subtitle cues.

    Break points, checked per word: trailing punctuation, a silence gap before
    the word, the duration cap, then the hard word cap. Breaking on pauses
    keeps cuts off mid-phrase (critical for char-level zh tokens).
    """
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for word in words:
        if current:
            gap = word["start"] - current[-1]["end"]
            duration = word["end"] - current[0]["start"]
            over_cap = len(current) >= max_words
            over_time = max_cue_seconds is not None and duration > max_cue_seconds
            long_gap = gap >= max_gap
            punctuated = current[-1]["word"].endswith(PUNCTUATION)
            if punctuated or long_gap or over_time or over_cap:
                chunks.append(current)
                current = []
        current.append(word)
    if current:
        chunks.append(current)
    return chunks


_CJK_SPACE = re.compile(r"(?<=[\u3000-\u9fff\uff01-\uff65])\s+(?=[\u3000-\u9fff\uff01-\uff65])")


def cue_text(chunk: list[dict]) -> str:
    text = " ".join(item["word"] for item in chunk)
    text = text.replace(" ,", ",").replace(" .", ".").replace(" ?", "?").replace(" !", "!")
    return _CJK_SPACE.sub("", text).strip()


def build_cues(
    words_by_source: dict[str, list[dict]],
    edl: list[dict],
    max_words: int,
    *,
    edge_pad: float = 0.0,
    source_durations: dict[str, float] | None = None,
    max_gap: float = DEFAULT_MAX_GAP,
    max_cue_seconds: float | None = DEFAULT_MAX_CUE_SECONDS,
) -> list[dict]:
    cues: list[dict] = []
    output_offset = 0.0
    durations = source_durations or {}
    for segment in edl:
        speed = max(float(segment.get("speed", 1.0) or 1.0), 1e-6)
        if segment.get("is_silence"):
            output_offset += segment_duration(segment)
            continue
        words = words_by_source[segment["source"]]
        start_ref, end_ref = effective_range(
            segment,
            edge_pad=edge_pad,
            source_duration=durations.get(segment["source"]),
        )
        kept_words = words_for_segment(words, segment["start"], segment["end"])
        for chunk in chunk_words(
            kept_words,
            max_words=max_words,
            max_gap=max_gap,
            max_cue_seconds=max_cue_seconds,
        ):
            if not chunk:
                continue
            start = output_offset + (chunk[0]["start"] - start_ref) / speed
            end = output_offset + (chunk[-1]["end"] - start_ref) / speed
            cues.append({"start": start, "end": max(start + 0.2, end), "text": cue_text(chunk)})
        output_offset += (end_ref - start_ref) / speed
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


def run_refine_srt(
    *,
    srt_path: Path,
    edit_dir: Path,
    model: str,
    fallback_model: str | None,
    language: str,
    batch_size: int | None,
    reference_chars: int,
    script: str = "refine_srt_groq.py",
) -> None:
    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parent / script),
        str(srt_path),
        "--edit-dir",
        str(edit_dir),
        "--language",
        language,
        "--reference-chars",
        str(reference_chars),
    ]
    if batch_size is not None:
        cmd.extend(["--batch-size", str(batch_size)])
    if model:
        cmd.extend(["--model", model])
    if fallback_model:
        cmd.extend(["--fallback-model", fallback_model])
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build output-timeline subtitles from an EDL")
    parser.add_argument("audio", nargs="+", type=Path, help="One or more source audio paths")
    parser.add_argument("--edit-dir", type=Path, default=None, help="Defaults to <first_audio_dir>/edit")
    parser.add_argument(
        "--edl",
        type=Path,
        default=None,
        help="Explicit EDL path. Defaults to edl.approved.json, edl.json, or edl.draft.json",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=24,
        help="Hard cap of words per cue. Cues primarily break at punctuation and pauses",
    )
    parser.add_argument(
        "--max-cue-seconds",
        type=float,
        default=DEFAULT_MAX_CUE_SECONDS,
        help=f"Duration cap per cue in seconds (default: {DEFAULT_MAX_CUE_SECONDS})",
    )
    parser.add_argument(
        "--max-gap",
        type=float,
        default=DEFAULT_MAX_GAP,
        help=f"Break a cue when the silence gap before a word reaches this many seconds (default: {DEFAULT_MAX_GAP})",
    )
    parser.add_argument("-o", "--output", type=Path, default=None, help="Defaults to <edit_dir>/final.srt")
    parser.add_argument(
        "--refine-groq",
        action="store_true",
        help="Run the optional Groq subtitle refinement pass after writing the SRT",
    )
    parser.add_argument(
        "--refine-local",
        action="store_true",
        help="Run subtitle refinement against the local LiteLLM endpoint (qwen36-genesis)",
    )
    parser.add_argument(
        "--edge-pad-ms",
        type=float,
        default=40.0,
        help="Pad per segment in milliseconds, must match render_audio.py (default: 40)",
    )
    parser.add_argument(
        "--refine-model",
        default="qwen/qwen3.8-27b",
        help="Primary Groq text model for subtitle refinement",
    )
    parser.add_argument(
        "--refine-fallback-model",
        default="openai/gpt-oss-120b",
        help="Fallback Groq text model for subtitle refinement. Use an empty string to disable fallback.",
    )
    parser.add_argument(
        "--refine-language",
        default="zh-Hant",
        help="Language hint for subtitle refinement",
    )
    parser.add_argument(
        "--refine-batch-size",
        type=int,
        default=None,
        help="Cues per refinement request. Default: auto (80, or 160 for long episodes)",
    )
    parser.add_argument(
        "--refine-reference-chars",
        type=int,
        default=12000,
        help="Maximum reference context chars loaded during subtitle refinement",
    )
    parser.add_argument(
        "--local-refine-model",
        default=None,
        help="Local refinement model. Defaults to PODCAST_REFINE_MODEL or qwen36-genesis",
    )
    args = parser.parse_args()

    if args.refine_groq and args.refine_local:
        sys.exit("choose either --refine-groq or --refine-local, not both")

    audio_paths = [path.resolve() for path in args.audio]
    missing = [str(path) for path in audio_paths if not path.exists()]
    if missing:
        sys.exit(f"audio not found: {', '.join(missing)}")
    edit_dir = (args.edit_dir or (audio_paths[0].parent / "edit")).resolve()
    output_path = args.output or (edit_dir / "final.srt")

    words_by_source = {path.stem: load_words(edit_dir, path.stem) for path in audio_paths}
    source_durations = {
        path.stem: duration
        for path in audio_paths
        if (duration := probe_duration(path)) is not None
    }
    edge_pad = max(0.0, args.edge_pad_ms / 1000.0)
    edl_path = resolve_edl_path(edit_dir, args.edl)
    _, edl = load_segments(
        edit_dir,
        set(words_by_source),
        edl_path=edl_path,
        source_durations=source_durations,
    )
    cues = build_cues(
        words_by_source,
        edl,
        max_words=max(1, args.max_words),
        edge_pad=edge_pad,
        source_durations=source_durations,
        max_gap=max(0.0, args.max_gap),
        max_cue_seconds=max(0.1, args.max_cue_seconds) if args.max_cue_seconds > 0 else None,
    )
    if not cues:
        sys.exit("no subtitle cues generated")
    write_srt(cues, output_path)
    print(f"edl: {edl_path}")
    print(f"wrote subtitles: {output_path} ({len(cues)} cues)")
    batch_size = max(1, args.refine_batch_size) if args.refine_batch_size else None
    if args.refine_groq:
        run_refine_srt(
            srt_path=output_path,
            edit_dir=edit_dir,
            model=args.refine_model,
            fallback_model=args.refine_fallback_model.strip() or None,
            language=args.refine_language,
            batch_size=batch_size,
            reference_chars=max(0, args.refine_reference_chars),
        )
    if args.refine_local:
        run_refine_srt(
            srt_path=output_path,
            edit_dir=edit_dir,
            model=args.local_refine_model or "",
            fallback_model=None,
            language=args.refine_language,
            batch_size=batch_size,
            reference_chars=max(0, args.refine_reference_chars),
            script="refine_srt_local.py",
        )


if __name__ == "__main__":
    main()
