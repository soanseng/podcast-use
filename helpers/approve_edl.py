from __future__ import annotations

import argparse
import sys
from pathlib import Path

from edl_io import approve_edl


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Promote edl.draft.json (or edl.json) to edl.approved.json"
    )
    parser.add_argument("--edit-dir", type=Path, required=True, help="Edit directory")
    parser.add_argument(
        "--from",
        dest="source_name",
        default="edl.draft.json",
        help="Source EDL filename inside edit-dir (default: edl.draft.json)",
    )
    args = parser.parse_args()
    edit_dir = args.edit_dir.resolve()
    if not edit_dir.is_dir():
        sys.exit(f"edit dir not found: {edit_dir}")
    approved = approve_edl(edit_dir, source_name=args.source_name)
    print(f"approved: {approved}")
    print(f"alias: {edit_dir / 'edl.json'}")


if __name__ == "__main__":
    main()
