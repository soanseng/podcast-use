#!/usr/bin/env bash

set -euo pipefail

TARGET="${1:-claude}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$TARGET" in
  claude)
    DEST_DIR="${HOME}/.claude/skills"
    DEST_LINK="${DEST_DIR}/podcast-use"
    ;;
  codex)
    DEST_DIR="${CODEX_HOME:-${HOME}/.codex}/skills"
    DEST_LINK="${DEST_DIR}/podcast-use"
    ;;
  *)
    echo "usage: $0 [claude|codex]" >&2
    exit 1
    ;;
esac

mkdir -p "$DEST_DIR"
ln -sfn "$ROOT" "$DEST_LINK"

if command -v uv >/dev/null 2>&1; then
  (
    cd "$ROOT"
    UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}" uv sync
  )
else
  echo "uv not found; install uv first" >&2
  exit 1
fi

echo "installed: $DEST_LINK"
echo "restart your client to pick up the skill"
