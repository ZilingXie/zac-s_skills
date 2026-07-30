from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SLIDE_HEADING = re.compile(r"^## Slide\s+(\d+)\s+-\s+(.+?)\s*$")
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
ABBREVIATIONS = (
    "e.g.",
    "i.e.",
    "Mr.",
    "Mrs.",
    "Ms.",
    "Dr.",
    "Prof.",
    "vs.",
    "etc.",
)


@dataclass(frozen=True)
class ParsedSentence:
    paragraph: int
    text: str


@dataclass(frozen=True)
class ParsedSlide:
    number: int
    title: str
    sentences: list[ParsedSentence]


def split_sentences(paragraph: str) -> list[str]:
    text = " ".join(paragraph.split())
    placeholders: dict[str, str] = {}
    for index, abbreviation in enumerate(ABBREVIATIONS):
        placeholder = f"\u0001{index}\u0002"
        if abbreviation in text:
            text = text.replace(abbreviation, placeholder)
            placeholders[placeholder] = abbreviation
    parts = [part.strip() for part in SENTENCE_BOUNDARY.split(text) if part.strip()]
    return [
        _restore_placeholders(part, placeholders)
        for part in parts
    ]


def _restore_placeholders(text: str, placeholders: dict[str, str]) -> str:
    for placeholder, abbreviation in placeholders.items():
        text = text.replace(placeholder, abbreviation)
    return text


def parse_transcript(path: Path) -> list[ParsedSlide]:
    slides: list[ParsedSlide] = []
    number: int | None = None
    title = ""
    paragraphs: list[str] = []

    def flush() -> None:
        nonlocal paragraphs
        if number is None:
            return
        sentences: list[ParsedSentence] = []
        for paragraph_index, paragraph in enumerate(paragraphs, 1):
            sentences.extend(
                ParsedSentence(paragraph=paragraph_index, text=text)
                for text in split_sentences(paragraph)
            )
        if not sentences:
            raise ValueError(f"Slide {number} has no narration")
        slides.append(ParsedSlide(number=number, title=title, sentences=sentences))
        paragraphs = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = SLIDE_HEADING.match(raw_line)
        if match:
            flush()
            number = int(match.group(1))
            title = match.group(2).strip()
            continue
        line = raw_line.strip()
        if number is not None and line and not line.startswith("Estimated duration:"):
            paragraphs.append(line)
    flush()

    expected = list(range(1, len(slides) + 1))
    actual = [slide.number for slide in slides]
    if actual != expected:
        raise ValueError(f"Transcript slide order mismatch: expected {expected}, got {actual}")
    return slides
