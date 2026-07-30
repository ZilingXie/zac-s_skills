from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import build_dir, resolve_from_project
from .utils import run, sha256_file, write_json


def _version(command: list[str]) -> str:
    result = run(command, capture=True)
    return (result.stdout or result.stderr).splitlines()[0].strip()


def write_build_manifest(
    project_dir: Path,
    config,
    plan,
    timings,
    synthesis,
    artifact_dir: Path,
    outputs: dict[str, Path],
) -> Path:
    deck = resolve_from_project(project_dir, config.deck)
    transcript = resolve_from_project(project_dir, config.transcript)
    pronunciations = resolve_from_project(project_dir, config.pronunciations)
    video_config = project_dir / "video.yaml"
    narration_plan = build_dir(project_dir, config) / "narration-plan.json"
    output_records = {
        name: {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for name, path in outputs.items()
        if path.is_file()
    }
    capture_metadata_path = build_dir(project_dir, config) / "slides" / "capture-metadata.json"
    capture_metadata = (
        json.loads(capture_metadata_path.read_text(encoding="utf-8"))
        if capture_metadata_path.is_file()
        else None
    )
    payload = {
        "schema_version": 1,
        "project": config.name,
        "built_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "tools": {
            "ffmpeg": _version(["ffmpeg", "-version"]),
            "ffprobe": _version(["ffprobe", "-version"]),
            "playwright": importlib.metadata.version("playwright"),
            "moviepy": importlib.metadata.version("moviepy"),
            "pydantic": importlib.metadata.version("pydantic"),
            "chromium": capture_metadata,
        },
        "inputs": {
            "deck": {"path": str(deck), "sha256": sha256_file(deck)},
            "transcript": {"path": str(transcript), "sha256": sha256_file(transcript)},
            "pronunciations": {
                "path": str(pronunciations),
                "sha256": sha256_file(pronunciations),
            },
            "video_config": {
                "path": str(video_config),
                "sha256": sha256_file(video_config),
            },
            "narration_plan": {
                "path": str(narration_plan),
                "sha256": sha256_file(narration_plan),
                "approved": plan.approved,
            },
        },
        "narration": {
            "region": synthesis.region,
            "voice": synthesis.voice,
            "output_format": synthesis.output_format,
            "sentence_count": synthesis.requested_sentences,
            "generated_sentences": synthesis.generated_sentences,
            "cache_hits": synthesis.cache_hits,
            "submitted_characters": synthesis.submitted_characters,
        },
        "timeline": {
            "slides": len(timings.slides),
            "sentences": len(timings.sentences),
            "duration_seconds": timings.total_duration,
        },
        "video": config.video.model_dump(mode="json"),
        "captions": config.captions.model_dump(mode="json"),
        "outputs": output_records,
    }
    path = artifact_dir / "build-manifest.json"
    write_json(path, payload)
    return path
