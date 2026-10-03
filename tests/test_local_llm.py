from __future__ import annotations

import pytest

import local_llm


def test_refine_base_url_appends_v1(monkeypatch) -> None:
    monkeypatch.setenv("PODCAST_REFINE_BASE_URL", "https://api.example.com/openai")
    assert local_llm.refine_base_url() == "https://api.example.com/openai/v1"

@pytest.fixture(autouse=True)
def _no_env_file(monkeypatch) -> None:
    """Keep the developer's real .env out of these resolution tests."""
    monkeypatch.setattr(local_llm, "load_env_file", lambda: {})


def test_refine_base_url_falls_back_to_litellm(monkeypatch) -> None:
    monkeypatch.delenv("PODCAST_REFINE_BASE_URL", raising=False)
    monkeypatch.setenv("LITELLM_BASE_URL", "http://100.102.183.27:4000")
    assert local_llm.refine_base_url() == "http://100.102.183.27:4000/v1"


def test_refine_api_key_prefers_provider_key(monkeypatch) -> None:
    monkeypatch.setenv("PODCAST_REFINE_API_KEY", "sk-cloud")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-local")
    assert local_llm.refine_api_key() == "sk-cloud"


def test_thinking_toggle_only_for_local_endpoints(monkeypatch) -> None:
    monkeypatch.delenv("PODCAST_REFINE_BASE_URL", raising=False)
    monkeypatch.setenv("LITELLM_BASE_URL", "http://100.102.183.27:4000/v1")
    assert local_llm.thinking_toggle_supported() is True
    monkeypatch.setenv("LITELLM_BASE_URL", "https://api.groq.com/openai/v1")
    assert local_llm.thinking_toggle_supported() is False



def test_refine_reasoning_none_for_cloud(monkeypatch) -> None:
    monkeypatch.delenv("PODCAST_REFINE_REASONING", raising=False)
    monkeypatch.delenv("PODCAST_REFINE_BASE_URL", raising=False)
    monkeypatch.setenv("LITELLM_BASE_URL", "https://api.groq.com/openai/v1")
    assert local_llm.refine_reasoning() == "none"


def test_refine_reasoning_env_override(monkeypatch) -> None:
    monkeypatch.setenv("PODCAST_REFINE_REASONING", "low")
    assert local_llm.refine_reasoning() == "low"


def test_refine_reasoning_skips_toggle_for_local(monkeypatch) -> None:
    monkeypatch.delenv("PODCAST_REFINE_REASONING", raising=False)
    monkeypatch.setenv("LITELLM_BASE_URL", "http://100.102.183.27:4000/v1")
    assert local_llm.refine_reasoning() is None


def test_refine_base_url_strips_full_endpoint_suffix(monkeypatch) -> None:
    monkeypatch.setenv(
        "PODCAST_REFINE_BASE_URL",
        "https://api.commandcode.ai/provider/v1/chat/completions",
    )
    assert local_llm.refine_base_url() == "https://api.commandcode.ai/provider/v1"