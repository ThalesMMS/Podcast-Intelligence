#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-}"

if [[ -z "$TARGET" ]]; then
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) TARGET="aarch64-apple-darwin" ;;
    Darwin-x86_64) TARGET="x86_64-apple-darwin" ;;
    Linux-aarch64) TARGET="aarch64-unknown-linux-gnu" ;;
    Linux-x86_64) TARGET="x86_64-unknown-linux-gnu" ;;
    *) echo "Unsupported host. Pass a Rust target triple explicitly." >&2; exit 2 ;;
  esac
fi

MEDIA_DIR="$ROOT_DIR/build/media/$TARGET"
mkdir -p "$MEDIA_DIR"

command -v uv >/dev/null || { echo "uv is required" >&2; exit 2; }
command -v npm >/dev/null || { echo "Node.js/npm is required" >&2; exit 2; }
command -v cargo >/dev/null || { echo "Rust/cargo is required" >&2; exit 2; }

python3 "$ROOT_DIR/scripts/fetch_media_tools.py" --target "$TARGET" --output-dir "$MEDIA_DIR"
ATTRIBUTION_DIR="$ROOT_DIR/frontend/src-tauri/third_party/ffmpeg"
mkdir -p "$ATTRIBUTION_DIR"
cp "$MEDIA_DIR/SOURCE.json" "$ATTRIBUTION_DIR/SOURCE.json"
for notice in UPSTREAM-LICENSE.txt UPSTREAM-README.txt; do
  if [[ -f "$MEDIA_DIR/$notice" ]]; then cp "$MEDIA_DIR/$notice" "$ATTRIBUTION_DIR/$notice"; fi
done
suffix=""
if [[ "$TARGET" == *windows* ]]; then suffix=".exe"; fi
(
  cd "$ROOT_DIR/backend"
  uv sync --extra desktop --extra dev
  uv run python scripts/build_engine.py \
    --target "$TARGET" \
    --ffmpeg "$MEDIA_DIR/ffmpeg${suffix}" \
    --ffprobe "$MEDIA_DIR/ffprobe${suffix}"
)
(
  cd "$ROOT_DIR/frontend"
  npm install --no-audit --no-fund
  npm run tauri build -- --target "$TARGET"
)
