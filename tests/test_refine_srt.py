from __future__ import annotations

import pytest

from refine_srt_groq import refine_batch


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
        completions = _Completions(script)
        self.completions = completions
        self.chat = type("Chat", (), {"completions": completions})()


def _cues(count: int = 1) -> list[dict]:
    return [
        {"index": index, "timing": f"00:00:0{index},000 --> 00:00:0{index},900", "text": f"原文 {index}"}
        for index in range(1, count + 1)
    ]


def _payload(count: int = 1, suffix: str = "校正後") -> str:
    items = ",".join(f'{{"index":{i},"text":"{suffix} {i}"}}' for i in range(1, count + 1))
    return "{" + f'"cues":[{items}]' + "}"


def test_refine_batch_preserves_indexes_and_timings() -> None:
    client = _Client([_Response(_payload(2))])
    output = refine_batch(
        client=client,
        model="m",
        fallback_model=None,
        cues=_cues(2),
        language="zh-Hant",
        glossary_terms=[],
        reference_context="",
    )
    assert [item["index"] for item in output] == [1, 2]
    assert output[0]["timing"] == _cues(2)[0]["timing"]
    assert output[0]["text"] == "校正後 1"


def test_refine_batch_local_defaults_disable_thinking_and_json_mode() -> None:
    client = _Client([_Response(_payload(1))])
    refine_batch(
        client=client,
        model="qwen36-genesis",
        fallback_model=None,
        cues=_cues(1),
        language="zh-Hant",
        glossary_terms=[],
        reference_context="",
        json_mode=False,
        disable_thinking=True,
        max_tokens=4096,
    )
    call = client.completions.calls[0]
    assert "response_format" not in call
    assert "chat_template_kwargs" not in call
    assert call["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert call["max_tokens"] == 4096


def test_refine_batch_drops_thinking_toggle_when_provider_rejects_it() -> None:
    client = _Client(
        [
            TypeError("Completions.create() got an unexpected keyword argument 'chat_template_kwargs'"),
            _Response(_payload(1)),
        ]
    )
    output = refine_batch(
        client=client,
        model="m",
        fallback_model=None,
        cues=_cues(1),
        language="zh-Hant",
        glossary_terms=[],
        reference_context="",
        json_mode=False,
        disable_thinking=True,
    )
    assert output[0]["text"] == "校正後 1"
    assert len(client.completions.calls) == 2
    assert "extra_body" not in client.completions.calls[1]


def test_refine_batch_retries_without_json_mode_on_rejection() -> None:
    client = _Client(
        [
            ValueError("response_format is not supported"),
            _Response(_payload(1)),
        ]
    )
    refine_batch(
        client=client,
        model="m",
        fallback_model=None,
        cues=_cues(1),
        language="zh-Hant",
        glossary_terms=[],
        reference_context="",
    )
    assert client.completions.calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in client.completions.calls[1]


def test_refine_batch_retries_on_empty_completion() -> None:
    client = _Client([_Response(""), _Response(_payload(1))])
    output = refine_batch(
        client=client,
        model="m",
        fallback_model=None,
        cues=_cues(1),
        language="zh-Hant",
        glossary_terms=[],
        reference_context="",
    )
    assert output[0]["text"] == "校正後 1"
    retry = client.completions.calls[1]
    assert "response_format" not in retry
    assert retry["max_tokens"] >= 4096


def test_refine_batch_rejects_cue_count_change() -> None:
    client = _Client([_Response(_payload(2))])
    with pytest.raises(RuntimeError):
        refine_batch(
            client=client,
            model="m",
            fallback_model=None,
            cues=_cues(1),
            language="zh-Hant",
            glossary_terms=[],
            reference_context="",
        )


def test_chat_json_retries_on_truncated_completion() -> None:
    from refine_srt_groq import chat_json

    client = _Client(
        [
            _Response('{"cues":[{"index":1,"text":"半截', finish_reason="length"),
            _Response('{"cues":[{"index":1,"text":"完整的"}]}'),
        ]
    )
    payload = chat_json(
        client,
        "qwen36-genesis",
        [{"role": "user", "content": "x"}],
        json_mode=False,
        disable_thinking=True,
        max_tokens=4096,
    )
    assert payload["cues"][0]["text"] == "完整的"
    retry = client.completions.calls[1]
    assert retry["max_tokens"] >= 8192


def test_chat_json_retries_on_unparsable_json() -> None:
    from refine_srt_groq import chat_json

    client = _Client(
        [
            _Response('{"cues":[{"index":1,"text":"缺右括號'),
            _Response('{"cues":[{"index":1,"text":"第二次好"}]}'),
        ]
    )
    payload = chat_json(
        client,
        "m",
        [{"role": "user", "content": "x"}],
        json_mode=False,
        max_tokens=1000,
    )
    assert payload["cues"][0]["text"] == "第二次好"
    assert client.completions.calls[1]["max_tokens"] >= 4000


def test_chat_json_sends_and_drops_reasoning_effort() -> None:
    from refine_srt_groq import chat_json

    client = _Client(
        [
            _Response('{"ok":true}'),
        ]
    )
    payload = chat_json(
        client,
        "deepseek-v4.1",
        [{"role": "user", "content": "x"}],
        json_mode=False,
        reasoning_effort="none",
    )
    assert payload == {"ok": True}
    assert client.completions.calls[0]["reasoning_effort"] == "none"


def test_chat_json_drops_reasoning_on_rejection() -> None:
    from refine_srt_groq import chat_json

    client = _Client(
        [
            ValueError("Unsupported parameter: reasoning_effort"),
            _Response('{"ok":true}'),
        ]
    )
    payload = chat_json(
        client,
        "m",
        [{"role": "user", "content": "x"}],
        json_mode=False,
        reasoning_effort="low",
    )
    assert payload == {"ok": True}
    assert "reasoning_effort" not in client.completions.calls[1]
