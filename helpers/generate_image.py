from __future__ import annotations

import argparse
import base64
import os
import sys
from io import BytesIO
from pathlib import Path

from google import genai
from openai import OpenAI
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


def load_api_key(provider: str) -> str:
    if provider == "gemini":
        for name in ["GEMINI_API_KEY", "GOOGLE_API_KEY"]:
            value = load_env_value(name)
            if value:
                return value
        sys.exit("GEMINI_API_KEY or GOOGLE_API_KEY not found in .env or environment")

    if provider == "openai":
        value = load_env_value("OPENAI_API_KEY")
        if value:
            return value
        sys.exit("OPENAI_API_KEY not found in .env or environment")

    raise ValueError(f"unsupported provider: {provider}")


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


def try_generate_image_gemini(api_key: str, model: str, prompt: str) -> Image.Image:
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=[prompt])
    for part in response.parts:
        if getattr(part, "inline_data", None) is not None:
            return Image.open(BytesIO(part.inline_data.data))
    raise RuntimeError(f"model {model} did not return an image")


def try_generate_image_openai(api_key: str, model: str, prompt: str) -> Image.Image:
    client = OpenAI(api_key=api_key)
    response = client.images.generate(model=model, prompt=prompt)
    image_data = getattr(response, "data", None) or []
    if not image_data:
        raise RuntimeError(f"model {model} did not return any image data")
    b64_json = getattr(image_data[0], "b64_json", None)
    if not b64_json:
        raise RuntimeError(f"model {model} did not return base64 image data")
    return Image.open(BytesIO(base64.b64decode(b64_json)))


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
    provider: str,
    primary_model: str,
    fallback_model: str | None,
    image_kind: str,
    width: int,
    height: int,
) -> str:
    api_key = load_api_key(provider)
    built_prompt = build_image_prompt(prompt, image_kind=image_kind, aspect_hint=f"{width}:{height}")
    models = [primary_model]
    if fallback_model and fallback_model != primary_model:
        models.append(fallback_model)

    last_error: Exception | None = None
    for model in models:
        try:
            if provider == "gemini":
                image = try_generate_image_gemini(api_key, model, built_prompt)
            elif provider == "openai":
                image = try_generate_image_openai(api_key, model, built_prompt)
            else:
                raise ValueError(f"unsupported provider: {provider}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fit_image(image, width, height).save(output_path)
            return model
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    raise RuntimeError(
        f"image generation failed for provider {provider} and models {models}: {last_error}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an image and save it locally")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output image path")
    parser.add_argument("--prompt", default=None, help="Prompt text")
    parser.add_argument("--prompt-file", type=Path, default=None, help="Prompt file")
    parser.add_argument(
        "--provider",
        choices=["gemini", "openai"],
        default="openai",
        help="Image provider. Defaults to OpenAI.",
    )
    parser.add_argument(
        "--model",
        default="gpt-image-2",
        help="Primary image model",
    )
    parser.add_argument(
        "--fallback-model",
        default="",
        help="Fallback image model. Defaults to Gemini fallback only when provider=gemini.",
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

    if args.provider == "gemini":
        default_model = "gemini-3.1-flash-image-preview"
        default_fallback_model = "gemini-2.5-flash-image"
    else:
        default_model = "gpt-image-2"
        default_fallback_model = None

    model = default_model if args.model == parser.get_default("model") else args.model
    fallback_model = args.fallback_model.strip() or default_fallback_model

    prompt = load_prompt(args.prompt, args.prompt_file)
    model_used = generate_image_file(
        output_path=args.output.resolve(),
        prompt=prompt,
        provider=args.provider,
        primary_model=model,
        fallback_model=fallback_model,
        image_kind=args.image_kind,
        width=args.width,
        height=args.height,
    )
    print(f"generated: {args.output.resolve()} via {args.provider}/{model_used}")


if __name__ == "__main__":
    main()
