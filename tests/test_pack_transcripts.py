from __future__ import annotations

import json
from pathlib import Path

from pack_transcripts import group_words, phrase_stats, render_markdown


def test_group_words_splits_on_silence() -> None:
    words = [
        {"word": "Hello", "start": 0.0, "end": 0.3},
        {"word": "there", "start": 0.35, "end": 0.6},
        {"word": "again", "start": 1.5, "end": 1.9},
    ]
    phrases = group_words(words, silence_threshold=0.5)
    assert len(phrases) == 2
    assert phrases[0]["text"] == "Hello there"
    assert phrases[1]["text"] == "again"


def test_group_words_cleans_punctuation_spacing() -> None:
    words = [
        {"word": "Wow", "start": 0.0, "end": 0.2},
        {"word": "!", "start": 0.2, "end": 0.25},
        {"word": "Okay", "start": 0.3, "end": 0.5},
        {"word": ".", "start": 0.5, "end": 0.55},
    ]
    phrases = group_words(words, silence_threshold=0.5)
    assert len(phrases) == 1
    assert phrases[0]["text"] == "Wow! Okay."


def test_phrase_stats_and_markdown(sample_words: list[dict]) -> None:
    # insert a longer gap between world and this
    words = list(sample_words)
    words[2] = {"word": "this", "start": 2.0, "end": 2.3}
    words[3] = {"word": "is", "start": 2.35, "end": 2.5}
    words[4] = {"word": "a", "start": 2.55, "end": 2.7}
    words[5] = {"word": "test", "start": 2.75, "end": 3.1}

    phrases = group_words(words, silence_threshold=0.5)
    stats = phrase_stats(phrases)
    assert stats["phrase_count"] == 2
    assert stats["longest_gap"] > 1.0
    assert stats["longest_gap_at"] is not None

    md = render_markdown([("episode", 3.1, phrases)], 0.5)
    assert "## Quick stats" in md
    assert "**episode**" in md
    assert "[000.00-" in md


def test_pack_cli(tmp_path: Path, sample_words: list[dict]) -> None:
    import subprocess
    import sys

    edit = tmp_path / "edit"
    (edit / "transcripts").mkdir(parents=True)
    (edit / "transcripts" / "episode.json").write_text(
        json.dumps({"words": sample_words, "text": "Hello world this is a test"})
    )
    helper = Path(__file__).resolve().parents[1] / "helpers" / "pack_transcripts.py"
    result = subprocess.run(
        [sys.executable, str(helper), "--edit-dir", str(edit)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "packed" in result.stdout
    out = (edit / "takes_packed.md").read_text()
    assert "Quick stats" in out
