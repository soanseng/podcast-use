from __future__ import annotations

from pathlib import Path

import pytest

from build_subtitles import build_cues, chunk_words, format_srt_timestamp, words_for_segment, write_srt


def test_format_srt_timestamp() -> None:
    assert format_srt_timestamp(0) == "00:00:00,000"
    assert format_srt_timestamp(65.5) == "00:01:05,500"
    assert format_srt_timestamp(3661.234) == "01:01:01,234"


def test_words_for_segment_and_chunking() -> None:
    words = [
        {"word": "One", "start": 0.0, "end": 0.2},
        {"word": "two", "start": 0.25, "end": 0.4},
        {"word": "three.", "start": 0.45, "end": 0.7},
        {"word": "Four", "start": 0.8, "end": 1.0},
    ]
    kept = words_for_segment(words, 0.0, 0.7)
    assert [w["word"] for w in kept] == ["One", "two", "three."]

    chunks = chunk_words(kept, max_words=6)
    # punctuation break on "three."
    assert len(chunks) == 1
    assert chunks[0][-1]["word"] == "three."

    chunks = chunk_words(words, max_words=2)
    assert all(len(chunk) <= 2 or chunk[-1]["word"].endswith((".", "!", "?", ",")) for chunk in chunks)


def test_build_cues_output_timeline() -> None:
    words_by_source = {
        "episode": [
            {"word": "Hello", "start": 10.0, "end": 10.3},
            {"word": "world", "start": 10.4, "end": 10.8},
            {"word": "again", "start": 20.0, "end": 20.4},
        ]
    }
    edl = [
        {"source": "episode", "start": 10.0, "end": 10.8},
        {"source": "episode", "start": 20.0, "end": 20.4},
    ]
    cues = build_cues(words_by_source, edl, max_words=6)
    assert len(cues) >= 2
    # first cue starts near 0 on output timeline
    assert cues[0]["start"] == pytest.approx(0.0)
    # second segment starts after first duration 0.8
    assert any(c["start"] >= 0.8 for c in cues)


def test_write_srt(tmp_path: Path) -> None:
    path = tmp_path / "final.srt"
    write_srt(
        [
            {"start": 0.0, "end": 1.2, "text": "Hello world"},
            {"start": 1.3, "end": 2.0, "text": "Again"},
        ],
        path,
    )
    text = path.read_text()
    assert "1\n" in text
    assert "00:00:00,000 --> 00:00:01,200" in text
    assert "Hello world" in text
    assert "Again" in text
