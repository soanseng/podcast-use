from __future__ import annotations

import argparse
from pathlib import Path

from generate_image import generate_image_file, load_prompt

__all__ = ["generate_image_file", "main"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an image with Gemini and save it locally")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output image path")
    parser.add_argument("--prompt", default=None, help="Prompt text")
    parser.add_argument("--prompt-file", type=Path, default=None, help="Prompt file")
    parser.add_argument(
        "--model",
        default="gemini-3.1-flash-image-preview",
        help="Primary Gemini image model",
    )
    parser.add_argument(
        "--fallback-model",
        default="gemini-2.5-flash-image",
        help="Fallback Gemini image model",
    )
    parser.add_argument(
        "--image-kind",
        choices=["youtube", "reel"],
        default="youtube",
        help="Image use case",
    )
    parser.add_argument("--width", type=int, default=1280, help="Output width")
    parser.add_argument("--height", type=int, default=720, help="Output height")
    args = parser.parse_args()

    prompt = load_prompt(args.prompt, args.prompt_file)
    model_used = generate_image_file(
        output_path=args.output.resolve(),
        prompt=prompt,
        provider="gemini",
        primary_model=args.model,
        fallback_model=args.fallback_model,
        image_kind=args.image_kind,
        width=args.width,
        height=args.height,
    )
    print(f"generated: {args.output.resolve()} via gemini/{model_used}")


if __name__ == "__main__":
    main()
