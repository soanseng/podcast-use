from __future__ import annotations

import argparse
from pathlib import Path


TEMPLATE = """# Edit status

mode: unset
phase: inventory
source:
transcript: not_started
analysis: not_started
edl: none
preview: none
final: not_rendered
subtitles: not_started
packaging: not_started

## Decisions
- 

## Open questions
- 

## Notes
- 
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Create edit/STATUS.md session tracker")
    parser.add_argument("--edit-dir", type=Path, required=True, help="Edit directory")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Defaults to <edit_dir>/STATUS.md",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing STATUS.md",
    )
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    edit_dir.mkdir(parents=True, exist_ok=True)
    output = args.output or (edit_dir / "STATUS.md")
    if output.exists() and not args.force:
        print(f"exists: {output}")
        return
    output.write_text(TEMPLATE)
    print(f"created: {output}")


if __name__ == "__main__":
    main()
