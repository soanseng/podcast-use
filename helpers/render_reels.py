from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from build_subtitles import chunk_words, format_srt_timestamp, load_words
from generate_image import generate_image_file


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def words_for_range(words: list[dict], start: float, end: float) -> list[dict]:
    kept: list[dict] = []
    for word in words:
        token = (word.get("word") or "").strip()
        word_start = word.get("start")
        word_end = word.get("end")
        if not token or word_start is None or word_end is None:
            continue
        if float(word_start) >= start and float(word_end) <= end:
            kept.append({"word": token, "start": float(word_start), "end": float(word_end)})
    return kept


def build_clip_cues(words: list[dict], clip_start: float, max_words: int) -> list[dict]:
    cues: list[dict] = []
    for chunk in chunk_words(words, max_words=max_words):
        if not chunk:
            continue
        start = chunk[0]["start"] - clip_start
        end = chunk[-1]["end"] - clip_start
        text = " ".join(item["word"] for item in chunk)
        text = text.replace(" ,", ",").replace(" .", ".").replace(" ?", "?").replace(" !", "!")
        cues.append({"start": start, "end": max(start + 0.2, end), "text": text})
    return cues


def write_srt(cues: list[dict], output_path: Path) -> None:
    lines: list[str] = []
    for index, cue in enumerate(cues, start=1):
        lines.append(str(index))
        lines.append(
            f"{format_srt_timestamp(cue['start'])} --> {format_srt_timestamp(cue['end'])}"
        )
        lines.append(cue["text"])
        lines.append("")
    output_path.write_text("\n".join(lines))


def extract_audio_clip(source_audio: Path, start: float, end: float, output_path: Path) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source_audio),
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_path),
        ]
    )


def ffmpeg_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(",", "\\,")
    )


def render_reel_video(
    *,
    image_path: Path,
    audio_path: Path,
    srt_path: Path,
    output_path: Path,
    title: str,
    intro: str,
    preset: str,
    fps: int,
) -> None:
    filter_parts = [
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        "drawbox=x=0:y=0:w=iw:h=260:color=black@0.30:t=fill",
    ]
    if intro.strip():
        filter_parts.append(
            f"drawtext=text='{ffmpeg_escape(intro)}':x=60:y=70:fontsize=52:fontcolor=white"
        )
    if title.strip():
        filter_parts.append(
            f"drawtext=text='{ffmpeg_escape(title)}':x=60:y=140:fontsize=78:fontcolor=white"
        )
    filter_parts.append(
        "subtitles="
        + ffmpeg_escape(str(srt_path))
        + ":force_style='FontName=Arial,FontSize=26,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=140'"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(max(1, fps)),
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-vf",
            ",".join(filter_parts),
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-tune",
            "stillimage",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            str(output_path),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render vertical podcast reels from a reels plan")
    parser.add_argument("audio", nargs="+", type=Path, help="Source audio files")
    parser.add_argument("--edit-dir", type=Path, required=True, help="Edit directory")
    parser.add_argument(
        "--plan",
        type=Path,
        default=None,
        help="Defaults to <edit_dir>/reels_plan.json",
    )
    parser.add_argument(
        "--generate-images",
        action="store_true",
        help="Generate missing reel images with the configured provider",
    )
    parser.add_argument(
        "--image-provider",
        choices=["gemini", "openai"],
        default="openai",
        help="Image provider for generated reel art",
    )
    parser.add_argument(
        "--image-model",
        default="gpt-image-2",
        help="Primary image model",
    )
    parser.add_argument(
        "--fallback-image-model",
        default="",
        help="Fallback image model. Defaults to Gemini fallback only when provider=gemini.",
    )
    parser.add_argument("--max-words", type=int, default=6, help="Max words per subtitle cue")
    parser.add_argument(
        "--preset",
        default="veryfast",
        help="ffmpeg x264 preset for reel rendering",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=1,
        help="Output frame rate for static-image reels. Defaults to 1 fps",
    )
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    plan_path = (args.plan or (edit_dir / "reels_plan.json")).resolve()
    if not plan_path.exists():
        sys.exit(f"missing reels plan: {plan_path}")

    audio_map = {path.resolve().stem: path.resolve() for path in args.audio}
    payload = json.loads(plan_path.read_text())
    reels = payload.get("reels", [])
    if not reels:
        sys.exit("reels plan is empty")

    reels_dir = edit_dir / "reels"
    reels_dir.mkdir(parents=True, exist_ok=True)
    image_model = (
        "gemini-3.1-flash-image-preview"
        if args.image_provider == "gemini" and args.image_model == "gpt-image-2"
        else args.image_model
    )
    fallback_image_model = (
        "gemini-2.5-flash-image"
        if args.image_provider == "gemini" and not args.fallback_image_model.strip()
        else args.fallback_image_model.strip() or None
    )

    for reel in reels:
        reel_id = reel["id"]
        source = reel["source"]
        if source not in audio_map:
            sys.exit(f"missing source audio for reel {reel_id}: {source}")
        start = float(reel["start"])
        end = float(reel["end"])
        if end <= start:
            sys.exit(f"invalid range for reel {reel_id}")
        duration = end - start
        if duration < 30 or duration > 60:
            print(f"warning: reel {reel_id} duration is {duration:.1f}s; recommended 30-60s")

        source_audio = audio_map[source]
        words = load_words(edit_dir, source)
        clip_words = words_for_range(words, start, end)
        if not clip_words:
            sys.exit(f"no transcript words found for reel {reel_id}")

        reel_audio = reels_dir / f"{reel_id}.m4a"
        reel_srt = reels_dir / f"{reel_id}.srt"
        reel_image = reels_dir / f"{reel_id}.png"
        reel_output = reels_dir / f"{reel_id}.mp4"

        extract_audio_clip(source_audio, start, end, reel_audio)
        cues = build_clip_cues(clip_words, clip_start=start, max_words=max(1, args.max_words))
        write_srt(cues, reel_srt)

        if args.generate_images and not reel_image.exists():
            prompt = reel.get("image_prompt", "").strip()
            if not prompt:
                sys.exit(f"missing image_prompt for reel {reel_id}")
            model_used = generate_image_file(
                output_path=reel_image,
                prompt=prompt,
                provider=args.image_provider,
                primary_model=image_model,
                fallback_model=fallback_image_model,
                image_kind="reel",
                width=1080,
                height=1920,
            )
            print(f"generated reel image {reel_image} via {args.image_provider}/{model_used}")
        elif not reel_image.exists():
            sys.exit(f"missing reel image: {reel_image}. Use --generate-images or create it manually.")

        render_reel_video(
            image_path=reel_image,
            audio_path=reel_audio,
            srt_path=reel_srt,
            output_path=reel_output,
            title=reel.get("title", "").strip(),
            intro=reel.get("intro", "").strip(),
            preset=args.preset,
            fps=args.fps,
        )
        print(f"rendered reel: {reel_output}")


if __name__ == "__main__":
    main()
