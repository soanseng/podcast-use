from __future__ import annotations

from pathlib import Path

import pytest

from build_subtitles import build_cues, chunk_words, cue_text, format_srt_timestamp, words_for_segment, write_srt


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


def test_build_cues_silence_and_speed() -> None:
    words_by_source = {
        "episode": [
            {"word": "Hello", "start": 0.0, "end": 0.4},
            {"word": "world", "start": 5.0, "end": 5.4},
        ]
    }
    edl = [
        {"source": "episode", "start": 0.0, "end": 0.4, "speed": 2.0},
        {"silence": 1.0, "is_silence": True, "start": 0.0, "end": 1.0, "speed": 1.0},
        {"source": "episode", "start": 5.0, "end": 5.4},
    ]
    cues = build_cues(words_by_source, edl, max_words=6)
    # 0.4s of audio at 2x tempo occupies 0.2s of output
    assert cues[0]["start"] == pytest.approx(0.0)
    assert cues[0]["end"] == pytest.approx(0.2)
    # next cue starts after tempo-divided segment plus inserted silence
    assert cues[1]["start"] == pytest.approx(1.2)
    assert cues[1]["end"] == pytest.approx(1.6)


def test_build_cues_edge_pad_matches_render_offset() -> None:
    words_by_source = {
        "episode": [
            {"word": "a", "start": 1.0, "end": 1.2},
            {"word": "b", "start": 3.0, "end": 3.2},
        ]
    }
    edl = [
        {"source": "episode", "start": 1.0, "end": 1.2},
        {"source": "episode", "start": 3.0, "end": 3.2},
    ]
    unpadded = build_cues(words_by_source, edl, max_words=6)
    padded = build_cues(words_by_source, edl, max_words=6, edge_pad=0.04)
    assert unpadded[1]["start"] == pytest.approx(0.2)
    assert padded[1]["start"] == pytest.approx(0.32)


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


def test_chunk_words_breaks_on_pause_gap() -> None:
    words = [
        {"word": "a", "start": 0.0, "end": 0.3},
        {"word": "b", "start": 0.35, "end": 0.6},
        {"word": "c", "start": 1.2, "end": 1.4},
    ]
    chunks = chunk_words(words, max_words=10)
    assert [[w["word"] for w in chunk] for chunk in chunks] == [["a", "b"], ["c"]]


def test_chunk_words_breaks_after_punctuation() -> None:
    words = [
        {"word": "好，", "start": 0.0, "end": 0.3},
        {"word": "我", "start": 0.35, "end": 0.6},
    ]
    chunks = chunk_words(words, max_words=10, max_gap=5.0)
    assert [w["word"] for w in chunks[0]] == ["好，"]
    assert [w["word"] for w in chunks[1]] == ["我"]


def test_chunk_words_duration_cap_splits_long_runs() -> None:
    words = [
        {"word": str(i), "start": i * 0.5, "end": i * 0.5 + 0.4}
        for i in range(10)
    ]
    chunks = chunk_words(words, max_words=99, max_cue_seconds=1.5)
    assert len(chunks) >= 3
    assert all(chunk[-1]["end"] - chunk[0]["start"] <= 2.0 for chunk in chunks)


def test_cue_text_joins_cjk_without_spaces() -> None:
    chunk = [{"word": "大家好"}, {"word": "歡迎"}, {"word": "來到"}]
    assert cue_text(chunk) == "大家好歡迎來到"
