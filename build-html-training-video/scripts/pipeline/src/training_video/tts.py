from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from dotenv import dotenv_values

from .config import build_dir, resolve_from_project
from .models import NarrationPlan, SynthesizedSentence, SynthesisResult
from .normalizer import validate_spoken
from .utils import ffprobe_duration, sha256_bytes, write_json


def _load_key(project_dir: Path, speech) -> str:
    env_path = resolve_from_project(project_dir, speech.env_file)
    values = dotenv_values(env_path) if env_path.is_file() else {}
    key = os.environ.get(speech.key_env) or values.get(speech.key_env)
    if not key or not str(key).strip():
        raise ValueError(f"{speech.key_env} is missing from the environment or configured .env file")
    return str(key).strip()


def _request_audio(text: str, speech, key: str) -> tuple[bytes, str | None]:
    if any(character in key for character in {'"', "\r", "\n"}):
        raise ValueError("The Microsoft Speech key contains unsupported characters")
    endpoint = f"https://{speech.region}.tts.speech.microsoft.com/cognitiveservices/v1"
    ssml = (
        "<speak version='1.0' xml:lang='en-US'>"
        f"<voice name='{html.escape(speech.voice, quote=True)}'>"
        f"<prosody rate='{html.escape(speech.rate, quote=True)}'>{html.escape(text)}</prosody>"
        "</voice></speak>"
    ).encode("utf-8")
    with tempfile.NamedTemporaryFile(suffix=".ssml") as ssml_file, tempfile.NamedTemporaryFile(
        suffix=".headers"
    ) as header_file:
        ssml_file.write(ssml)
        ssml_file.flush()
        curl_config = "\n".join(
            [
                f'url = "{endpoint}"',
                'request = "POST"',
                f'header = "Ocp-Apim-Subscription-Key: {key}"',
                'header = "Content-Type: application/ssml+xml"',
                'header = "Accept: audio/wav"',
                f'header = "X-Microsoft-OutputFormat: {speech.output_format}"',
                'header = "User-Agent: training-video-pipeline"',
                f'data-binary = "@{ssml_file.name}"',
                f'dump-header = "{header_file.name}"',
                "silent",
                "show-error",
                "fail-with-body",
                f"retry = {max(0, speech.retries - 1)}",
                "retry-all-errors",
                "connect-timeout = 15",
                f"max-time = {speech.timeout_seconds}",
            ]
        )
        result = subprocess.run(
            ["curl", "--config", "-"],
            input=curl_config.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        header_file.seek(0)
        response_headers = header_file.read().decode("utf-8", errors="replace")
    if result.returncode != 0:
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Microsoft Speech curl request failed with exit {result.returncode}: {details}")
    payload = result.stdout
    if len(payload) < 44 or not payload.startswith(b"RIFF"):
        raise RuntimeError("Microsoft Speech returned a non-WAV payload")
    request_id = None
    for line in reversed(response_headers.splitlines()):
        name, separator, value = line.partition(":")
        if separator and name.strip().lower() in {
            "x-microsoft-requestid",
            "x-requestid",
            "x-ms-request-id",
            "x-correlationid",
        }:
            request_id = value.strip() or None
            break
    return payload, request_id


def _valid_wave(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 44:
        return False
    try:
        with wave.open(str(path), "rb") as source:
            return source.getnframes() > 0 and source.getframerate() > 0
    except (OSError, EOFError, wave.Error):
        return False


def synthesize_slides(
    project_dir: Path, config, plan: NarrationPlan, slide_numbers: list[int]
) -> SynthesisResult:
    if not plan.approved:
        raise ValueError("narration-plan.json is not approved")
    selected = set(slide_numbers)
    key = _load_key(project_dir, config.speech)
    root = build_dir(project_dir, config)
    cache_dir = root / "cache" / "tts"
    audio_dir = root / "audio" / "sentences"
    cache_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    records: list[SynthesizedSentence] = []
    generated = 0
    cache_hits = 0
    submitted_characters = 0

    for slide in plan.slides:
        if slide.number not in selected:
            continue
        for sentence in slide.sentences:
            validate_spoken(sentence.spoken_text)
            identity = "\n".join(
                [
                    sentence.spoken_text,
                    config.speech.region,
                    config.speech.voice,
                    config.speech.output_format,
                    config.speech.rate,
                ]
            ).encode("utf-8")
            cache_path = cache_dir / f"{sha256_bytes(identity)}.wav"
            cache_metadata_path = cache_path.with_suffix(".json")
            cache_hit = _valid_wave(cache_path)
            request_id = None
            if not cache_hit:
                payload, request_id = _request_audio(sentence.spoken_text, config.speech, key)
                cache_path.write_bytes(payload)
                if not _valid_wave(cache_path):
                    cache_path.unlink(missing_ok=True)
                    raise RuntimeError(f"Generated audio is not a complete WAV for {sentence.id}")
                write_json(cache_metadata_path, {"request_id": request_id})
                generated += 1
                submitted_characters += len(sentence.spoken_text)
            else:
                cache_hits += 1
                if cache_metadata_path.is_file():
                    request_id = json.loads(
                        cache_metadata_path.read_text(encoding="utf-8")
                    ).get("request_id")
            output = audio_dir / f"{sentence.id}.wav"
            shutil.copy2(cache_path, output)
            records.append(
                SynthesizedSentence(
                    id=sentence.id,
                    slide=sentence.slide,
                    characters=len(sentence.spoken_text),
                    duration=ffprobe_duration(output),
                    cache_hit=cache_hit,
                    request_id=request_id,
                    audio_file=str(output),
                )
            )
    result = SynthesisResult(
        region=config.speech.region,
        voice=config.speech.voice,
        output_format=config.speech.output_format,
        requested_sentences=len(records),
        generated_sentences=generated,
        cache_hits=cache_hits,
        submitted_characters=submitted_characters,
        sentences=records,
    )
    write_json(root / "tts-manifest.json", result.model_dump(mode="json"))
    return result
