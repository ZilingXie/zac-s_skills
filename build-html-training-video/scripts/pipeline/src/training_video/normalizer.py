from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml
from num2words import num2words


ALLOWED_SPOKEN = re.compile(r"^[A-Za-z .,!?;:'\"()]+$")
FORBIDDEN_TECHNICAL = re.compile(r"[0-9_\-/\\=<>@#$%^&*+\[\]{}|~`]")
IDENTIFIER = re.compile(r"\b(CSD|UID|SID)\s*-?\s*(\d+)\b", re.IGNORECASE)
TIME_VALUE = re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b")
DECIMAL = re.compile(r"\b(\d+)\.(\d+)\b")
INTEGER = re.compile(r"\b\d+\b")
UPPERCASE_TOKEN = re.compile(r"\b[A-Z]{2,}\b")


def load_pronunciations(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mappings = payload.get("mappings", payload)
    if not isinstance(mappings, dict):
        raise ValueError(f"Pronunciations must be a mapping: {path}")
    return {str(key): str(value) for key, value in mappings.items()}


def _digits(value: str) -> str:
    return " ".join(num2words(int(char), lang="en") for char in value)


def _integer(value: str) -> str:
    return str(num2words(int(value), lang="en")).replace("-", " ").replace(",", "")


def _decimal(match: re.Match[str]) -> str:
    return f"{_integer(match.group(1))} point {_digits(match.group(2))}"


def _time(match: re.Match[str]) -> str:
    parts = [_integer(match.group(1)), _integer(match.group(2))]
    if match.group(3) is not None:
        parts.append(_integer(match.group(3)))
    return " ".join(parts)


def _identifier(match: re.Match[str]) -> str:
    prefix = " ".join(match.group(1).upper())
    return f"{prefix} {_digits(match.group(2))}"


def _acronym(match: re.Match[str]) -> str:
    return " ".join(match.group(0))


def normalize_spoken(source: str, mappings: dict[str, str]) -> str:
    text = unicodedata.normalize("NFKC", source)
    text = text.replace("`", "").replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2014", " ")

    text = IDENTIFIER.sub(_identifier, text)

    for original in sorted(mappings, key=len, reverse=True):
        text = text.replace(original, mappings[original])

    text = TIME_VALUE.sub(_time, text)
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = DECIMAL.sub(_decimal, text)
    text = INTEGER.sub(lambda match: _integer(match.group(0)), text)
    text = UPPERCASE_TOKEN.sub(_acronym, text)
    text = text.replace("/", " ").replace("_", " ").replace("=", " equals ")
    text = text.replace("\u2192", " to ").replace("-", " ")
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    validate_spoken(text)
    return text


def validate_spoken(text: str) -> None:
    if not text:
        raise ValueError("spoken_text is empty")
    if FORBIDDEN_TECHNICAL.search(text):
        raise ValueError(f"spoken_text contains a digit or technical symbol: {text!r}")
    if not ALLOWED_SPOKEN.fullmatch(text):
        invalid = sorted({char for char in text if not re.match(r"[A-Za-z .,!?;:'\"()]", char)})
        raise ValueError(f"spoken_text contains non-English text or unsupported characters {invalid}: {text!r}")


def caption_text(source: str) -> str:
    return " ".join(source.replace("`", "").split())
