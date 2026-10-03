from __future__ import annotations

import argparse
from pathlib import Path


FILES = {
    "show_notes.md": """# Show Notes

## Episode Summary

TODO

## Key Topics

- TODO

## Notable Quotes

- TODO

## Resources

- TODO
""",
    "timestamps.txt": """00:00 Intro
""",
    "youtube_description.md": """EPISODE HOOK

TODO short description

Timestamps
00:00 Intro

Links
- Host: TODO
- Guest: TODO
- Sponsor: TODO
""",
    "cover_prompt.md": """# Cover Prompt

## Episode

- Title: TODO
- Host: TODO
- Guest: TODO

## Visual Direction

- Mood: TODO
- Palette: TODO
- Composition: 16:9 YouTube cover

## Prompt

TODO

## Negative Prompt

Avoid clutter, unreadable tiny text, distorted faces, extra fingers, low contrast typography.
""",
    "facebook_post.md": """# Facebook Post

Target: ~2000 characters (1800-2200) in the episode's language.

## Structure

1. Hook line (stands alone in feed preview)
2. Why this episode matters
3. 3-5 key takeaways or moments (rough timestamps optional)
4. One question to the audience
5. CTA: listen link placeholder

## Draft

TODO
""",
    "threads_post.md": """# Threads / X Post

Hard limit: 500 characters including spaces and hashtags. One idea only.

- Strongest hook from the episode, plain language
- 1-3 hashtags max
- Listen link placeholder at the end

## Draft

TODO
""",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create editable deliverable files in edit/")
    parser.add_argument("audio", type=Path, help="Path to source audio")
    parser.add_argument("--edit-dir", type=Path, default=None, help="Defaults to <audio_dir>/edit")
    args = parser.parse_args()

    audio_path = args.audio.resolve()
    edit_dir = (args.edit_dir or (audio_path.parent / "edit")).resolve()
    edit_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in FILES.items():
        path = edit_dir / filename
        if not path.exists():
            path.write_text(content)
            print(f"created: {path}")
        else:
            print(f"exists: {path}")


if __name__ == "__main__":
    main()
