from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from edl_io import (
    format_clock,
    format_duration,
    load_segments,
    load_words,
    nearest_word_boundary,
    resolve_edl_path,
    segment_duration,
    total_duration,
)


def source_span(words: list[dict]) -> tuple[float, float] | None:
    if not words:
        return None
    return words[0]["start"], words[-1]["end"]


def dropped_gaps(segments: list[dict], source: str, source_end: float) -> list[dict]:
    """Estimate dropped ranges on a single source timeline (chronological keep list)."""
    kept = sorted(
        [s for s in segments if s["source"] == source],
        key=lambda s: s["start"],
    )
    if not kept:
        return [{"start": 0.0, "end": source_end, "duration": source_end}] if source_end > 0 else []

    gaps: list[dict] = []
    cursor = 0.0
    for seg in kept:
        if seg["start"] > cursor + 0.05:
            gaps.append(
                {
                    "start": cursor,
                    "end": seg["start"],
                    "duration": seg["start"] - cursor,
                }
            )
        cursor = max(cursor, seg["end"])
    if source_end > cursor + 0.05:
        gaps.append({"start": cursor, "end": source_end, "duration": source_end - cursor})
    return gaps


def validate(
    edit_dir: Path,
    *,
    edl_path: Path | None,
    boundary_tol: float,
    edge_pad: float,
    strict: bool,
) -> int:
    path = resolve_edl_path(edit_dir, edl_path)
    _, segments = load_segments(edit_dir, allowed_sources=None, edl_path=path, require_allowed=False)

    transcripts_dir = edit_dir / "transcripts"
    known_sources = {p.stem for p in transcripts_dir.glob("*.json")} if transcripts_dir.is_dir() else set()

    errors: list[str] = []
    warnings: list[str] = []
    words_by_source: dict[str, list[dict]] = {}

    for index, seg in enumerate(segments):
        if seg.get("is_silence"):
            continue
        source = seg["source"]
        if source not in words_by_source:
            words_by_source[source] = load_words(edit_dir, source)
        words = words_by_source[source]

        if known_sources and source not in known_sources:
            errors.append(f"[{index}] unknown source stem '{source}' (no transcripts/{source}.json)")

        if not words:
            warnings.append(f"[{index}] no word timestamps for source '{source}'; skip boundary checks")
            continue

        span = source_span(words)
        assert span is not None
        src_start, src_end = span
        if seg["start"] < src_start - 0.25 or seg["end"] > src_end + 0.25:
            warnings.append(
                f"[{index}] range {format_clock(seg['start'])}-{format_clock(seg['end'])} "
                f"is outside transcript span {format_clock(src_start)}-{format_clock(src_end)}"
            )

        start_boundary, start_delta = nearest_word_boundary(words, seg["start"], "start")
        end_boundary, end_delta = nearest_word_boundary(words, seg["end"], "end")
        if start_delta > boundary_tol:
            msg = (
                f"[{index}] start {seg['start']:.3f} is {start_delta*1000:.0f}ms from nearest "
                f"word start {start_boundary:.3f}"
            )
            (errors if strict else warnings).append(msg)
        if end_delta > boundary_tol:
            msg = (
                f"[{index}] end {seg['end']:.3f} is {end_delta*1000:.0f}ms from nearest "
                f"word end {end_boundary:.3f}"
            )
            (errors if strict else warnings).append(msg)

        # Mid-word cut heuristic: start falls strictly inside a word body.
        for word in words:
            if word["start"] + 0.02 < seg["start"] < word["end"] - 0.02:
                msg = (
                    f"[{index}] start appears mid-word '{word['word']}' "
                    f"({word['start']:.3f}-{word['end']:.3f})"
                )
                (errors if strict else warnings).append(msg)
                break
        for word in words:
            if word["start"] + 0.02 < seg["end"] < word["end"] - 0.02:
                msg = (
                    f"[{index}] end appears mid-word '{word['word']}' "
                    f"({word['start']:.3f}-{word['end']:.3f})"
                )
                (errors if strict else warnings).append(msg)
                break

    # Overlap check per source
    by_source: dict[str, list[tuple[int, dict]]] = {}
    for index, seg in enumerate(segments):
        if seg.get("is_silence"):
            continue
        by_source.setdefault(seg["source"], []).append((index, seg))
    for source, items in by_source.items():
        ordered = sorted(items, key=lambda pair: pair[1]["start"])
        for (i1, a), (i2, b) in zip(ordered, ordered[1:]):
            if b["start"] < a["end"] - 0.01:
                warnings.append(
                    f"overlap on '{source}': segment [{i1}] ends {a['end']:.3f}, "
                    f"[{i2}] starts {b['start']:.3f}"
                )

    kept = total_duration(segments, edge_pad=edge_pad)
    source_totals: dict[str, float] = {}
    for source, words in words_by_source.items():
        span = source_span(words)
        if span:
            source_totals[source] = span[1] - span[0]
        else:
            source_totals[source] = 0.0
    source_total = sum(source_totals.values()) if source_totals else 0.0
    removed = max(0.0, source_total - kept)

    print(f"EDL: {path}")
    print(f"segments: {len(segments)}")
    print(f"estimated output: {format_duration(kept)} ({kept:.2f}s)")
    if source_total > 0:
        print(
            f"source speech span: {format_duration(source_total)} | "
            f"removed ~{format_duration(removed)} ({(removed / source_total) * 100:.1f}%)"
        )

    print("\nSegments:")
    for index, seg in enumerate(segments):
        dur = segment_duration(seg, edge_pad=edge_pad)
        reason = f" — {seg['reason']}" if seg.get("reason") else ""
        if seg.get("is_silence"):
            print(f"  [{index:02d}] silence ({format_duration(dur)}){reason}")
            continue
        ops: list[str] = []
        if seg.get("gain_db"):
            ops.append(f"gain {seg['gain_db']:+.1f}dB")
        if abs(float(seg.get("speed", 1.0) or 1.0) - 1.0) > 1e-9:
            ops.append(f"speed {float(seg['speed']):.2f}x")
        if seg.get("fade_in"):
            ops.append(f"fade-in {seg['fade_in']:.2f}s")
        if seg.get("fade_out"):
            ops.append(f"fade-out {seg['fade_out']:.2f}s")
        op_text = f" [{', '.join(ops)}]" if ops else ""
        print(
            f"  [{index:02d}] {seg['source']} "
            f"{format_clock(seg['start'])}-{format_clock(seg['end'])} "
            f"({format_duration(dur)}){op_text}{reason}"
        )

    # Largest dropped gaps per source (helpful review surface)
    print("\nLargest dropped gaps (per source, chronological keep assumption):")
    any_gaps = False
    for source, words in words_by_source.items():
        span = source_span(words)
        if not span:
            continue
        gaps = sorted(
            dropped_gaps(segments, source, span[1]),
            key=lambda g: g["duration"],
            reverse=True,
        )[:5]
        if not gaps:
            continue
        any_gaps = True
        print(f"  {source}:")
        for gap in gaps:
            print(
                f"    - {format_clock(gap['start'])}-{format_clock(gap['end'])} "
                f"({format_duration(gap['duration'])})"
            )
    if not any_gaps:
        print("  (none detected)")

    report = {
        "edl": str(path),
        "segment_count": len(segments),
        "output_seconds": kept,
        "source_seconds": source_total,
        "removed_seconds": removed,
        "errors": errors,
        "warnings": warnings,
    }
    report_path = edit_dir / "edl_validation.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"\nreport: {report_path}")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for item in warnings:
            print(f"  - {item}")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for item in errors:
            print(f"  - {item}")
        return 1

    print("\nOK")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate an edit decision list against word timestamps"
    )
    parser.add_argument("--edit-dir", type=Path, required=True, help="Edit directory")
    parser.add_argument(
        "--edl",
        type=Path,
        default=None,
        help="Explicit EDL path. Defaults to edl.approved.json, edl.json, or edl.draft.json",
    )
    parser.add_argument(
        "--boundary-tol",
        type=float,
        default=0.04,
        help="Max seconds from nearest word boundary before warning/error",
    )
    parser.add_argument(
        "--edge-pad",
        type=float,
        default=0.0,
        help="Global edge pad seconds to include in duration estimate",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat boundary and mid-word issues as errors",
    )
    args = parser.parse_args()
    edit_dir = args.edit_dir.resolve()
    if not edit_dir.is_dir():
        sys.exit(f"edit dir not found: {edit_dir}")
    raise SystemExit(
        validate(
            edit_dir,
            edl_path=args.edl,
            boundary_tol=args.boundary_tol,
            edge_pad=args.edge_pad,
            strict=args.strict,
        )
    )


if __name__ == "__main__":
    main()
