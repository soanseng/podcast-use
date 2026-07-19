from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "helpers"


def run_helper(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_init_status_and_glossary(tmp_path: Path) -> None:
    edit = tmp_path / "edit"
    run_helper(str(HELPERS / "init_status.py"), "--edit-dir", str(edit))
    status = edit / "STATUS.md"
    assert status.exists()
    text = status.read_text()
    assert "mode:" in text
    assert "phase:" in text

    # second call should not overwrite
    before = status.read_text()
    run_helper(str(HELPERS / "init_status.py"), "--edit-dir", str(edit))
    assert status.read_text() == before

    run_helper(str(HELPERS / "init_glossary.py"), "--edit-dir", str(edit))
    glossary = (edit / "glossary.txt").read_text()
    assert "One term per line" in glossary
    assert "AnatoMee" not in glossary


def test_approve_edl_cli(tmp_path: Path) -> None:
    edit = tmp_path / "edit"
    edit.mkdir()
    draft = edit / "edl.draft.json"
    draft.write_text('[{"source":"episode","start":0.0,"end":1.0,"reason":"x"}]\n')
    run_helper(str(HELPERS / "approve_edl.py"), "--edit-dir", str(edit))
    assert (edit / "edl.approved.json").exists()
    assert (edit / "edl.json").exists()
    assert (edit / "edl.approved.json").read_text() == draft.read_text()
