from __future__ import annotations

import json
from pathlib import Path

import pytest

from edl_io import (
    SILENCE_SOURCE,
    approve_edl,
    effective_range,
    format_clock,
    format_duration,
    load_segments,
    load_words,
    nearest_word_boundary,
    normalize_segment,
    resolve_edl_path,
    segment_duration,
    total_duration,
    write_edl,
)


def test_resolve_edl_prefers_approved(sample_edit: Path) -> None:
    (sample_edit / "edl.draft.json").write_text("[]")
    (sample_edit / "edl.json").write_text("[]")
    (sample_edit / "edl.approved.json").write_text("[]")
    assert resolve_edl_path(sample_edit).name == "edl.approved.json"


def test_resolve_edl_falls_back_to_draft(sample_edit: Path) -> None:
    (sample_edit / "edl.draft.json").write_text(
        json.dumps([{"source": "episode", "start": 0.0, "end": 0.3}])
    )
    assert resolve_edl_path(sample_edit).name == "edl.draft.json"


def test_resolve_edl_missing_exits(sample_edit: Path) -> None:
    with pytest.raises(SystemExit):
        resolve_edl_path(sample_edit)


def test_normalize_and_effective_range() -> None:
    segment = normalize_segment(
        {
            "source": "episode",
            "start": 1.0,
            "end": 2.0,
            "pad_in": 0.05,
            "pad_out": 0.1,
            "reason": "keep",
        },
        0,
    )
    start, end = effective_range(segment, edge_pad=0.04)
    assert start == pytest.approx(0.91)
    assert end == pytest.approx(2.14)
    assert segment_duration(segment, edge_pad=0.04) == pytest.approx(1.23)


def test_normalize_rejects_bad_ranges() -> None:
    with pytest.raises(SystemExit):
        normalize_segment({"source": "x", "start": 2, "end": 1}, 0)
    with pytest.raises(SystemExit):
        normalize_segment({"source": "x", "start": 1, "end": 2, "pad_in": -0.1}, 0)


def test_write_load_approve_roundtrip(sample_edit: Path) -> None:
    segments = [
        {"source": "episode", "start": 0.0, "end": 0.7, "reason": "open"},
        {"source": "episode", "start": 0.75, "end": 1.9, "reason": "body", "pad_out": 0.05},
    ]
    write_edl(sample_edit / "edl.draft.json", segments)
    path, loaded = load_segments(
        sample_edit,
        {"episode"},
        edl_path=sample_edit / "edl.draft.json",
    )
    assert path.name == "edl.draft.json"
    assert len(loaded) == 2
    # 0.7 + (1.15 + pad_out 0.05) = 1.9
    assert total_duration(loaded) == pytest.approx(1.9)
    assert loaded[1]["pad_out"] == pytest.approx(0.05)

    approved = approve_edl(sample_edit)
    assert approved.exists()
    assert (sample_edit / "edl.json").exists()
    resolved = resolve_edl_path(sample_edit)
    assert resolved.name == "edl.approved.json"


def test_load_words_and_nearest_boundary(sample_edit: Path, sample_words: list[dict]) -> None:
    words = load_words(sample_edit, "episode")
    assert len(words) == len(sample_words)

    boundary, delta = nearest_word_boundary(words, 0.0, "start")
    assert boundary == 0.0
    assert delta == 0.0

    boundary, delta = nearest_word_boundary(words, 0.72, "end")
    assert boundary == pytest.approx(0.7)
    assert delta == pytest.approx(0.02)


def test_format_helpers() -> None:
    assert format_duration(12.3) == "12.3s"
    assert format_duration(75.5).startswith("1m")
    assert format_clock(65.5) == "01:05.500"
    assert format_clock(3661.25).startswith("01:01:")


def test_normalize_silence_segment() -> None:
    segment = normalize_segment({"silence": 2.5, "reason": "beat"}, 0)
    assert segment["is_silence"] is True
    assert segment["source"] == SILENCE_SOURCE
    assert segment["end"] == pytest.approx(2.5)
    assert segment_duration(segment) == pytest.approx(2.5)

    with pytest.raises(SystemExit):
        normalize_segment({"silence": 0}, 0)
    with pytest.raises(SystemExit):
        normalize_segment({"silence": -1}, 0)


def test_normalize_audacity_ops() -> None:
    segment = normalize_segment(
        {"source": "episode", "start": 1.0, "end": 3.0, "gain_db": -6.0, "fade_in": 0.3, "fade_out": 0.4, "speed": 2.0},
        0,
    )
    assert segment["gain_db"] == pytest.approx(-6.0)
    assert segment["fade_in"] == pytest.approx(0.3)
    assert segment["fade_out"] == pytest.approx(0.4)
    assert segment["speed"] == pytest.approx(2.0)
    # 2.0s of source at 2x tempo occupies 1.0s of output
    assert segment_duration(segment) == pytest.approx(1.0)

    with pytest.raises(SystemExit):  # fades longer than the sped segment
        normalize_segment({"source": "e", "start": 0.0, "end": 1.0, "fade_in": 1.2, "speed": 2.0}, 0)
    with pytest.raises(SystemExit):  # speed out of ffmpeg atempo range
        normalize_segment({"source": "e", "start": 0.0, "end": 1.0, "speed": 9.0}, 0)
    with pytest.raises(SystemExit):  # gain out of range
        normalize_segment({"source": "e", "start": 0.0, "end": 1.0, "gain_db": 80.0}, 0)


def test_remove_mode_inverts_to_kept_complement(sample_edit: Path) -> None:
    payload = {
        "mode": "remove",
        "segments": [
            {"source": "episode", "start": 0.5, "end": 1.0, "reason": "um"},
            {"source": "episode", "start": 1.5, "end": 1.6, "reason": "slip"},
        ],
    }
    (sample_edit / "edl.remove.json").write_text(json.dumps(payload))
    _, kept = load_segments(
        sample_edit,
        {"episode"},
        edl_path=sample_edit / "edl.remove.json",
        source_durations={"episode": 2.0},
    )
    ranges = [(round(s["start"], 3), round(s["end"], 3)) for s in kept]
    assert ranges == [(0.0, 0.5), (1.0, 1.5), (1.6, 2.0)]
    assert total_duration(kept) == pytest.approx(1.4)


def test_remove_mode_rejects_silence(sample_edit: Path) -> None:
    payload = {"mode": "remove", "segments": [{"silence": 1.0}]}
    (sample_edit / "edl.remove.json").write_text(json.dumps(payload))
    with pytest.raises(SystemExit):
        load_segments(
            sample_edit,
            {"episode"},
            edl_path=sample_edit / "edl.remove.json",
            source_durations={"episode": 2.0},
        )


def test_write_edl_roundtrips_ops_and_silence(tmp_path: Path) -> None:
    segments = [
        normalize_segment({"source": "episode", "start": 1.0, "end": 2.0, "gain_db": -3.0, "fade_in": 0.1, "speed": 1.5}, 0),
        normalize_segment({"silence": 0.75}, 1),
    ]
    path = tmp_path / "edl.json"
    write_edl(path, segments)
    items = json.loads(path.read_text())
    assert items[0]["gain_db"] == pytest.approx(-3.0)
    assert items[0]["speed"] == pytest.approx(1.5)
    assert items[1]["silence"] == pytest.approx(0.75)
