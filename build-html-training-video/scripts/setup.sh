#!/usr/bin/env bash
set -euo pipefail

skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pipeline_dir="$skill_dir/scripts/pipeline"

host_system="$(uname -s)"
case "$host_system" in
  Darwin|Linux) ;;
  *)
    echo "error: build-html-training-video supports macOS and Linux; got $host_system" >&2
    exit 1
    ;;
esac

for command_name in uv ffmpeg ffprobe curl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "error: missing required command: $command_name" >&2
    exit 1
  fi
done

if ! ffmpeg -hide_banner -encoders 2>&1 | grep 'libx264' >/dev/null; then
  echo "error: FFmpeg does not include the libx264 encoder" >&2
  exit 1
fi
if ! ffmpeg -hide_banner -filters 2>&1 | grep -E '(^|[[:space:]])ass[[:space:]]' >/dev/null; then
  echo "error: FFmpeg does not include the libass subtitle filter" >&2
  exit 1
fi

uv sync --project "$pipeline_dir"
uv run --project "$pipeline_dir" playwright install chromium
echo "build-html-training-video setup complete"
