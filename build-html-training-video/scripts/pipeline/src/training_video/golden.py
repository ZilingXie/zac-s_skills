from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .config import resolve_from_project
from .utils import sha256_file, write_json


def approve_goldens(
    project_dir: Path,
    config,
    slide_numbers: list[int],
    screenshots: dict[int, Path],
    *,
    confirmed: bool,
) -> Path:
    if not confirmed:
        raise ValueError(
            "Golden approval requires --confirm after visually reviewing the selected slides"
        )
    golden_value = config.golden_dir or "golden"
    golden_dir = resolve_from_project(project_dir, golden_value)
    golden_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for slide_number in slide_numbers:
        source = screenshots[slide_number]
        target = golden_dir / f"{slide_number:02d}.png"
        shutil.copy2(source, target)
        records.append(
            {
                "slide": slide_number,
                "path": str(target),
                "sha256": sha256_file(target),
            }
        )

    config_path = project_dir / "video.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    payload["golden_dir"] = golden_value
    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    manifest = {
        "approved_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "project": config.name,
        "slides": records,
        "rms_tolerance": config.golden_rms_tolerance,
    }
    manifest_path = golden_dir / "golden-manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path
