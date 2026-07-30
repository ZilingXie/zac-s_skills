from __future__ import annotations

import platform
import re
import shutil
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from .config import build_dir, resolve_from_project
from .models import NarrationPlan, SentencePlan, SlidePlan
from .normalizer import caption_text, load_pronunciations, normalize_spoken, validate_spoken
from .transcript import parse_transcript
from .utils import sha256_file


def deck_slides(path: Path) -> list[tuple[int, str]]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    result: list[tuple[int, str]] = []
    for element in soup.select("section.slide[data-index]"):
        raw_index = element.get("data-index", "")
        if not re.fullmatch(r"\d+", raw_index):
            raise ValueError(f"Invalid slide data-index: {raw_index!r}")
        result.append((int(raw_index), str(element.get("data-title", "")).strip()))
    if not result:
        raise ValueError(f"No section.slide[data-index] elements found in {path}")
    return result


def validate_project_inputs(project_dir: Path, config) -> dict[str, object]:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError(
            f"This release supports Apple Silicon macOS only; got {platform.system()} {platform.machine()}"
        )
    missing_tools = [tool for tool in ("ffmpeg", "ffprobe", "curl") if not shutil.which(tool)]
    if missing_tools:
        raise FileNotFoundError(f"Missing required command-line tools: {missing_tools}")
    with sync_playwright() as playwright:
        chromium_path = Path(playwright.chromium.executable_path)
    if not chromium_path.is_file():
        raise FileNotFoundError(
            "Playwright Chromium is not installed; run `uv run playwright install chromium`"
        )
    transcript_path = resolve_from_project(project_dir, config.transcript)
    deck_path = resolve_from_project(project_dir, config.deck)
    pronunciations_path = resolve_from_project(project_dir, config.pronunciations)
    for label, path in {
        "deck": deck_path,
        "transcript": transcript_path,
        "pronunciations": pronunciations_path,
    }.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing {label}: {path}")

    soup = BeautifulSoup(deck_path.read_text(encoding="utf-8"), "html.parser")
    missing_assets: list[str] = []
    local_assets: list[Path] = []
    for element in soup.select("img[src]"):
        source = str(element.get("src", "")).strip()
        if not source or source.startswith(("http://", "https://", "data:")):
            continue
        asset = (deck_path.parent / source).resolve()
        if not asset.is_file():
            missing_assets.append(str(asset))
        else:
            local_assets.append(asset)
    if missing_assets:
        raise FileNotFoundError("Missing deck assets: " + ", ".join(missing_assets))

    plan = create_plan(project_dir, config, approved=False)
    focus_selectors: list[dict[str, object]] = []
    for cue in config.focus_cues:
        slide = soup.select_one(f'section.slide[data-index="{cue.slide:02d}"]')
        if slide is None or slide.select_one(cue.selector) is None:
            raise ValueError(f"Focus selector not found on slide {cue.slide}: {cue.selector}")
        slide_plan = next((item for item in plan.slides if item.number == cue.slide), None)
        if slide_plan is None:
            raise ValueError(f"Focus cue references an unknown slide: {cue.slide}")
        sentence_count = len(slide_plan.sentences)
        end_sentence = cue.end_sentence or sentence_count
        if cue.start_sentence > sentence_count or end_sentence > sentence_count:
            raise ValueError(
                f"Focus cue sentence range exceeds slide {cue.slide} narration: "
                f"{cue.start_sentence}-{end_sentence} of {sentence_count}"
            )
        focus_selectors.append({"slide": cue.slide, "selector": cue.selector})

    return {
        "slides": len(plan.slides),
        "sentences": sum(len(slide.sentences) for slide in plan.slides),
        "assets": len(local_assets),
        "focus_selectors": focus_selectors,
        "environment": {
            "system": platform.system(),
            "machine": platform.machine(),
            "macos": platform.mac_ver()[0],
            "chromium_executable": str(chromium_path),
        },
        "input_hashes": {
            "deck": sha256_file(deck_path),
            "transcript": sha256_file(transcript_path),
            "pronunciations": sha256_file(pronunciations_path),
        },
    }


def create_plan(project_dir: Path, config, *, approved: bool = True) -> NarrationPlan:
    transcript_path = resolve_from_project(project_dir, config.transcript)
    deck_path = resolve_from_project(project_dir, config.deck)
    pronunciations_path = resolve_from_project(project_dir, config.pronunciations)
    transcript = parse_transcript(transcript_path)
    deck = deck_slides(deck_path)

    deck_numbers = [number for number, _ in deck]
    transcript_numbers = [slide.number for slide in transcript]
    if deck_numbers != transcript_numbers:
        raise ValueError(
            f"Deck/transcript mismatch: deck={deck_numbers}, transcript={transcript_numbers}"
        )

    mappings = load_pronunciations(pronunciations_path)
    slides: list[SlidePlan] = []
    for parsed_slide in transcript:
        sentences: list[SentencePlan] = []
        for order, parsed_sentence in enumerate(parsed_slide.sentences, 1):
            spoken = normalize_spoken(parsed_sentence.text, mappings)
            sentences.append(
                SentencePlan(
                    id=f"{parsed_slide.number:02d}-{order:02d}",
                    slide=parsed_slide.number,
                    order=order,
                    paragraph=parsed_sentence.paragraph,
                    source_text=parsed_sentence.text,
                    caption_text=caption_text(parsed_sentence.text),
                    spoken_text=spoken,
                )
            )
        slides.append(
            SlidePlan(
                id=f"{parsed_slide.number:02d}",
                number=parsed_slide.number,
                title=parsed_slide.title,
                sentences=sentences,
            )
        )
    return NarrationPlan(project=config.name, approved=approved, slides=slides)


def save_plan(project_dir: Path, config, plan: NarrationPlan) -> Path:
    output_dir = build_dir(project_dir, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "narration-plan.json"
    path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def load_plan(project_dir: Path, config) -> NarrationPlan:
    path = build_dir(project_dir, config) / "narration-plan.json"
    plan = NarrationPlan.model_validate_json(path.read_text(encoding="utf-8"))
    for slide in plan.slides:
        for sentence in slide.sentences:
            validate_spoken(sentence.spoken_text)
    return plan
