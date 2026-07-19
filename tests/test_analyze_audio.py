from __future__ import annotations

from pathlib import Path

from analyze_audio import find_fillers, find_retake_clusters, normalize_token, write_report


def test_normalize_token() -> None:
    assert normalize_token("Um,") == "um"
    assert normalize_token("  嗯。") == "嗯"


def test_find_fillers_zh_en() -> None:
    words = [
        {"word": "嗯", "start": 0.0, "end": 0.2},
        {"word": "Hello", "start": 0.3, "end": 0.6},
        {"word": "um", "start": 0.7, "end": 0.9},
        {"word": "world", "start": 1.0, "end": 1.3},
        {"word": "就是", "start": 1.4, "end": 1.6},
    ]
    hits = find_fillers(words)
    tokens = {h["word"] for h in hits}
    assert "嗯" in tokens
    assert "um" in tokens
    assert "就是" in tokens
    assert "Hello" not in tokens


def test_find_retake_clusters() -> None:
    phrases = [
        {"start": 0.0, "end": 1.0, "text": "I think we should ship this feature now"},
        {"start": 1.2, "end": 2.3, "text": "I think we should ship this feature today"},
        {"start": 10.0, "end": 11.0, "text": "Completely different topic here"},
    ]
    clusters = find_retake_clusters(phrases)
    assert len(clusters) == 1
    assert clusters[0]["count"] == 2


def test_write_report(tmp_path: Path) -> None:
    edit = tmp_path / "edit"
    audio = tmp_path / "episode.wav"
    audio.write_bytes(b"")  # path only; not decoded
    silences = [{"start": 2.0, "end": 4.5, "duration": 2.5}]
    fillers = [{"word": "um", "start": 0.5, "end": 0.7, "lang": "en"}]
    phrases = [{"start": 0.0, "end": 1.0, "text": "hello"}]
    retakes = [
        {
            "count": 2,
            "start": 5.0,
            "end": 8.0,
            "texts": ["take one", "take two"],
        }
    ]
    json_path, md_path = write_report(
        edit_dir=edit,
        audio_path=audio,
        duration=20.0,
        silences=silences,
        fillers=fillers,
        phrases=phrases,
        retakes=retakes,
        min_silence_report=1.0,
    )
    assert json_path.exists()
    assert md_path.exists()
    text = md_path.read_text()
    assert "filler candidates: 1" in text
    assert "Long silences" in text
    assert (edit / "analysis" / "suggestions.md").exists()
