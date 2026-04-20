from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a static-image YouTube video from final audio")
    parser.add_argument("audio", type=Path, help="Original source audio path")
    parser.add_argument("--edit-dir", type=Path, default=None, help="Defaults to <audio_dir>/edit")
    parser.add_argument("--image", type=Path, required=True, help="Cover image path")
    parser.add_argument(
        "--audio-input",
        type=Path,
        default=None,
        help="Defaults to <edit_dir>/final.mp3",
    )
    parser.add_argument(
        "--subtitles",
        type=Path,
        default=None,
        help="Defaults to <edit_dir>/final.srt",
    )
    parser.add_argument(
        "--burn-subtitles",
        action="store_true",
        help="Burn subtitles into the output video",
    )
    parser.add_argument("-o", "--output", type=Path, default=None, help="Defaults to <edit_dir>/final.mp4")
    args = parser.parse_args()

    audio_path = args.audio.resolve()
    if not audio_path.exists():
        sys.exit(f"audio not found: {audio_path}")
    image_path = args.image.resolve()
    if not image_path.exists():
        sys.exit(f"image not found: {image_path}")

    edit_dir = (args.edit_dir or (audio_path.parent / "edit")).resolve()
    audio_input = (args.audio_input or (edit_dir / "final.mp3")).resolve()
    subtitles_path = (args.subtitles or (edit_dir / "final.srt")).resolve()
    output_path = args.output or (edit_dir / "final.mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not audio_input.exists():
        sys.exit(f"rendered audio not found: {audio_input}")

    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-i",
        str(audio_input),
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-pix_fmt",
        "yuv420p",
        "-shortest",
    ]

    if args.burn_subtitles:
        if not subtitles_path.exists():
            sys.exit(f"subtitle file not found: {subtitles_path}")
        subtitle_filter = f"subtitles={subtitles_path}:force_style='FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=40'"
        cmd.extend(["-vf", subtitle_filter])

    cmd.append(str(output_path))
    run(cmd)
    print(f"rendered video: {output_path}")


if __name__ == "__main__":
    main()
