from __future__ import annotations

import argparse
from pathlib import Path


TEMPLATE = """{
  "global_style": "Bold editorial collage with cinematic lighting and strong typography space",
  "global_note": "Keep reels between 30 and 60 seconds. Prioritize one idea per reel. Reels must be vertical 9:16.",
  "reels": [
    {
      "id": "reel_01",
      "source": "PHONE",
      "start": 120.0,
      "end": 165.0,
      "title": "AI 讓時間加倍？",
      "hook": "當你懂一點技術，又有 AI，很多以前做不到的事突然做得到了。",
      "why_it_works": "Strong claim, immediate curiosity, and clear self-contained idea.",
      "style_tag": "cinematic philosophical",
      "aspect_ratio": "9:16",
      "image_prompt": "A thoughtful Taiwanese podcast visual about AI multiplying human time, cinematic, editorial, vertical, strong focal subject, modern but human.",
      "intro": "本集精華"
    }
  ]
}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a reels plan template")
    parser.add_argument("--edit-dir", type=Path, required=True, help="Edit directory")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Defaults to <edit_dir>/reels_plan.json",
    )
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    edit_dir.mkdir(parents=True, exist_ok=True)
    output = args.output or (edit_dir / "reels_plan.json")
    if output.exists():
        print(f"exists: {output}")
        return
    output.write_text(TEMPLATE)
    print(f"created: {output}")


if __name__ == "__main__":
    main()
