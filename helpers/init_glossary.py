from __future__ import annotations

import argparse
from pathlib import Path


TEMPLATE = """# One term per line. Lines starting with # are ignored.
覓己
AnatoMee
陳璿丞
Claude Code
ChatGPT
Substack
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a glossary template for transcription")
    parser.add_argument("--edit-dir", type=Path, required=True, help="Edit directory")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Defaults to <edit_dir>/glossary.txt",
    )
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    edit_dir.mkdir(parents=True, exist_ok=True)
    output = args.output or (edit_dir / "glossary.txt")
    if output.exists():
        print(f"exists: {output}")
        return
    output.write_text(TEMPLATE)
    print(f"created: {output}")


if __name__ == "__main__":
    main()
