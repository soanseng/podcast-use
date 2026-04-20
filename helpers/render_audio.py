from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def load_edl(edit_dir: Path, source_stem: str) -> list[dict]:
    edl_path = edit_dir / "edl.json"
    if not edl_path.exists():
        sys.exit(f"missing EDL: {edl_path}")

    payload = json.loads(edl_path.read_text())
    if not isinstance(payload, list) or not payload:
        sys.exit("edl.json must be a non-empty JSON array")

    segments: list[dict] = []
    for index, item in enumerate(payload):
        if item.get("source") != source_stem:
            continue
        start = float(item["start"])
        end = float(item["end"])
        if end <= start:
            sys.exit(f"invalid segment at index {index}: end must be greater than start")
        segments.append({"start": start, "end": end})

    if not segments:
        sys.exit(f"no EDL segments found for source '{source_stem}'")
    return segments


def render_segments(audio_path: Path, tmp_dir: Path, segments: list[dict]) -> list[Path]:
    rendered: list[Path] = []
    for index, segment in enumerate(segments):
        out_path = tmp_dir / f"part_{index:04d}.wav"
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


def concat_segments(parts: list[Path], output_path: Path, tmp_dir: Path, normalize: bool) -> None:
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
    audio_filters = ["loudnorm"] if normalize else []
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
    parser.add_argument("audio", type=Path, help="Path to source audio")
    parser.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="Edit directory. Defaults to <audio_dir>/edit",
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
    args = parser.parse_args()

    audio_path = args.audio.resolve()
    if not audio_path.exists():
        sys.exit(f"audio not found: {audio_path}")

    edit_dir = (args.edit_dir or (audio_path.parent / "edit")).resolve()
    output_path = args.output or (edit_dir / "final.mp3")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    segments = load_edl(edit_dir, audio_path.stem)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        parts = render_segments(audio_path, tmp_dir, segments)
        concat_segments(parts, output_path, tmp_dir, normalize=not args.no_normalize)

    print(f"rendered: {output_path}")


if __name__ == "__main__":
    main()
