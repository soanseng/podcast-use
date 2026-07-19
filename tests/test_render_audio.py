from __future__ import annotations

from render_audio import build_podcast_filter_chain


def test_filter_chain_full() -> None:
    filters = build_podcast_filter_chain(
        denoise=True,
        post_denoise=True,
        leveler=True,
        highpass_hz=80,
        lowpass_hz=13500,
        equalizer=True,
        compressor=True,
        normalize=True,
        limiter=True,
    )
    joined = ",".join(filters)
    assert "afftdn=" in joined
    assert "speechnorm=" in joined
    assert "highpass=f=80" in joined
    assert "lowpass=f=13500" in joined
    assert "firequalizer=" in joined
    assert "acompressor=" in joined
    assert "loudnorm=" in joined
    assert "alimiter=" in joined
    # denoise appears twice when post_denoise enabled
    assert joined.count("afftdn=") == 2


def test_filter_chain_preview_like() -> None:
    filters = build_podcast_filter_chain(
        denoise=False,
        post_denoise=False,
        leveler=False,
        highpass_hz=0,
        lowpass_hz=0,
        equalizer=False,
        compressor=False,
        normalize=False,
        limiter=True,
    )
    assert filters == ["alimiter=limit=0.95:level=disabled"]


def test_filter_chain_empty() -> None:
    filters = build_podcast_filter_chain(
        denoise=False,
        post_denoise=False,
        leveler=False,
        highpass_hz=0,
        lowpass_hz=0,
        equalizer=False,
        compressor=False,
        normalize=False,
        limiter=False,
    )
    assert filters == []
