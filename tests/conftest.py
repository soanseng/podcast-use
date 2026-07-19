from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "helpers"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))


@pytest.fixture
def edit_dir(tmp_path: Path) -> Path:
    path = tmp_path / "edit"
    (path / "transcripts").mkdir(parents=True)
    return path


@pytest.fixture
def sample_words() -> list[dict]:
    # Hello(0-0.3) world(0.35-0.7) this(0.75-1.0) is(1.05-1.2) a(1.25-1.4) test(1.45-1.9)
    words = []
    timeline = [
        ("Hello", 0.0, 0.3),
        ("world", 0.35, 0.7),
        ("this", 0.75, 1.0),
        ("is", 1.05, 1.2),
        ("a", 1.25, 1.4),
        ("test", 1.45, 1.9),
    ]
    for token, start, end in timeline:
        words.append({"word": token, "start": start, "end": end})
    return words


@pytest.fixture
def sample_edit(edit_dir: Path, sample_words: list[dict]) -> Path:
    payload = {
        "text": " ".join(w["word"] for w in sample_words),
        "words": sample_words,
        "source": "episode.wav",
        "model": "test",
    }
    (edit_dir / "transcripts" / "episode.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return edit_dir
