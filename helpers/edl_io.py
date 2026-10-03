from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


EDL_CANDIDATES = (
    "edl.approved.json",
    "edl.json",
    "edl.draft.json",
)

SILENCE_SOURCE = "_silence"


def load_edl_payload(edl_path: Path) -> tuple[str, list[dict]]:
    """Return (mode, items). Array payload means keep-mode."""
    raw = json.loads(edl_path.read_text())
    if isinstance(raw, dict):
        mode = str(raw.get("mode", "keep"))
        items = raw.get("segments")
    else:
        mode = "keep"
        items = raw
    if mode not in ("keep", "remove"):
        sys.exit(f"{edl_path.name}: mode must be 'keep' or 'remove', got {mode!r}")
    if not isinstance(items, list) or not items:
        sys.exit(f"{edl_path.name} must be a non-empty JSON array or an object with 'segments'")
    return mode, items


def resolve_edl_path(edit_dir: Path, preferred: Path | None = None) -> Path:
    """Resolve which EDL file to use.

    Preference order for final work:
    1. explicit path
    2. edl.approved.json
    3. edl.json (legacy / approved alias)
    4. edl.draft.json
    """
    if preferred is not None:
        path = preferred.resolve()
        if not path.exists():
            sys.exit(f"missing EDL: {path}")
        return path

    for name in EDL_CANDIDATES:
        path = edit_dir / name
        if path.exists():
            return path

    sys.exit(
        f"missing EDL in {edit_dir}. Expected one of: {', '.join(EDL_CANDIDATES)}"
    )


def normalize_segment(item: dict, index: int) -> dict:
    if "silence" in item:
        try:
            duration = float(item["silence"])
        except (TypeError, ValueError):
            sys.exit(f"invalid segment at index {index}: silence must be a number")
        if duration <= 0:
            sys.exit(f"invalid segment at index {index}: silence must be > 0")
        return {
            "source": SILENCE_SOURCE,
            "start": 0.0,
            "end": duration,
            "pad_in": 0.0,
            "pad_out": 0.0,
            "gain_db": 0.0,
            "fade_in": 0.0,
            "fade_out": 0.0,
            "speed": 1.0,
            "reason": str(item.get("reason") or "").strip(),
            "is_silence": True,
            "raw": item,
        }

    try:
        source = str(item["source"]).strip()
        start = float(item["start"])
        end = float(item["end"])
    except (KeyError, TypeError, ValueError) as exc:
        sys.exit(f"invalid segment at index {index}: {exc}")

    if not source:
        sys.exit(f"invalid segment at index {index}: empty source")
    if end <= start:
        sys.exit(f"invalid segment at index {index}: end must be greater than start")

    pad_in = float(item.get("pad_in", 0.0) or 0.0)
    pad_out = float(item.get("pad_out", 0.0) or 0.0)
    if pad_in < 0 or pad_out < 0:
        sys.exit(f"invalid segment at index {index}: pad values must be >= 0")

    try:
        gain_db = float(item.get("gain_db", 0.0) or 0.0)
        fade_in = float(item.get("fade_in", 0.0) or 0.0)
        fade_out = float(item.get("fade_out", 0.0) or 0.0)
        speed = float(item.get("speed", 1.0) or 1.0)
    except (TypeError, ValueError):
        sys.exit(f"invalid segment at index {index}: gain_db/fade_in/fade_out/speed must be numbers")
    if not -60.0 <= gain_db <= 30.0:
        sys.exit(f"invalid segment at index {index}: gain_db must be within -60..30")
    if fade_in < 0 or fade_out < 0:
        sys.exit(f"invalid segment at index {index}: fade values must be >= 0")
    if not 0.25 <= speed <= 4.0:
        sys.exit(f"invalid segment at index {index}: speed must be within 0.25..4.0")
    if (fade_in + fade_out) * speed > (end - start) + pad_in + pad_out + 1e-9:
        sys.exit(f"invalid segment at index {index}: fades longer than segment")

    return {
        "source": source,
        "start": start,
        "end": end,
        "pad_in": pad_in,
        "pad_out": pad_out,
        "gain_db": gain_db,
        "fade_in": fade_in,
        "fade_out": fade_out,
        "speed": speed,
        "reason": str(item.get("reason") or "").strip(),
        "is_silence": False,
        "raw": item,
    }


def invert_segments(
    removed: list[dict],
    *,
    edit_dir: Path,
    source_durations: dict[str, float] | None = None,
) -> list[dict]:
    """Audacity-style remove EDL: keep the complement of the removed ranges."""
    if any(seg.get("is_silence") for seg in removed):
        sys.exit("mode 'remove' cannot contain silence segments")
    durations: dict[str, float] = dict(source_durations or {})
    for seg in removed:
        source = seg["source"]
        if source in durations:
            continue
        words = load_words(edit_dir, source)
        if not words:
            sys.exit(
                f"mode 'remove' needs an audio duration or transcript for source '{source}'"
            )
        durations[source] = float(words[-1]["end"])

    kept: list[dict] = []
    for source, total in durations.items():
        cursor = 0.0
        spans = sorted(
            (seg for seg in removed if seg["source"] == source),
            key=lambda seg: seg["start"],
        )
        for seg in spans:
            if seg["start"] > cursor + 1e-6:
                kept.append(_kept_segment(source, cursor, min(seg["start"], total)))
            cursor = max(cursor, seg["end"])
        if total > cursor + 1e-6:
            kept.append(_kept_segment(source, cursor, total))
    return kept


def _kept_segment(source: str, start: float, end: float) -> dict:
    return {
        "source": source,
        "start": start,
        "end": end,
        "pad_in": 0.0,
        "pad_out": 0.0,
        "gain_db": 0.0,
        "fade_in": 0.0,
        "fade_out": 0.0,
        "speed": 1.0,
        "reason": "kept (remove-mode complement)",
        "is_silence": False,
        "raw": {},
    }


def load_segments(
    edit_dir: Path,
    allowed_sources: set[str] | None = None,
    *,
    edl_path: Path | None = None,
    require_allowed: bool = True,
    source_durations: dict[str, float] | None = None,
) -> tuple[Path, list[dict]]:
    path = resolve_edl_path(edit_dir, edl_path)
    mode, payload = load_edl_payload(path)
    segments: list[dict] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            sys.exit(f"invalid segment at index {index}: expected object")
        segment = normalize_segment(item, index)
        if segment.get("is_silence"):
            segments.append(segment)
            continue
        if allowed_sources is not None and segment["source"] not in allowed_sources:
            if require_allowed:
                continue
        segments.append(segment)

    if mode == "remove":
        segments = invert_segments(
            segments,
            edit_dir=edit_dir,
            source_durations=source_durations,
        )

    if (
        allowed_sources is not None
        and require_allowed
        and not any(not seg.get("is_silence") for seg in segments)
    ):
        sys.exit(f"no EDL segments found for sources {sorted(allowed_sources)} in {path}")
    return path, segments


def effective_range(
    segment: dict,
    *,
    edge_pad: float = 0.0,
    source_duration: float | None = None,
) -> tuple[float, float]:
    start = max(0.0, float(segment["start"]) - float(segment.get("pad_in", 0.0)) - edge_pad)
    end = float(segment["end"]) + float(segment.get("pad_out", 0.0)) + edge_pad
    if source_duration is not None:
        end = min(end, source_duration)
    if end <= start:
        sys.exit(
            f"effective range invalid for {segment['source']} "
            f"{segment['start']:.3f}-{segment['end']:.3f}"
        )
    return start, end


def segment_duration(segment: dict, *, edge_pad: float = 0.0) -> float:
    start, end = effective_range(segment, edge_pad=edge_pad)
    speed = float(segment.get("speed", 1.0) or 1.0)
    return (end - start) / max(speed, 1e-6)


def total_duration(segments: list[dict], *, edge_pad: float = 0.0) -> float:
    return sum(segment_duration(seg, edge_pad=edge_pad) for seg in segments)


def write_edl(path: Path, segments: list[dict]) -> None:
    payload = []
    for segment in segments:
        if segment.get("is_silence"):
            item: dict = {"silence": round(float(segment["end"]) - float(segment["start"]), 3)}
            if segment.get("reason"):
                item["reason"] = segment["reason"]
            payload.append(item)
            continue
        item = {
            "source": segment["source"],
            "start": round(float(segment["start"]), 3),
            "end": round(float(segment["end"]), 3),
        }
        if segment.get("pad_in"):
            item["pad_in"] = round(float(segment["pad_in"]), 3)
        if segment.get("pad_out"):
            item["pad_out"] = round(float(segment["pad_out"]), 3)
        if segment.get("gain_db"):
            item["gain_db"] = round(float(segment["gain_db"]), 2)
        if segment.get("fade_in"):
            item["fade_in"] = round(float(segment["fade_in"]), 3)
        if segment.get("fade_out"):
            item["fade_out"] = round(float(segment["fade_out"]), 3)
        if segment.get("speed") and abs(float(segment["speed"]) - 1.0) > 1e-9:
            item["speed"] = round(float(segment["speed"]), 4)
        if segment.get("reason"):
            item["reason"] = segment["reason"]
        payload.append(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def approve_edl(edit_dir: Path, source_name: str = "edl.draft.json") -> Path:
    source = edit_dir / source_name
    if not source.exists():
        legacy = edit_dir / "edl.json"
        if legacy.exists() and source_name == "edl.draft.json":
            source = legacy
        else:
            sys.exit(f"missing draft EDL: {edit_dir / source_name}")
    approved = edit_dir / "edl.approved.json"
    shutil.copy2(source, approved)
    # Keep legacy alias in sync for older helper call sites.
    shutil.copy2(approved, edit_dir / "edl.json")
    return approved


def load_words(edit_dir: Path, source_stem: str) -> list[dict]:
    transcript_path = edit_dir / "transcripts" / f"{source_stem}.json"
    if not transcript_path.exists():
        return []
    payload = json.loads(transcript_path.read_text())
    words = []
    for word in payload.get("words", []):
        token = (word.get("word") or "").strip()
        start = word.get("start")
        end = word.get("end")
        if not token or start is None or end is None:
            continue
        words.append({"word": token, "start": float(start), "end": float(end)})
    return words


def nearest_word_boundary(words: list[dict], t: float, side: str) -> tuple[float | None, float]:
    """Return (boundary_time, abs_delta). side is 'start' or 'end'."""
    if not words:
        return None, float("inf")

    if side == "start":
        candidates = [w["start"] for w in words]
    else:
        candidates = [w["end"] for w in words]

    best = min(candidates, key=lambda value: abs(value - t))
    return best, abs(best - t)


def format_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    rem = seconds - minutes * 60
    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}h {minutes:02d}m {rem:04.1f}s"
    if minutes > 0:
        return f"{minutes}m {rem:04.1f}s"
    return f"{rem:.1f}s"


def format_clock(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    return f"{minutes:02d}:{secs:06.3f}"
