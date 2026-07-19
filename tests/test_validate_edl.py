from __future__ import annotations

import json
from pathlib import Path

import pytest

from validate_edl import dropped_gaps, source_span, validate


def test_source_span_and_dropped_gaps() -> None:
    words = [
        {"word": "a", "start": 0.0, "end": 0.2},
        {"word": "b", "start": 5.0, "end": 5.3},
    ]
    assert source_span(words) == (0.0, 5.3)

    segments = [
        {"source": "episode", "start": 0.0, "end": 1.0},
        {"source": "episode", "start": 4.0, "end": 5.0},
    ]
    gaps = dropped_gaps(segments, "episode", source_end=6.0)
    assert len(gaps) == 2
    assert gaps[0]["start"] == pytest.approx(1.0)
    assert gaps[0]["end"] == pytest.approx(4.0)
    assert gaps[1]["start"] == pytest.approx(5.0)
    assert gaps[1]["end"] == pytest.approx(6.0)


def test_dropped_gaps_when_nothing_kept() -> None:
    gaps = dropped_gaps([], "episode", source_end=10.0)
    assert gaps == [{"start": 0.0, "end": 10.0, "duration": 10.0}]


def test_validate_ok(sample_edit: Path) -> None:
    (sample_edit / "edl.draft.json").write_text(
        json.dumps(
            [
                {"source": "episode", "start": 0.0, "end": 0.7, "reason": "open"},
                {"source": "episode", "start": 0.75, "end": 1.9, "reason": "rest"},
            ]
        )
    )
    code = validate(
        sample_edit,
        edl_path=sample_edit / "edl.draft.json",
        boundary_tol=0.04,
        edge_pad=0.0,
        strict=False,
    )
    assert code == 0
    report = json.loads((sample_edit / "edl_validation.json").read_text())
    assert report["segment_count"] == 2
    assert report["output_seconds"] == pytest.approx(1.85)
    assert report["errors"] == []


def test_validate_unknown_source_errors(sample_edit: Path) -> None:
    (sample_edit / "edl.draft.json").write_text(
        json.dumps([{"source": "missing", "start": 0.0, "end": 1.0}])
    )
    code = validate(
        sample_edit,
        edl_path=sample_edit / "edl.draft.json",
        boundary_tol=0.04,
        edge_pad=0.0,
        strict=False,
    )
    assert code == 1
    report = json.loads((sample_edit / "edl_validation.json").read_text())
    assert any("unknown source" in err for err in report["errors"])


def test_validate_mid_word_strict(sample_edit: Path) -> None:
    # 0.15 is inside Hello (0.0-0.3)
    (sample_edit / "edl.draft.json").write_text(
        json.dumps([{"source": "episode", "start": 0.15, "end": 0.7}])
    )
    code = validate(
        sample_edit,
        edl_path=sample_edit / "edl.draft.json",
        boundary_tol=0.01,
        edge_pad=0.0,
        strict=True,
    )
    assert code == 1
    report = json.loads((sample_edit / "edl_validation.json").read_text())
    assert report["errors"]


def test_validate_cli(sample_edit: Path) -> None:
    import subprocess
    import sys

    (sample_edit / "edl.draft.json").write_text(
        json.dumps([{"source": "episode", "start": 0.0, "end": 1.9}])
    )
    helper = Path(__file__).resolve().parents[1] / "helpers" / "validate_edl.py"
    result = subprocess.run(
        [
            sys.executable,
            str(helper),
            "--edit-dir",
            str(sample_edit),
            "--edl",
            str(sample_edit / "edl.draft.json"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "OK" in result.stdout
