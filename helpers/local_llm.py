"""Shared config for the local LiteLLM endpoint (Taigi ASR + text refinement).

Settings resolve from process env first, then the skill `.env` (local-only,
gitignored). Never commit real keys.

Env keys:
  LITELLM_BASE_URL       proxy endpoint, default http://100.102.183.27:4000/v1
  LITELLM_MASTER_KEY     proxy master key (required)
  PODCAST_ASR_MODEL      default breeze-asr-26-taigi
  PODCAST_REFINE_MODEL   default qwen36-genesis
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from openai import OpenAI

DEFAULT_BASE_URL = "http://100.102.183.27:4000/v1"
DEFAULT_ASR_MODEL = "breeze-asr-26-taigi"
DEFAULT_REFINE_MODEL = "qwen36-genesis"


@lru_cache(maxsize=1)
def load_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if not candidate.exists():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def get_setting(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key, "").strip()
    if value:
        return value
    value = load_env_file().get(key, "").strip()
    return value or default


def require_master_key() -> str:
    key = get_setting("LITELLM_MASTER_KEY")
    if not key:
        sys.exit(
            "LITELLM_MASTER_KEY not set. Add it to the skill .env (gitignored):\n"
            "  LITELLM_MASTER_KEY=<proxy master key>"
        )
    return key


def base_url() -> str:
    url = (get_setting("LITELLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


def asr_model() -> str:
    return get_setting("PODCAST_ASR_MODEL") or DEFAULT_ASR_MODEL


def refine_model() -> str:
    return get_setting("PODCAST_REFINE_MODEL") or DEFAULT_REFINE_MODEL


def refine_base_url(base_url_override: str | None = None) -> str:
    url = (
        base_url_override
        or get_setting("PODCAST_REFINE_BASE_URL")
        or get_setting("LITELLM_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")
    # Tolerate full endpoint URLs pasted as the base, e.g. .../v1/chat/completions
    for suffix in ("/chat/completions", "/completions", "/chat"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


def refine_api_key() -> str:
    key = get_setting("PODCAST_REFINE_API_KEY") or get_setting("LITELLM_MASTER_KEY")
    if not key:
        sys.exit(
            "No refine API key. Set PODCAST_REFINE_API_KEY (any OpenAI-compatible provider)\n"
            "or LITELLM_MASTER_KEY (local proxy) in the skill .env (gitignored)."
        )
    return key


def thinking_toggle_supported(base_url_override: str | None = None) -> bool:
    """The llama.cpp enable_thinking toggle only exists on local llama-server endpoints."""
    url = refine_base_url(base_url_override).lower()
    return any(host in url for host in ("100.102.183.27", "llama-server", "localhost", "127.0.0.1"))


def refine_reasoning(base_url_override: str | None = None) -> str | None:
    """Reasoning effort for cloud refine models (none by default: JSON tasks do not need it).

    Local llama-server endpoints use the enable_thinking toggle instead and get None.
    """
    setting = get_setting("PODCAST_REFINE_REASONING")
    if setting:
        return setting
    if thinking_toggle_supported(base_url_override):
        return None
    return "none"


def make_client(*, timeout: float = 1800.0, base_url_override: str | None = None) -> OpenAI:
    url = base_url_override.rstrip("/") if base_url_override else base_url()
    if url and not url.endswith("/v1"):
        url = f"{url}/v1"
    return OpenAI(
        api_key=require_master_key(),
        base_url=url,
        timeout=timeout,
        max_retries=2,
    )


def make_refine_client(*, timeout: float = 600.0, base_url_override: str | None = None) -> OpenAI:
    """Client for the refinement model: any OpenAI-compatible endpoint, local or cloud."""
    return OpenAI(
        api_key=refine_api_key(),
        base_url=refine_base_url(base_url_override),
        timeout=timeout,
        max_retries=2,
    )
