from __future__ import annotations

import json
from pathlib import Path

import pytest

from edl_io import (
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
