from __future__ import annotations

from pathlib import Path

import yaml

from .models import ProjectConfig


def load_config(project_dir: Path) -> ProjectConfig:
    path = project_dir.resolve() / "video.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Missing project config: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return ProjectConfig.model_validate(payload)


def resolve_from_project(project_dir: Path, value: str) -> Path:
    return (project_dir.resolve() / value).resolve()


def build_dir(project_dir: Path, config: ProjectConfig) -> Path:
    return resolve_from_project(project_dir, config.build_dir)

