from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from edl_io import format_clock, format_duration
from pack_transcripts import group_words


FILLER_PATTERNS = {
    "zh": [
        r"^嗯+$",
        r"^啊+$",
        r"^呃+$",
        r"^額+$",
        r"^那個$",
        r"^就是$",
        r"^然後$",
        r"^對+$",
        r"^對對+$",
        r"^嗯哼$",
        r"^這樣$",
    ],
    "en": [
        r"^um+$",
        r"^uh+$",
        r"^er+$",
        r"^ah+$",
        r"^like$",
        r"^youknow$",
        r"^sortof$",
        r"^kindof$",
        r"^basically$",
        r"^actually$",
    ],
}


def run_silencedetect(audio_path: Path, noise_db: float, min_silence: float) -> list[dict]:
    cmd = [
        "ffmpeg",
        "-i",
        str(audio_path),
        "-af",
        f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    stderr = result.stderr or ""
    starts: list[float] = []
    silences: list[dict] = []
    for line in stderr.splitlines():
        if "silence_start:" in line:
            match = re.search(r"silence_start:\s*([0-9.]+)", line)
            if match:
                starts.append(float(match.group(1)))
        if "silence_end:" in line:
            match = re.search(
                r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)",
                line,
            )
            if match:
                end = float(match.group(1))
                duration = float(match.group(2))
                start = starts.pop(0) if starts else max(0.0, end - duration)
                silences.append({"start": start, "end": end, "duration": duration})
    return silences


def get_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def load_transcript_words(edit_dir: Path, stem: str) -> list[dict]:
    path = edit_dir / "transcripts" / f"{stem}.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    words = []
    for word in payload.get("words", []):
        token = (word.get("word") or "").strip()
        start = word.get("start")
        end = word.get("end")
        if not token or start is None or end is None:
            continue
        words.append({"word": token, "start": float(start), "end": float(end)})
    return words


def normalize_token(token: str) -> str:
    return re.sub(r"[\s\W_]+", "", token.lower())


def find_fillers(words: list[dict]) -> list[dict]:
    compiled = {
        lang: [re.compile(pat, re.IGNORECASE) for pat in pats]
        for lang, pats in FILLER_PATTERNS.items()
    }
    hits: list[dict] = []
    for word in words:
        token = word["word"].strip()
        norm = normalize_token(token)
        if not norm:
            continue
        for lang, patterns in compiled.items():
            if any(pat.match(norm) or pat.match(token.strip()) for pat in patterns):
                hits.append(
                    {
                        "word": token,
                        "start": word["start"],
                        "end": word["end"],
                        "lang": lang,
                    }
                )
                break
    return hits


def find_retake_clusters(phrases: list[dict], similarity_chars: int = 12) -> list[dict]:
    clusters: list[dict] = []
    i = 0
    while i < len(phrases) - 1:
        current = phrases[i]
        text = re.sub(r"\s+", "", current["text"])[:similarity_chars]
        if len(text) < 6:
            i += 1
            continue
        group = [current]
        j = i + 1
        while j < len(phrases):
            nxt = phrases[j]
            nxt_text = re.sub(r"\s+", "", nxt["text"])[:similarity_chars]
            gap = float(nxt["start"]) - float(group[-1]["end"])
            if gap > 8.0:
                break
            if nxt_text and (nxt_text == text or text.startswith(nxt_text) or nxt_text.startswith(text)):
                group.append(nxt)
                j += 1
                continue
            break
        if len(group) >= 2:
            clusters.append(
                {
                    "count": len(group),
                    "start": group[0]["start"],
                    "end": group[-1]["end"],
                    "texts": [item["text"] for item in group],
                }
            )
            i = j
        else:
            i += 1
    return clusters


def write_report(
    *,
    edit_dir: Path,
    audio_path: Path,
    duration: float,
    silences: list[dict],
    fillers: list[dict],
    phrases: list[dict],
    retakes: list[dict],
    min_silence_report: float,
) -> tuple[Path, Path]:
    analysis_dir = edit_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    long_silences = [s for s in silences if s["duration"] >= min_silence_report]
    speech_estimate = duration - sum(s["duration"] for s in silences)
    speech_estimate = max(0.0, speech_estimate)

    payload = {
        "source": audio_path.name,
        "duration": duration,
        "silence_count": len(silences),
        "long_silence_count": len(long_silences),
        "filler_count": len(fillers),
        "phrase_count": len(phrases),
        "retake_cluster_count": len(retakes),
        "speech_estimate_seconds": speech_estimate,
        "silences": silences,
        "long_silences": long_silences,
        "fillers": fillers[:200],
        "retake_clusters": retakes[:50],
    }
    json_path = analysis_dir / f"{audio_path.stem}_analysis.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    lines = [
        f"# Analysis: {audio_path.name}",
        "",
        f"- duration: {format_duration(duration)}",
        f"- estimated speech: {format_duration(speech_estimate)}",
        f"- silence regions: {len(silences)}",
        f"- long silences (>= {min_silence_report:.1f}s): {len(long_silences)}",
        f"- filler candidates: {len(fillers)}",
        f"- phrase count: {len(phrases)}",
        f"- possible retake clusters: {len(retakes)}",
        "",
        "## Long silences (review before cutting)",
        "",
    ]
    if long_silences:
        for item in sorted(long_silences, key=lambda s: s["duration"], reverse=True)[:20]:
            lines.append(
                f"- {format_clock(item['start'])}-{format_clock(item['end'])} "
                f"({format_duration(item['duration'])})"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Filler candidates (sample)", ""])
    if fillers:
        for item in fillers[:40]:
            lines.append(
                f"- {format_clock(item['start'])} `{item['word']}` ({item['lang']})"
            )
    else:
        lines.append("- none detected by heuristic")

    lines.extend(["", "## Possible retake clusters", ""])
    if retakes:
        for item in retakes[:15]:
            preview = item["texts"][0][:80]
            lines.append(
                f"- {format_clock(item['start'])}-{format_clock(item['end'])} "
                f"x{item['count']}: {preview}"
            )
    else:
        lines.append("- none detected")

    lines.extend(
        [
            "",
            "## Editing hints",
            "",
            "- Prefer removing dead air and false starts before content cuts.",
            "- Keep breaths and pauses that protect jokes, emotion, or turn-taking.",
            "- Treat filler hits as candidates, not automatic deletes.",
            "- For retake clusters, keep the cleanest complete take.",
            "",
        ]
    )

    md_path = analysis_dir / f"{audio_path.stem}_suggestions.md"
    md_path.write_text("\n".join(lines))

    # Convenience alias for single-source workflows
    (analysis_dir / "suggestions.md").write_text("\n".join(lines))
    return json_path, md_path


def analyze_one(
    audio_path: Path,
    edit_dir: Path,
    *,
    noise_db: float,
    min_silence: float,
    min_silence_report: float,
    phrase_silence: float,
) -> None:
    duration = get_duration(audio_path)
    silences = run_silencedetect(audio_path, noise_db=noise_db, min_silence=min_silence)
    words = load_transcript_words(edit_dir, audio_path.stem)
    phrases = group_words(words, phrase_silence) if words else []
    fillers = find_fillers(words) if words else []
    retakes = find_retake_clusters(phrases) if phrases else []
    json_path, md_path = write_report(
        edit_dir=edit_dir,
        audio_path=audio_path,
        duration=duration,
        silences=silences,
        fillers=fillers,
        phrases=phrases,
        retakes=retakes,
        min_silence_report=min_silence_report,
    )
    print(f"analysis: {json_path}")
    print(f"suggestions: {md_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze spoken-word audio for silence, fillers, and retake clusters"
    )
    parser.add_argument("audio", nargs="+", type=Path, help="Source audio file(s)")
    parser.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="Edit directory. Defaults to <first_audio_dir>/edit",
    )
    parser.add_argument(
        "--noise-db",
        type=float,
        default=-35.0,
        help="silencedetect noise threshold in dB",
    )
    parser.add_argument(
        "--min-silence",
        type=float,
        default=0.35,
        help="Minimum silence duration for detection",
    )
    parser.add_argument(
        "--min-silence-report",
        type=float,
        default=1.0,
        help="Minimum silence duration to highlight as long silence",
    )
    parser.add_argument(
        "--phrase-silence",
        type=float,
        default=0.5,
        help="Silence threshold used when grouping transcript phrases",
    )
    args = parser.parse_args()

    audio_paths = [path.resolve() for path in args.audio]
    missing = [str(path) for path in audio_paths if not path.exists()]
    if missing:
        sys.exit(f"audio not found: {', '.join(missing)}")
    edit_dir = (args.edit_dir or (audio_paths[0].parent / "edit")).resolve()
    edit_dir.mkdir(parents=True, exist_ok=True)

    for audio_path in audio_paths:
        analyze_one(
            audio_path,
            edit_dir,
            noise_db=args.noise_db,
            min_silence=args.min_silence,
            min_silence_report=args.min_silence_report,
            phrase_silence=args.phrase_silence,
        )


if __name__ == "__main__":
    main()
