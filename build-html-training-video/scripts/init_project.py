#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["beautifulsoup4==4.13.4"]
# ///
from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup


SLIDE_HEADING = re.compile(r"^## Slide\s+(\d+)\s+-\s+(.+?)\s*$")
SKIP_NAMES = {".env", ".git", ".venv", "__pycache__", "build", "node_modules"}
RESOURCE_SELECTORS = {
    "img": ("src", "srcset"),
    "script": ("src",),
    "link": ("href",),
    "source": ("src", "srcset"),
    "video": ("src", "poster"),
    "audio": ("src",),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create an isolated HTML training-video project")
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    return parser


def _validate_transcript(path: Path) -> int:
    numbers = [
        int(match.group(1))
        for line in path.read_text(encoding="utf-8").splitlines()
        if (match := SLIDE_HEADING.match(line))
    ]
    expected = list(range(1, len(numbers) + 1))
    if not numbers or numbers != expected:
        raise ValueError(
            "Transcript headings must be sequential `## Slide N - Title` sections; "
            f"expected {expected}, got {numbers}"
        )
    return len(numbers)


def _local_resource(value: str) -> str | None:
    value = value.strip().strip("'\"")
    if not value or value.startswith(("data:", "http://", "https://", "//", "#")):
        return None
    path = unquote(urlsplit(value).path)
    return path or None


def _copy_resource(source_root: Path, target_root: Path, resource: str) -> Path:
    relative = Path(resource)
    if relative.is_absolute() or ".." in relative.parts or relative.name in SKIP_NAMES:
        raise ValueError(f"Unsupported local resource path outside the HTML bundle: {resource}")
    source = (source_root / relative).resolve()
    try:
        source.relative_to(source_root.resolve())
    except ValueError as error:
        raise ValueError(f"Resource escapes the HTML bundle: {resource}") from error
    if not source.exists():
        raise FileNotFoundError(f"Missing local HTML resource: {source}")
    target = target_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIP_NAMES))
    else:
        shutil.copy2(source, target)
    return target


def _copy_referenced_resources(soup: BeautifulSoup, source_root: Path, target_root: Path) -> None:
    resources: set[str] = set()
    for selector, attributes in RESOURCE_SELECTORS.items():
        for element in soup.select(selector):
            for attribute in attributes:
                raw_value = str(element.get(attribute, ""))
                values = [part.strip().split()[0] for part in raw_value.split(",") if part.strip()]
                for value in values:
                    if local := _local_resource(value):
                        resources.add(local)
    for resource in sorted(resources):
        _copy_resource(source_root, target_root, resource)


def _slide_elements(soup: BeautifulSoup):
    selectors = ("section.slide", ".slide", "[data-slide]", "main > section", "body > section")
    for selector in selectors:
        slides = soup.select(selector)
        if slides:
            return slides, selector
    raise ValueError("No static slide elements found in the HTML document")


def _normalize_deck(source: Path, target: Path) -> int:
    soup = BeautifulSoup(source.read_text(encoding="utf-8"), "html.parser")
    slides, selected_by = _slide_elements(soup)

    adapted_layout = selected_by not in {"section.slide", ".slide"}
    for index, slide in enumerate(slides, 1):
        slide.name = "section"
        classes = [str(value) for value in slide.get("class", []) if value != "active"]
        if "slide" not in classes:
            classes.append("slide")
        if index == 1:
            classes.append("active")
        slide["class"] = classes
        slide["data-index"] = f"{index:02d}"
        if not str(slide.get("data-title", "")).strip():
            heading = slide.select_one("h1, h2, h3")
            slide["data-title"] = heading.get_text(" ", strip=True) if heading else f"Slide {index}"

    if adapted_layout:
        style = soup.new_tag("style")
        style.string = (
            "html,body{width:100%;height:100%;margin:0;overflow:hidden}"
            "section.slide{position:absolute!important;inset:0!important;display:none!important}"
            "section.slide.active{display:block!important}"
        )
        (soup.head or soup).append(style)

    script = soup.new_tag("script")
    script.string = """
(() => {
  const trainingSlides = [...document.querySelectorAll('section.slide[data-index]')];
  window.show = (index) => {
    trainingSlides.forEach((slide, position) => slide.classList.toggle('active', position === index));
    history.replaceState(null, '', `#${index + 1}`);
  };
  const initial = Math.max(0, Number(location.hash.slice(1) || 1) - 1);
  window.show(initial);
})();
"""
    (soup.body or soup).append(script)
    target.write_text(str(soup), encoding="utf-8")
    return len(slides)


def _yaml_string(value: str | Path) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def main() -> int:
    args = _parser().parse_args()
    html_path = args.html.expanduser().resolve()
    transcript_path = args.transcript.expanduser().resolve()
    project_dir = args.project_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not html_path.is_file() or not transcript_path.is_file():
        raise FileNotFoundError("Both --html and --transcript must reference existing files")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.name):
        raise ValueError("--name must use lowercase letters, digits, and hyphens")
    if project_dir.exists():
        raise FileExistsError(f"Project directory must not already exist: {project_dir}")

    transcript_count = _validate_transcript(transcript_path)
    source_soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    slide_count = len(_slide_elements(source_soup)[0])
    if slide_count != transcript_count:
        raise ValueError(
            f"HTML/transcript slide count mismatch: HTML={slide_count}, transcript={transcript_count}"
        )
    project_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=f".{project_dir.name}-", dir=project_dir.parent))
    source_dir = staging_dir / "source"
    source_dir.mkdir()
    try:
        _copy_referenced_resources(source_soup, html_path.parent, source_dir)
        deck_target = source_dir / html_path.name
        _normalize_deck(html_path, deck_target)
        shutil.copy2(transcript_path, staging_dir / "transcript.md")
        (staging_dir / "pronunciations.yaml").write_text("mappings: {}\n", encoding="utf-8")
        config = f"""name: {_yaml_string(args.name)}
deck: source/{html_path.name}
transcript: transcript.md
pronunciations: pronunciations.yaml
build_dir: {_yaml_string(output_dir)}
speech:
  region: japanwest
  voice: en-US-AndrewMultilingualNeural
  output_format: riff-24khz-16bit-mono-pcm
  rate: "+0%"
  env_file: .env
  key_env: AZURE_SPEECH_KEY
  timeout_seconds: 45
  retries: 8
pauses:
  leading: 0.8
  sentence: 0.28
  paragraph: 0.55
  trailing: 0.9
captions:
  font: Arial
  font_size: 34
  max_chars_per_line: 92
  margin_horizontal: 110
  margin_vertical: 54
video:
  width: 1920
  height: 1080
  fps: 30
  codec: libx264
  preset: medium
  crf: 18
  transition_seconds: 0.15
capture:
  hide_selectors: []
  settle_ms: 1000
focus_cues: []
"""
        (staging_dir / "video.yaml").write_text(config, encoding="utf-8")
        staging_dir.rename(project_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    print(project_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
