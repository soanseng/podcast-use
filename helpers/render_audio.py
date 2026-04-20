from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def build_podcast_filter_chain(
    *,
    denoise: bool,
    highpass_hz: int,
    lowpass_hz: int,
    compressor: bool,
    normalize: bool,
) -> list[str]:
    filters: list[str] = []

    if denoise:
        # Conservative broadband denoise for spoken-word recordings.
        filters.append("afftdn=nr=10:nf=-25:tn=1")

    if highpass_hz > 0:
        filters.append(f"highpass=f={highpass_hz}")

    if lowpass_hz > 0:
        filters.append(f"lowpass=f={lowpass_hz}")

    if compressor:
        filters.append("acompressor=threshold=0.089:ratio=3:attack=20:release=250:makeup=2")

    if normalize:
        filters.append("loudnorm=I=-16:LRA=7:TP=-1.5")

    return filters


def load_edl(edit_dir: Path, allowed_sources: set[str]) -> list[dict]:
    edl_path = edit_dir / "edl.json"
    if not edl_path.exists():
        sys.exit(f"missing EDL: {edl_path}")

    payload = json.loads(edl_path.read_text())
    if not isinstance(payload, list) or not payload:
        sys.exit("edl.json must be a non-empty JSON array")

    segments: list[dict] = []
    for index, item in enumerate(payload):
        source = item.get("source")
        if source not in allowed_sources:
            continue
        start = float(item["start"])
        end = float(item["end"])
        if end <= start:
            sys.exit(f"invalid segment at index {index}: end must be greater than start")
        segments.append({"source": source, "start": start, "end": end})

    if not segments:
        sys.exit(f"no EDL segments found for sources {sorted(allowed_sources)}")
    return segments


def render_segments(audio_map: dict[str, Path], tmp_dir: Path, segments: list[dict]) -> list[Path]:
    rendered: list[Path] = []
    for index, segment in enumerate(segments):
        out_path = tmp_dir / f"part_{index:04d}.wav"
        audio_path = audio_map[segment["source"]]
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-ss",
            f"{segment['start']:.3f}",
            "-to",
            f"{segment['end']:.3f}",
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
    highpass_hz: int,
    lowpass_hz: int,
    compressor: bool,
    normalize: bool,
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
        highpass_hz=highpass_hz,
        lowpass_hz=lowpass_hz,
        compressor=compressor,
        normalize=normalize,
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
    parser = argparse.ArgumentParser(description="Render spoken-word audio from edl.json")
    parser.add_argument("audio", nargs="+", type=Path, help="One or more source audio paths")
    parser.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="Edit directory. Defaults to <first_audio_dir>/edit",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to <edit_dir>/final.mp3",
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
        "--no-compressor",
        action="store_true",
        help="Disable spoken-word compression",
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
    output_path = args.output or (edit_dir / "final.mp3")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio_map = {path.stem: path for path in audio_paths}
    segments = load_edl(edit_dir, set(audio_map))
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        parts = render_segments(audio_map, tmp_dir, segments)
        concat_segments(
            parts,
            output_path,
            tmp_dir,
            denoise=not args.no_denoise,
            highpass_hz=max(0, args.highpass_hz),
            lowpass_hz=max(0, args.lowpass_hz),
            compressor=not args.no_compressor,
            normalize=not args.no_normalize,
        )

    print(f"rendered: {output_path}")


if __name__ == "__main__":
    main()
