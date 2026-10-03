from __future__ import annotations

from pathlib import Path

from transcribe_local import extract_words, transcribe


class _Transcriptions:
    def __init__(self, script: list[object]) -> None:
        self.script = list(script)
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _Client:
    def __init__(self, script: list[object]) -> None:
        transcriptions = _Transcriptions(script)
        self.transcriptions = transcriptions
        self.audio = type("Audio", (), {"transcriptions": transcriptions})()


class _Payload:
    def __init__(self, data: dict) -> None:
        self._data = data

    def model_dump(self) -> dict:
        return self._data


def _audio(tmp_path: Path) -> Path:
    path = tmp_path / "clip.wav"
    path.write_bytes(b"RIFF....WAVEfmt ")
    return path


def test_transcribe_requests_word_granularities(tmp_path: Path) -> None:
    payload = {"text": "hi", "segments": [], "words": [{"word": "hi", "start": 0.0, "end": 0.2}]}
    client = _Client([_Payload(payload)])
    result = transcribe(client, _audio(tmp_path), model="breeze-asr-26-taigi", language=None, prompt=None)
    call = client.transcriptions.calls[0]
    assert call["response_format"] == "verbose_json"
    assert call["timestamp_granularities"] == ["word", "segment"]
    assert result["words"][0]["word"] == "hi"


def test_transcribe_downgrades_when_granularities_rejected(tmp_path: Path) -> None:
    client = _Client(
        [
            ValueError("Unsupported parameter: timestamp_granularities"),
            _Payload({"text": "hi", "words": [{"word": "hi", "start": 0.0, "end": 0.1}]}),
        ]
    )
    result = transcribe(client, _audio(tmp_path), model="m", language=None, prompt=None)
    assert len(client.transcriptions.calls) == 2
    assert "timestamp_granularities" not in client.transcriptions.calls[1]
    assert client.transcriptions.calls[1]["response_format"] == "verbose_json"
    assert result["words"]


def test_transcribe_downgrades_to_plain_json(tmp_path: Path) -> None:
    client = _Client(
        [
            ValueError("Unsupported parameter: timestamp_granularities"),
            ValueError("Unsupported response_format: verbose_json"),
            _Payload({"text": "hi"}),
        ]
    )
    result = transcribe(client, _audio(tmp_path), model="m", language=None, prompt=None)
    assert len(client.transcriptions.calls) == 3
    assert client.transcriptions.calls[2]["response_format"] == "json"
    assert result["words"] == []


def test_extract_words_falls_back_to_segment_words() -> None:
    payload = {
        "text": "a b",
        "segments": [{"words": [{"word": "a", "start": 0.0, "end": 0.1}]}, {"words": None}],
    }
    assert extract_words(payload) == [{"word": "a", "start": 0.0, "end": 0.1}]


def test_extract_words_ignores_incomplete_entries() -> None:
    payload = {"words": [{"word": "", "start": 0.0, "end": 0.1}, {"word": "x", "start": None, "end": 1}]}
    assert extract_words(payload) == []
