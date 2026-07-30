from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from .config import build_dir, resolve_from_project
from .utils import ffprobe_duration, run, sha256_file, write_json


def _audio_metrics(path: Path) -> dict[str, object]:
    volume = run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "/dev/null"],
        capture=True,
    ).stderr
    mean_match = re.search(r"mean_volume:\s+(-?[0-9.]+) dB", volume)
    peak_match = re.search(r"max_volume:\s+(-?[0-9.]+) dB", volume)
    if not mean_match or not peak_match:
        raise RuntimeError("Unable to measure narration volume")
    loudness = run(
        ["ffmpeg", "-i", str(path), "-filter_complex", "ebur128=peak=true", "-f", "null", "/dev/null"],
        capture=True,
    ).stderr
    integrated_matches = re.findall(r"I:\s+(-?[0-9.]+) LUFS", loudness)
    if not integrated_matches:
        raise RuntimeError("Unable to measure integrated narration loudness")
    silence = run(
        [
            "ffmpeg", "-i", str(path), "-af", "silencedetect=noise=-45dB:d=2",
            "-f", "null", "/dev/null",
        ],
        capture=True,
    ).stderr
    silence_starts = [float(value) for value in re.findall(r"silence_start:\s+([0-9.]+)", silence)]
    silence_ends = [
        (float(end), float(duration))
        for end, duration in re.findall(
            r"silence_end:\s+([0-9.]+)\s+\|\s+silence_duration:\s+([0-9.]+)", silence
        )
    ]
    silence_intervals = [
        {"start": start, "end": end, "duration": duration}
        for start, (end, duration) in zip(silence_starts, silence_ends, strict=False)
    ]
    return {
        "mean_db": float(mean_match.group(1)),
        "peak_db": float(peak_match.group(1)),
        "integrated_lufs": float(integrated_matches[-1]),
        "two_second_silence_intervals": silence_intervals,
    }


def _has_unexpected_silence(audio_metrics: dict[str, object], timings) -> bool:
    boundaries = [slide.end for slide in timings.slides[:-1]]
    intervals = audio_metrics["two_second_silence_intervals"]
    return any(
        interval["duration"] > 3.0
        or not any(interval["start"] <= boundary <= interval["end"] for boundary in boundaries)
        for interval in intervals
    )


def _sample_video_frames(captioned: Path, timings, output_dir: Path) -> dict[str, float]:
    output_dir.mkdir(parents=True, exist_ok=True)
    spreads: dict[str, float] = {}
    for slide in timings.slides:
        timestamp = slide.start + min(max(slide.duration / 2, 0.1), max(slide.duration - 0.1, 0.1))
        frame = output_dir / f"slide-{slide.slide:02d}.png"
        run([
            "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{timestamp:.6f}",
            "-i", str(captioned), "-frames:v", "1", str(frame),
        ])
        image = Image.open(frame).convert("RGB")
        spreads[str(slide.slide)] = sum(ImageStat.Stat(image).stddev) / 3
    return spreads


def _caption_visual_diffs(
    clean: Path, captioned: Path, timings, output_dir: Path, frame_height: int
) -> dict[str, float]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cues = timings.sentences
    indexes = sorted({0, len(cues) // 2, len(cues) - 1})
    ratios: dict[str, float] = {}
    for index in indexes:
        cue = cues[index]
        timestamp = (cue.start + cue.end) / 2
        clean_frame = output_dir / f"{cue.id}-clean.png"
        captioned_frame = output_dir / f"{cue.id}-captioned.png"
        for video, frame in ((clean, clean_frame), (captioned, captioned_frame)):
            run([
                "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{timestamp:.6f}",
                "-i", str(video), "-frames:v", "1", str(frame),
            ])
        clean_image = Image.open(clean_frame).convert("RGB")
        captioned_image = Image.open(captioned_frame).convert("RGB")
        crop_top = max(0, frame_height - 220)
        clean_crop = clean_image.crop((0, crop_top, clean_image.width, clean_image.height))
        captioned_crop = captioned_image.crop(
            (0, crop_top, captioned_image.width, captioned_image.height)
        )
        difference = ImageChops.difference(clean_crop, captioned_crop)
        changed = sum(1 for pixel in difference.getdata() if max(pixel) > 35)
        ratios[cue.id] = changed / (difference.width * difference.height)
    return ratios


def _golden_checks(project_dir: Path, config, slide_numbers: list[int], captured_dir: Path) -> dict[str, object]:
    if not config.golden_dir:
        return {"status": "skipped", "reason": "No approved golden_dir configured"}
    golden_dir = resolve_from_project(project_dir, config.golden_dir)
    rms: dict[str, float] = {}
    pending_slides: list[int] = []
    for slide_number in slide_numbers:
        golden_path = golden_dir / f"{slide_number:02d}.png"
        if not golden_path.is_file():
            pending_slides.append(slide_number)
            continue
        current = Image.open(captured_dir / f"{slide_number:02d}.png").convert("RGB")
        golden = Image.open(golden_path).convert("RGB")
        if current.size != golden.size:
            raise ValueError(f"Golden size mismatch for slide {slide_number}")
        stat = ImageStat.Stat(ImageChops.difference(current, golden))
        value = (sum(channel**2 for channel in stat.rms) / len(stat.rms)) ** 0.5
        rms[str(slide_number)] = value
        if value > config.golden_rms_tolerance:
            raise RuntimeError(
                f"Slide {slide_number} differs from its approved golden: RMS {value:.3f}"
            )
    if pending_slides and rms:
        status = "partial"
    elif pending_slides:
        status = "pending"
    else:
        status = "passed"
    return {
        "status": status,
        "rms": rms,
        "pending_slides": pending_slides,
        "tolerance": config.golden_rms_tolerance,
    }


def verify_artifact(
    project_dir: Path,
    config,
    plan,
    slide_numbers: list[int],
    clean: Path,
    captioned: Path,
    narration: Path,
    timings,
    artifact_dir: Path,
) -> tuple[Path, Path]:
    probe = run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(captioned)],
        capture=True,
    )
    metadata = json.loads(probe.stdout)
    video_streams = [stream for stream in metadata["streams"] if stream["codec_type"] == "video"]
    audio_streams = [stream for stream in metadata["streams"] if stream["codec_type"] == "audio"]
    if len(video_streams) != 1 or len(audio_streams) != 1:
        raise RuntimeError("Output must contain exactly one video stream and one narration stream")
    video = video_streams[0]
    audio = audio_streams[0]

    selected_ids = [
        sentence.id
        for slide in plan.slides
        if slide.number in set(slide_numbers)
        for sentence in slide.sentences
    ]
    timing_ids = [sentence.id for sentence in timings.sentences]
    ass_lines = (artifact_dir / "captions.ass").read_text(encoding="utf-8").splitlines()
    ass_events = [line for line in ass_lines if line.startswith("Dialogue:")]
    srt_cues = (artifact_dir / "captions.srt").read_text(encoding="utf-8").count(" --> ")
    audio_metrics = _audio_metrics(narration)
    frame_spreads = _sample_video_frames(captioned, timings, artifact_dir / "qa-frames")
    caption_diffs = _caption_visual_diffs(
        clean,
        captioned,
        timings,
        artifact_dir / "qa-caption-frames",
        config.video.height,
    )
    golden = _golden_checks(
        project_dir, config, slide_numbers, build_dir(project_dir, config) / "slides"
    )

    checks = {
        "video_codec_h264": video["codec_name"] == "h264",
        "audio_codec_aac": audio["codec_name"] == "aac",
        "resolution": (int(video["width"]), int(video["height"]))
        == (config.video.width, config.video.height),
        "fps": video["r_frame_rate"] == f"{config.video.fps}/1",
        "audio_48khz_mono": int(audio["sample_rate"]) == 48_000 and int(audio["channels"]) == 1,
        "duration_matches": abs(ffprobe_duration(captioned) - timings.total_duration) < 0.25,
        "sentence_ids_match": selected_ids == timing_ids,
        "sentence_audio_exists": all(Path(cue.audio_file).is_file() for cue in timings.sentences),
        "timings_ordered": all(
            cue.start < cue.end
            and (index == 0 or timings.sentences[index - 1].end <= cue.start)
            for index, cue in enumerate(timings.sentences)
        ),
        "caption_counts_match": len(ass_events) == len(selected_ids) == srt_cues,
        "captions_max_two_lines": all(event.count(r"\N") <= 1 for event in ass_events),
        "captions_visibly_burned": all(ratio > 0.003 for ratio in caption_diffs.values()),
        "sampled_frames_nonblank": all(spread > 4.0 for spread in frame_spreads.values()),
        "narration_not_clipped": -6.0 <= audio_metrics["peak_db"] <= -0.1,
        "narration_loudness": -16.5 <= audio_metrics["integrated_lufs"] <= -15.5,
        "narration_present": audio_metrics["mean_db"] > -35.0,
        "no_unexpected_silence": not _has_unexpected_silence(audio_metrics, timings),
        "no_background_music_stream": len(audio_streams) == 1,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"Artifact quality checks failed: {failed}")
    report = {
        "status": "passed",
        "checks": checks,
        "audio": audio_metrics,
        "sampled_frame_pixel_spread": frame_spreads,
        "caption_bottom_region_changed_ratio": caption_diffs,
        "golden_comparison": golden,
        "duration_seconds": timings.total_duration,
        "slides": slide_numbers,
        "sentence_count": len(selected_ids),
        "outputs": {
            "clean": {"path": str(clean), "sha256": sha256_file(clean)},
            "captioned": {"path": str(captioned), "sha256": sha256_file(captioned)},
        },
    }
    json_path = artifact_dir / "qa-report.json"
    write_json(json_path, report)
    rows = "\n".join(
        f"<tr><td>{name}</td><td class='pass'>PASS</td></tr>" for name in checks
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{config.name} build report</title>
<style>body{{font:16px system-ui;margin:40px;max-width:1000px;color:#17211b}}table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;border-bottom:1px solid #d8ded9;text-align:left}}.pass{{color:#087443;font-weight:700}}code{{background:#edf1ee;padding:2px 5px}}</style></head>
<body><h1>{config.name} build report</h1><p>Slides: <code>{slide_numbers}</code> · Sentences: <code>{len(selected_ids)}</code> · Duration: <code>{timings.total_duration:.3f}s</code></p>
<table><thead><tr><th>Gate</th><th>Result</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Audio</h2><pre>{json.dumps(audio_metrics, indent=2)}</pre>
<h2>Golden comparison</h2><pre>{json.dumps(golden, indent=2)}</pre></body></html>"""
    html_path = artifact_dir / "qa-report.html"
    html_path.write_text(html, encoding="utf-8")
    return json_path, html_path
