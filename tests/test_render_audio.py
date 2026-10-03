from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from edl_io import normalize_segment
from render_audio import (
    build_atempo,
    build_podcast_filter_chain,
    probe_duration,
    render_segments,
    segment_filter_chain,
)


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


def test_build_atempo_splits_out_of_range_speeds() -> None:
    assert build_atempo(1.0) == []
    assert build_atempo(1.5) == ["atempo=1.500000"]
    # 0.25x is outside a single-stage atempo range, so it chains two stages
    stages = build_atempo(0.25)
    assert stages == ["atempo=0.5", "atempo=0.500000"]
    assert build_atempo(4.0) == ["atempo=2.0", "atempo=2.000000"]


def test_segment_filter_chain_ops() -> None:
    chain = segment_filter_chain(
        {"speed": 2.0, "gain_db": -6.0, "fade_in": 0.25, "fade_out": 0.5},
        output_duration=1.0,
    )
    assert "atempo=2.000000" in chain
    assert "volume=-6.0dB" in chain
    assert "afade=t=in:st=0:d=0.250" in chain
    # fade-out is anchored to the end of the sped segment
    assert "afade=t=out:st=0.500:d=0.500" in chain


def _make_tone(path: Path, seconds: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _max_volume_db(path: Path) -> float:
    result = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    for line in result.stderr.splitlines():
        if "max_volume:" in line:
            return float(line.split("max_volume:")[1].split("dB")[0])
    raise AssertionError("volumedetect reported no max_volume")


def test_render_segments_tempo_silence_and_ops(tmp_path: Path) -> None:
    source = tmp_path / "episode.wav"
    _make_tone(source, seconds=4.0)
    segments = [
        normalize_segment({"source": "episode", "start": 0.0, "end": 2.0, "speed": 2.0, "gain_db": -20.0}, 0),
        normalize_segment({"silence": 0.5}, 1),
        normalize_segment({"source": "episode", "start": 3.0, "end": 4.0, "fade_in": 0.2, "fade_out": 0.2}, 2),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        parts = render_segments(
            {"episode": source},
            Path(tmp),
            segments,
            edge_pad=0.0,
            sample_rate=44100,
            channels=1,
        )
        durations = [probe_duration(part) for part in parts]

    assert durations[0] == pytest.approx(1.0, abs=0.05)  # 2s source at 2x tempo
    assert durations[1] == pytest.approx(0.5, abs=0.05)  # inserted silence
    assert durations[2] == pytest.approx(1.0, abs=0.05)
    assert sum(d or 0.0 for d in durations) == pytest.approx(2.5, abs=0.1)


def test_render_segments_gain_reduces_level(tmp_path: Path) -> None:
    source = tmp_path / "episode.wav"
    _make_tone(source, seconds=2.0)
    with tempfile.TemporaryDirectory() as tmp:
        loud = render_segments(
            {"episode": source},
            Path(tmp),
            [normalize_segment({"source": "episode", "start": 0.0, "end": 1.0}, 0)],
            edge_pad=0.0,
            sample_rate=44100,
            channels=1,
        )[0]
        loud_db = _max_volume_db(loud)
    with tempfile.TemporaryDirectory() as tmp:
        quiet = render_segments(
            {"episode": source},
            Path(tmp),
            [normalize_segment({"source": "episode", "start": 0.0, "end": 1.0, "gain_db": -20.0}, 0)],
            edge_pad=0.0,
            sample_rate=44100,
            channels=1,
        )[0]
        quiet_db = _max_volume_db(quiet)

    assert quiet_db == pytest.approx(loud_db - 20.0, abs=0.6)
