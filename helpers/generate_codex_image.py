"""Generate an image via the Codex CLI's built-in image_gen tool.

Uses the local ChatGPT-subscription Codex login (no OPENAI_API_KEY). The heavy
lifting — model, sizes, saving — is done by Codex's bundled imagegen skill; this
wrapper just dispatches a natural-language instruction and verifies the file.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

QUALITY_CHOICES = ("low", "medium", "high")


def load_prompt(prompt: str | None, prompt_file: Path | None) -> str:
    if prompt_file:
        if not prompt_file.exists():
            sys.exit(f"prompt file not found: {prompt_file}")
        return prompt_file.read_text().strip()
    if prompt and prompt.strip():
        return prompt.strip()
    sys.exit("provide --prompt or --prompt-file")


def build_instruction(prompt: str, output: Path, size: str, quality: str) -> str:
    return (
        "Use the image_gen tool to generate ONE image from the art direction below. "
        f"Save it to exactly this absolute path: {output.resolve()} . "
        f"Size {size}, quality {quality}, png format. "
        "Do not paste the image into your reply; just generate and save the file, "
        "then confirm the absolute path you saved it to.\n\n"
        "Art direction:\n"
        + prompt
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an image via Codex CLI image_gen (ChatGPT subscription)"
    )
    parser.add_argument("--prompt", default=None, help="Inline art direction")
    parser.add_argument("--prompt-file", type=Path, default=None, help="Art direction file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to <cwd>/cover.png",
    )
    parser.add_argument(
        "--size",
        default="1024x1024",
        help="Image size: 1024x1024 (1:1), 1536x1024 (16:9), 1024x1536 (9:16)",
    )
    parser.add_argument("--quality", default="medium", choices=QUALITY_CHOICES)
    parser.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="Working directory for codex exec (sandbox workspace). Defaults to output parent",
    )
    args = parser.parse_args()

    prompt = load_prompt(args.prompt, args.prompt_file)
    output = (args.output or Path("cover.png")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    workdir = (args.cwd or output.parent).resolve()
    if not output.exists() and output.is_dir():
        sys.exit(f"output must be a file path: {output}")

    instruction = build_instruction(prompt, output, args.size, args.quality)
    result = subprocess.run(
        ["codex", "exec", "--skip-git-repo-check", instruction],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        timeout=1200,
    )

    if not output.exists():
        tail = "\n".join((result.stderr or result.stdout or "").splitlines()[-12:])
        print(tail, file=sys.stderr)
        if "could not be refreshed" in tail or "401" in tail:
            sys.exit("Codex auth expired. Run: codex login  (browser sign-in), then retry.")
        sys.exit(f"codex exec finished (code {result.returncode}) but {output} was not created")

    print(f"generated: {output} via codex image_gen ({args.size}, {args.quality})")


if __name__ == "__main__":
    main()
