from __future__ import annotations

import argparse
import os
import sys
from io import BytesIO
from pathlib import Path

from google import genai
from PIL import Image


def load_env_value(name: str) -> str:
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == name:
                    return value.strip().strip('"').strip("'")
    return os.environ.get(name, "").strip()


def load_gemini_api_key() -> str:
    for name in ["GEMINI_API_KEY", "GOOGLE_API_KEY"]:
        value = load_env_value(name)
        if value:
            return value
    sys.exit("GEMINI_API_KEY or GOOGLE_API_KEY not found in .env or environment")


def load_prompt(prompt: str | None, prompt_file: Path | None) -> str:
    if prompt_file:
        return prompt_file.read_text().strip()
    if prompt:
        return prompt.strip()
    sys.exit("provide --prompt or --prompt-file")


def build_image_prompt(prompt: str, image_kind: str, aspect_hint: str | None) -> str:
    parts = [prompt.strip()]
    if image_kind == "youtube":
        parts.append("Create a compelling YouTube cover image for a podcast episode.")
        parts.append("Prioritize strong focal point, clean composition, high contrast, and thumbnail legibility.")
    elif image_kind == "reel":
        parts.append("Create an attention-grabbing vertical podcast reel visual.")
        parts.append("Prioritize bold subject framing, immediate emotional hook, and mobile-first readability.")
    if aspect_hint:
        parts.append(f"Compose for aspect ratio {aspect_hint}.")
    return " ".join(parts)


def try_generate_image(client: genai.Client, model: str, prompt: str) -> Image.Image:
    response = client.models.generate_content(model=model, contents=[prompt])
    for part in response.parts:
        if getattr(part, "inline_data", None) is not None:
            return Image.open(BytesIO(part.inline_data.data))
    raise RuntimeError(f"model {model} did not return an image")


def fit_image(image: Image.Image, width: int, height: int) -> Image.Image:
    target_ratio = width / height
    image = image.convert("RGB")
    src_ratio = image.width / image.height
    if src_ratio > target_ratio:
        new_width = int(image.height * target_ratio)
        left = (image.width - new_width) // 2
        image = image.crop((left, 0, left + new_width, image.height))
    else:
        new_height = int(image.width / target_ratio)
        top = (image.height - new_height) // 2
        image = image.crop((0, top, image.width, top + new_height))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def generate_image_file(
    *,
    output_path: Path,
    prompt: str,
    primary_model: str,
    fallback_model: str | None,
    image_kind: str,
    width: int,
    height: int,
) -> str:
    client = genai.Client(api_key=load_gemini_api_key())
    built_prompt = build_image_prompt(prompt, image_kind=image_kind, aspect_hint=f"{width}:{height}")
    models = [primary_model]
    if fallback_model and fallback_model != primary_model:
        models.append(fallback_model)

    last_error: Exception | None = None
    for model in models:
        try:
            image = try_generate_image(client, model, built_prompt)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fit_image(image, width, height).save(output_path)
            return model
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    raise RuntimeError(f"image generation failed for models {models}: {last_error}")


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
        primary_model=args.model,
        fallback_model=args.fallback_model,
        image_kind=args.image_kind,
        width=args.width,
        height=args.height,
    )
    print(f"generated: {args.output.resolve()} via {model_used}")


if __name__ == "__main__":
    main()
