from __future__ import annotations

import json
import sys

import pytest

from punctuate_words_local import apply_marks, punctuate_batch


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content
        self.reasoning_content = None


class _Choice:
    def __init__(self, content: str, finish_reason: str | None = None) -> None:
        self.message = _Msg(content)
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, content: str, finish_reason: str | None = None) -> None:
        self.choices = [_Choice(content, finish_reason)]


class _Completions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return _Response(self._content)


class _Client:
    def __init__(self, content: str) -> None:
        completions = _Completions(content)
        self.completions = completions
        self.chat = type("Chat", (), {"completions": completions})()


def _words(tokens: list[str]) -> list[dict]:
    return [
        {"word": token, "start": index * 0.5, "end": index * 0.5 + 0.4}
        for index, token in enumerate(tokens)
    ]


def test_apply_marks_appends_only_valid_marks() -> None:
    words = _words(["好", "棒", "讚", "行"])
    marks = [
        {"i": 0, "p": "，"},
        {"i": 1, "p": "。"},
        {"i": 2, "p": "X"},  # not an allowed mark -> ignored
        {"i": 9, "p": "，"},  # out of range -> ignored
        {"i": "x", "p": "，"},  # bad index -> ignored
    ]
    out = apply_marks(words, marks)
    assert [item["word"] for item in out] == ["好，", "棒。", "讚", "行"]
    assert out[0]["start"] == 0.0 and out[0]["end"] == 0.4


def test_apply_marks_keeps_already_punctuated_tokens() -> None:
    words = _words(["好，", "棒"])
    out = apply_marks(words, [{"i": 0, "p": "。"}, {"i": 1, "p": "！"}])
    assert [item["word"] for item in out] == ["好，", "棒！"]


def test_punctuate_batch_marks_from_model_response() -> None:
    client = _Client('{"punct":[{"i":0,"p":"，"},{"i":2,"p":"。"}]}')
    out = punctuate_batch(
        client, "m", _words(["好", "棒", "讚"]), json_mode=False, disable_thinking=True, max_tokens=512
    )
    assert [item["word"] for item in out] == ["好，", "棒", "讚。"]


def test_punctuate_batch_retries_on_invalid_list() -> None:
    client = _Client('{"punct":[' + ",".join('{"i":0,"p":"，"}' for _ in range(5)) + "]}")
    words = _words(["好", "棒"])
    with pytest.raises(RuntimeError):
        punctuate_batch(client, "m", words, json_mode=False, disable_thinking=True, max_tokens=512)
    assert len(client.completions.calls) == 3


class _ScriptedCompletions:
    """Client that returns scripted payloads (or raises scripted errors) per call."""

    def __init__(self, script: list[object]) -> None:
        self.script = list(script)
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Response(str(item))


class _ScriptedClient:
    def __init__(self, script: list[object]) -> None:
        completions = _ScriptedCompletions(script)
        self.completions = completions
        self.chat = type("Chat", (), {"completions": completions})()


def _patch_local_llm(monkeypatch, client: object) -> None:
    import punctuate_words_local as pwl

    monkeypatch.setattr(pwl.local_llm, "make_refine_client", lambda **kwargs: client)
    monkeypatch.setattr(pwl.local_llm, "refine_model", lambda: "m")
    monkeypatch.setattr(pwl.local_llm, "thinking_toggle_supported", lambda *a, **k: False)
    monkeypatch.setattr(pwl.local_llm, "refine_reasoning", lambda *a, **k: "low")


def test_main_keeps_word_order_with_parallel_batches(monkeypatch, sample_edit) -> None:
    import punctuate_words_local as pwl

    client = _Client('{"punct":[{"i":0,"p":"，"}]}')
    _patch_local_llm(monkeypatch, client)
    transcript = sample_edit / "transcripts" / "episode.json"
    monkeypatch.setattr(
        sys, "argv",
        ["punctuate", str(transcript), "--batch-words", "2", "--concurrency", "3"],
    )
    pwl.main()

    payload = json.loads((sample_edit / "transcripts" / "episode.punct.json").read_text())
    # Each of the 3 batches marks its own first word; order must survive the pool.
    assert [w["word"] for w in payload["words"]] == ["Hello，", "world", "this，", "is", "a，", "test"]
    assert payload["punctuated_by"] == "m"
    assert len(client.completions.calls) == 3
    assert not (sample_edit / "transcripts" / "episode.punct.partial.json").exists()


def test_main_resumes_from_prefix_checkpoint(monkeypatch, sample_edit) -> None:
    import punctuate_words_local as pwl

    transcript = sample_edit / "transcripts" / "episode.json"
    partial = sample_edit / "transcripts" / "episode.punct.partial.json"
    marks = '{"punct":[{"i":0,"p":"，"}]}'
    down = RuntimeError("upstream down")
    failing = _ScriptedClient([marks, marks, down, down, down])
    _patch_local_llm(monkeypatch, failing)
    monkeypatch.setattr(
        sys, "argv", ["punctuate", str(transcript), "--batch-words", "2", "--concurrency", "1"]
    )
    with pytest.raises(RuntimeError):
        pwl.main()

    # The checkpoint must stay a contiguous prefix so a resume cannot duplicate or drop words.
    checkpoint = json.loads(partial.read_text())
    assert [w["word"] for w in checkpoint["words"]] == ["Hello，", "world", "this，", "is"]

    resuming = _Client('{"punct":[{"i":0,"p":"。"}]}')
    _patch_local_llm(monkeypatch, resuming)
    pwl.main()

    payload = json.loads((sample_edit / "transcripts" / "episode.punct.json").read_text())
    assert [w["word"] for w in payload["words"]] == ["Hello，", "world", "this，", "is", "a。", "test"]
    assert resuming.completions.calls[0]["messages"][1]["content"].count('"a"') == 1
    assert not partial.exists()
