from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from edl_io import effective_range, load_segments, resolve_edl_path


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def build_podcast_filter_chain(
    *,
    denoise: bool,
    post_denoise: bool,
    leveler: bool,
    highpass_hz: int,
    lowpass_hz: int,
    equalizer: bool,
    compressor: bool,
    normalize: bool,
    limiter: bool,
) -> list[str]:
    filters: list[str] = []

    if denoise:
        # Conservative broadband denoise for spoken-word recordings.
        filters.append("afftdn=nr=10:nf=-25:tn=1")

    if leveler:
        # Pre-compression speech leveling to approximate a first normalize pass.
        filters.append("speechnorm=e=4.5:r=0.00008:l=1")

    if highpass_hz > 0:
        filters.append(f"highpass=f={highpass_hz}")

    if lowpass_hz > 0:
        filters.append(f"lowpass=f={lowpass_hz}")

    if equalizer:
        # Mild spoken-word EQ: trim sub-bass mud, add presence, tame top-end.
        filters.append(
            "firequalizer="
            "gain_entry='entry(0,-6);entry(70,-5);entry(120,-2);"
            "entry(250,-1.2);entry(3000,1.8);entry(4500,1.4);"
            "entry(7000,0.6);entry(13500,-3.5)'"
        )

    if compressor:
        filters.append("acompressor=threshold=0.089:ratio=3:attack=20:release=250:makeup=2")

    if normalize:
        filters.append("loudnorm=I=-16:LRA=7:TP=-1.5")

    if post_denoise:
        # Light second cleanup pass after dynamics processing.
        filters.append("afftdn=nr=4:nf=-30:tn=1")

    if limiter:
        filters.append("alimiter=limit=0.95:level=disabled")

    return filters


def probe_duration(audio_path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None


def render_segments(
    audio_map: dict[str, Path],
    tmp_dir: Path,
    segments: list[dict],
    *,
    edge_pad: float,
) -> list[Path]:
    rendered: list[Path] = []
    durations: dict[str, float | None] = {}
    for index, segment in enumerate(segments):
        out_path = tmp_dir / f"part_{index:04d}.wav"
        audio_path = audio_map[segment["source"]]
        if segment["source"] not in durations:
            durations[segment["source"]] = probe_duration(audio_path)
        start, end = effective_range(
            segment,
            edge_pad=edge_pad,
            source_duration=durations[segment["source"]],
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-af",
            "afade=t=in:st=0:d=0.03,areverse,afade=t=in:st=0:d=0.03,areverse",
            str(out_path),
        ]
        run(cmd)
        rendered.append(out_path)
    return rendered


def concat_segments(
    parts: list[Path],
    output_path: Path,
    tmp_dir: Path,
    *,
    denoise: bool,
    post_denoise: bool,
    leveler: bool,
    highpass_hz: int,
    lowpass_hz: int,
    equalizer: bool,
    compressor: bool,
    normalize: bool,
    limiter: bool,
) -> None:
    concat_list = tmp_dir / "concat.txt"
    concat_list.write_text("".join(f"file '{path}'\n" for path in parts))
    merged_wav = tmp_dir / "merged.wav"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c:a",
            "pcm_s16le",
            str(merged_wav),
        ]
    )

    ext = output_path.suffix.lower()
    audio_filters = build_podcast_filter_chain(
        denoise=denoise,
        post_denoise=post_denoise,
        leveler=leveler,
        highpass_hz=highpass_hz,
        lowpass_hz=lowpass_hz,
        equalizer=equalizer,
        compressor=compressor,
        normalize=normalize,
        limiter=limiter,
    )
    cmd = ["ffmpeg", "-y", "-i", str(merged_wav)]
    if audio_filters:
        cmd.extend(["-af", ",".join(audio_filters)])
    if ext == ".mp3":
        cmd.extend(["-c:a", "libmp3lame", "-q:a", "2", str(output_path)])
    elif ext == ".wav":
        cmd.extend(["-c:a", "pcm_s16le", str(output_path)])
    else:
        sys.exit(f"unsupported output format: {output_path.suffix}")
    run(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render spoken-word audio from an EDL")
    parser.add_argument("audio", nargs="+", type=Path, help="One or more source audio paths")
    parser.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="Edit directory. Defaults to <first_audio_dir>/edit",
    )
    parser.add_argument(
        "--edl",
        type=Path,
        default=None,
        help="Explicit EDL path. Defaults to edl.approved.json, edl.json, or edl.draft.json",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to <edit_dir>/final.mp3 (or preview.mp3 with --preview)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Fast preview render: skip heavy processing chain",
    )
    parser.add_argument(
        "--edge-pad-ms",
        type=float,
        default=40.0,
        help="Global pad in milliseconds applied around each segment (default: 40)",
    )
    parser.add_argument(
        "--only-segment",
        type=int,
        default=None,
        help="Render only the segment at this 0-based index",
    )
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="Disable final loudnorm pass",
    )
    parser.add_argument(
        "--no-denoise",
        action="store_true",
        help="Disable broadband denoise",
    )
    parser.add_argument(
        "--no-post-denoise",
        action="store_true",
        help="Disable the light cleanup denoise pass after compression and normalization",
    )
    parser.add_argument(
        "--no-leveler",
        action="store_true",
        help="Disable the pre-compression speech leveling stage",
    )
    parser.add_argument(
        "--no-eq",
        action="store_true",
        help="Disable spoken-word equalizer shaping",
    )
    parser.add_argument(
        "--no-compressor",
        action="store_true",
        help="Disable spoken-word compression",
    )
    parser.add_argument(
        "--no-limiter",
        action="store_true",
        help="Disable final true-peak safety limiting",
    )
    parser.add_argument(
        "--highpass-hz",
        type=int,
        default=80,
        help="High-pass filter cutoff for rumble removal",
    )
    parser.add_argument(
        "--lowpass-hz",
        type=int,
        default=13500,
        help="Low-pass filter cutoff for hiss reduction",
    )
    args = parser.parse_args()

    audio_paths = [path.resolve() for path in args.audio]
    missing = [str(path) for path in audio_paths if not path.exists()]
    if missing:
        sys.exit(f"audio not found: {', '.join(missing)}")

    edit_dir = (args.edit_dir or (audio_paths[0].parent / "edit")).resolve()
    if args.output is not None:
        output_path = args.output
    elif args.preview:
        output_path = edit_dir / "preview.mp3"
    else:
        output_path = edit_dir / "final.mp3"
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio_map = {path.stem: path for path in audio_paths}
    edl_path = resolve_edl_path(edit_dir, args.edl)
    _, segments = load_segments(edit_dir, set(audio_map), edl_path=edl_path)

    if args.only_segment is not None:
        if args.only_segment < 0 or args.only_segment >= len(segments):
            sys.exit(f"--only-segment out of range 0..{len(segments) - 1}")
        segments = [segments[args.only_segment]]

    edge_pad = max(0.0, args.edge_pad_ms / 1000.0)

    # Preview skips heavy chain for faster iteration.
    if args.preview:
        denoise = False
        post_denoise = False
        leveler = False
        equalizer = False
        compressor = False
        normalize = False
        limiter = True
        highpass_hz = 0
        lowpass_hz = 0
    else:
        denoise = not args.no_denoise
        post_denoise = not args.no_post_denoise
        leveler = not args.no_leveler
        equalizer = not args.no_eq
        compressor = not args.no_compressor
        normalize = not args.no_normalize
        limiter = not args.no_limiter
        highpass_hz = max(0, args.highpass_hz)
        lowpass_hz = max(0, args.lowpass_hz)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        parts = render_segments(audio_map, tmp_dir, segments, edge_pad=edge_pad)
        concat_segments(
            parts,
            output_path,
            tmp_dir,
            denoise=denoise,
            post_denoise=post_denoise,
            leveler=leveler,
            highpass_hz=highpass_hz,
            lowpass_hz=lowpass_hz,
            equalizer=equalizer,
            compressor=compressor,
            normalize=normalize,
            limiter=limiter,
        )

    print(f"edl: {edl_path}")
    print(f"segments: {len(segments)}")
    print(f"edge_pad_ms: {args.edge_pad_ms}")
    print(f"rendered: {output_path}")


if __name__ == "__main__":
    main()
