from __future__ import annotations

import json
import math
import shutil
import textwrap
import wave
from pathlib import Path

from moviepy import ImageClip

from .config import build_dir
from .models import NarrationPlan, SentenceTiming, SlideTiming, TimingPlan
from .utils import ffprobe_duration, run, sha256_bytes, sha256_file, write_json


def _timestamp(seconds: float, *, srt: bool) -> str:
    millis = max(0, round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    separator = "," if srt else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def _ass_timestamp(seconds: float) -> str:
    centis = max(0, round(seconds * 100))
    hours, remainder = divmod(centis, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _two_lines(text: str, width: int) -> str:
    words = text.split()
    if len(text) <= width:
        return text
    best_index = min(
        range(1, len(words)),
        key=lambda index: abs(len(" ".join(words[:index])) - len(" ".join(words[index:]))),
    )
    return " ".join(words[:best_index]) + "\\N" + " ".join(words[best_index:])


def _write_silence(output, frames: int) -> None:
    output.writeframes(b"\x00\x00" * frames)


def _escape_ffmetadata(value: str) -> str:
    for character in ("\\", "=", ";", "#"):
        value = value.replace(character, f"\\{character}")
    return value


def _normalize_loudness(source: Path, target: Path) -> None:
    analysis = run(
        [
            "ffmpeg", "-i", str(source), "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
            "-f", "null", "/dev/null",
        ],
        capture=True,
    ).stderr
    start = analysis.rfind("{")
    end = analysis.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("Unable to parse first-pass loudness measurements")
    measured = json.loads(analysis[start : end + 1])
    loudnorm = ":".join(
        [
            "loudnorm=I=-16",
            "TP=-1.5",
            "LRA=11",
            f"measured_I={measured['input_i']}",
            f"measured_TP={measured['input_tp']}",
            f"measured_LRA={measured['input_lra']}",
            f"measured_thresh={measured['input_thresh']}",
            f"offset={measured['target_offset']}",
            "linear=true",
            "print_format=summary",
        ]
    )
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
        "-af", loudnorm, "-ar", "48000", "-ac", "1", str(target),
    ])


def assemble_narration(
    project_dir: Path,
    config,
    plan: NarrationPlan,
    slide_numbers: list[int],
    output_dir: Path,
) -> tuple[Path, TimingPlan]:
    root = build_dir(project_dir, config)
    converted_dir = root / "audio" / "converted"
    output_dir.mkdir(parents=True, exist_ok=True)
    converted_dir.mkdir(parents=True, exist_ok=True)
    selected = [slide for slide in plan.slides if slide.number in set(slide_numbers)]
    if [slide.number for slide in selected] != slide_numbers:
        raise ValueError(
            f"Requested slides must exist and follow deck order: requested={slide_numbers}, "
            f"resolved={[slide.number for slide in selected]}"
        )

    converted: dict[str, Path] = {}
    for slide in selected:
        for sentence in slide.sentences:
            source = root / "audio" / "sentences" / f"{sentence.id}.wav"
            if not source.is_file():
                raise FileNotFoundError(f"Missing sentence audio: {source}")
            target = converted_dir / f"{sentence.id}.wav"
            source_identity = {
                "sha256": sha256_file(source),
                "sample_rate": 48_000,
                "channels": 1,
                "codec": "pcm_s16le",
            }
            identity_path = target.with_suffix(".json")
            previous_identity = (
                json.loads(identity_path.read_text(encoding="utf-8"))
                if identity_path.is_file()
                else None
            )
            if not target.is_file() or previous_identity != source_identity:
                run([
                    "ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
                    "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(target),
                ])
                write_json(identity_path, source_identity)
            converted[sentence.id] = target

    raw_narration = output_dir / "narration-raw.wav"
    timings: list[SentenceTiming] = []
    slide_timings: list[SlideTiming] = []
    sample_rate = 48_000
    cursor_frames = 0
    with wave.open(str(raw_narration), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        for slide in selected:
            slide_start_frames = cursor_frames
            leading_frames = round(config.pauses.leading * sample_rate)
            _write_silence(output, leading_frames)
            cursor_frames += leading_frames
            for index, sentence in enumerate(slide.sentences):
                path = converted[sentence.id]
                with wave.open(str(path), "rb") as source:
                    frame_count = source.getnframes()
                    frames = source.readframes(frame_count)
                start = cursor_frames / sample_rate
                output.writeframes(frames)
                cursor_frames += frame_count
                end = cursor_frames / sample_rate
                timings.append(
                    SentenceTiming(
                        id=sentence.id,
                        slide=slide.number,
                        start=start,
                        end=end,
                        duration=frame_count / sample_rate,
                        caption_text=sentence.caption_text,
                        audio_file=str(path),
                    )
                )
                if index < len(slide.sentences) - 1:
                    next_sentence = slide.sentences[index + 1]
                    pause = (
                        config.pauses.paragraph
                        if next_sentence.paragraph != sentence.paragraph
                        else config.pauses.sentence
                    )
                    pause_frames = round(pause * sample_rate)
                    _write_silence(output, pause_frames)
                    cursor_frames += pause_frames
            trailing_frames = round(config.pauses.trailing * sample_rate)
            _write_silence(output, trailing_frames)
            cursor_frames += trailing_frames
            slide_start = slide_start_frames / sample_rate
            slide_end = cursor_frames / sample_rate
            slide_timings.append(
                SlideTiming(
                    slide=slide.number,
                    start=slide_start,
                    end=slide_end,
                    duration=slide_end - slide_start,
                )
            )

    narration = output_dir / "narration.wav"
    _normalize_loudness(raw_narration, narration)
    total = ffprobe_duration(narration)
    timing_plan = TimingPlan(
        total_duration=total,
        sentences=timings,
        slides=slide_timings,
    )
    write_json(output_dir / "sentence-timings.json", timing_plan.model_dump(mode="json"))
    _write_captions(output_dir, config, timing_plan)
    _write_chapters(output_dir, selected, timing_plan)
    return narration, timing_plan


def assemble_sample(
    project_dir: Path, config, plan: NarrationPlan, slide_number: int
) -> tuple[Path, TimingPlan]:
    output_dir = build_dir(project_dir, config) / "samples" / f"slide-{slide_number:02d}"
    return assemble_narration(project_dir, config, plan, [slide_number], output_dir)


def _write_chapters(output_dir: Path, slides, timings: TimingPlan) -> None:
    title_by_number = {slide.number: slide.title for slide in slides}
    chapters = [
        {
            "slide": slide.slide,
            "title": title_by_number[slide.slide],
            "start": slide.start,
            "end": slide.end,
        }
        for slide in timings.slides
    ]
    write_json(output_dir / "chapters.json", chapters)
    metadata = [";FFMETADATA1"]
    for chapter in chapters:
        metadata.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={round(chapter['start'] * 1000)}",
                f"END={round(chapter['end'] * 1000)}",
                f"title={_escape_ffmetadata(str(chapter['title']))}",
            ]
        )
    (output_dir / "chapters.ffmetadata").write_text("\n".join(metadata) + "\n", encoding="utf-8")


def _write_captions(sample_dir: Path, config, timings: TimingPlan) -> None:
    srt: list[str] = []
    vtt: list[str] = ["WEBVTT", ""]
    ass_events: list[str] = []
    for index, cue in enumerate(timings.sentences, 1):
        wrapped = textwrap.fill(cue.caption_text, width=config.captions.max_chars_per_line)
        srt.extend([
            str(index),
            f"{_timestamp(cue.start, srt=True)} --> {_timestamp(cue.end, srt=True)}",
            wrapped,
            "",
        ])
        vtt.extend([
            f"{_timestamp(cue.start, srt=False)} --> {_timestamp(cue.end, srt=False)}",
            wrapped,
            "",
        ])
        ass_text = _two_lines(cue.caption_text, config.captions.max_chars_per_line)
        ass_text = ass_text.replace("{", r"\{").replace("}", r"\}")
        ass_events.append(
            f"Dialogue: 0,{_ass_timestamp(cue.start)},{_ass_timestamp(cue.end)},Default,,0,0,0,,{ass_text}"
        )
    (sample_dir / "captions.srt").write_text("\n".join(srt), encoding="utf-8")
    (sample_dir / "captions.vtt").write_text("\n".join(vtt), encoding="utf-8")
    ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {config.video.width}
PlayResY: {config.video.height}
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{config.captions.font},{config.captions.font_size},&H00FFFFFF,&H000000FF,&H80000000,&HC8000000,0,0,0,0,100,100,0,0,3,1,0,2,{config.captions.margin_horizontal},{config.captions.margin_horizontal},{config.captions.margin_vertical},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
""" + "\n".join(ass_events) + "\n"
    (sample_dir / "captions.ass").write_text(ass, encoding="utf-8")


def artifact_directory(root: Path, slide_numbers: list[int], total_slides: int) -> Path:
    if slide_numbers == list(range(1, total_slides + 1)):
        return root / "full"
    if len(slide_numbers) == 1:
        return root / "samples" / f"slide-{slide_numbers[0]:02d}"
    label = "-".join(f"{number:02d}" for number in slide_numbers)
    return root / "samples" / f"slides-{label}"


def _focus_filters(root: Path, config, timings: TimingPlan, slide_number: int) -> list[str]:
    layout_path = root / "slides" / "layout.json"
    if not layout_path.is_file():
        return []
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    slide_layout = layout.get(str(slide_number), {}).get("selectors", {})
    slide_timing = next(slide for slide in timings.slides if slide.slide == slide_number)
    slide_sentences = [sentence for sentence in timings.sentences if sentence.slide == slide_number]
    filters: list[str] = []
    for cue in config.focus_cues:
        if cue.slide != slide_number:
            continue
        box = slide_layout.get(cue.selector)
        if not box:
            raise ValueError(f"Missing captured layout for slide {slide_number}: {cue.selector}")
        if cue.start_sentence < 1 or cue.start_sentence > len(slide_sentences):
            raise ValueError(f"Invalid focus start sentence on slide {slide_number}: {cue.start_sentence}")
        end_order = cue.end_sentence or len(slide_sentences)
        if end_order < cue.start_sentence or end_order > len(slide_sentences):
            raise ValueError(f"Invalid focus end sentence on slide {slide_number}: {end_order}")
        start = slide_sentences[cue.start_sentence - 1].start - slide_timing.start
        end = slide_sentences[end_order - 1].end - slide_timing.start
        x = max(0, round(box["x"]))
        y = max(0, round(box["y"]))
        width = min(config.video.width - x, round(box["width"]))
        height = min(config.video.height - y, round(box["height"]))
        filters.append(
            f"drawbox=x={x}:y={y}:w={width}:h={height}:color=0x36AD7B@0.75:t=4:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
    return filters


def _render_segment(
    root: Path, config, timings: TimingPlan, slide_number: int
) -> tuple[Path, dict[str, object]]:
    segment_dir = root / "segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    screenshot = root / "slides" / f"{slide_number:02d}.png"
    if not screenshot.is_file():
        raise FileNotFoundError(f"Missing captured slide: {screenshot}")
    slide_timing = next(slide for slide in timings.slides if slide.slide == slide_number)
    moviepy_scene = ImageClip(str(screenshot)).with_duration(slide_timing.duration)
    planned_size = list(moviepy_scene.size)
    planned_duration = float(moviepy_scene.duration)
    moviepy_scene.close()
    if planned_size != [config.video.width, config.video.height]:
        raise ValueError(
            f"MoviePy scene size mismatch for slide {slide_number}: {planned_size}"
        )
    focus_filters = _focus_filters(root, config, timings, slide_number)
    transition = min(config.video.transition_seconds, slide_timing.duration / 2)
    identity = {
        "screenshot_sha256": sha256_file(screenshot),
        "duration": round(slide_timing.duration, 6),
        "width": config.video.width,
        "height": config.video.height,
        "fps": config.video.fps,
        "codec": config.video.codec,
        "preset": config.video.preset,
        "crf": config.video.crf,
        "motion": "ffmpeg-center-zoom-1.0-to-1.012",
        "moviepy_scene": {"size": planned_size, "duration": planned_duration},
        "focus_filters": focus_filters,
        "transition_seconds": transition,
    }
    identity_hash = sha256_bytes(json.dumps(identity, sort_keys=True).encode("utf-8"))[:16]
    segment = segment_dir / f"slide-{slide_number:02d}-{identity_hash}.mp4"
    frames = math.ceil(slide_timing.duration * config.video.fps)
    if not segment.is_file():
        zoom_increment = 0.012 / max(frames, 1)
        transition_filters = []
        if transition > 0:
            transition_filters = [
                f"fade=t=in:st=0:d={transition:.3f}",
                f"fade=t=out:st={max(0.0, slide_timing.duration - transition):.3f}:d={transition:.3f}",
            ]
        filters = [
            f"scale={config.video.width * 2}:{config.video.height * 2}:flags=lanczos",
            (
                "zoompan="
                f"z='min(zoom+{zoom_increment:.10f},1.012)':"
                "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d=1:s={config.video.width}x{config.video.height}:fps={config.video.fps}"
            ),
            *focus_filters,
            *transition_filters,
            "format=yuv420p",
        ]
        run([
            "ffmpeg", "-y", "-loglevel", "error", "-loop", "1",
            "-framerate", str(config.video.fps), "-i", str(screenshot),
            "-vf", ",".join(filters), "-frames:v", str(frames), "-an",
            "-c:v", config.video.codec, "-preset", config.video.preset,
            "-crf", str(config.video.crf), "-pix_fmt", "yuv420p", str(segment),
        ])
    return segment, {
        "slide": slide_number,
        "start": slide_timing.start,
        "end": slide_timing.end,
        "duration": slide_timing.duration,
        "frames": frames,
        "segment": str(segment),
        "identity": identity,
    }


def render_selection(
    project_dir: Path,
    config,
    plan: NarrationPlan,
    slide_numbers: list[int],
    narration: Path,
    timings: TimingPlan,
    artifact_dir: Path,
) -> tuple[Path, Path]:
    root = build_dir(project_dir, config)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    scenes: list[dict[str, object]] = []
    for slide_number in slide_numbers:
        segment, scene = _render_segment(root, config, timings, slide_number)
        segments.append(segment)
        scenes.append(scene)
    write_json(artifact_dir / "scene-plan.json", {"slides": scenes})

    concat_path = artifact_dir / "segments.txt"
    concat_path.write_text(
        "\n".join(f"file '{str(segment.resolve()).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'" for segment in segments)
        + "\n",
        encoding="utf-8",
    )
    video_only = artifact_dir / "video-only.mp4"
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", str(concat_path), "-c", "copy", str(video_only),
    ])

    clean = artifact_dir / "video-clean.mp4"
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(video_only),
        "-i", str(narration), "-i", str(artifact_dir / "chapters.ffmetadata"),
        "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "2",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-movflags", "+faststart", str(clean),
    ])
    captioned = artifact_dir / "video-captioned.mp4"
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", clean.name,
        "-vf", "ass=captions.ass", "-c:v", config.video.codec,
        "-preset", config.video.preset, "-crf", str(config.video.crf),
        "-c:a", "copy", "-map_metadata", "0", "-movflags", "+faststart",
        captioned.name,
    ], cwd=artifact_dir)

    thumbnail_dir = artifact_dir / "thumbnails"
    thumbnail_dir.mkdir(exist_ok=True)
    for index, slide_number in enumerate(slide_numbers):
        source = root / "slides" / f"{slide_number:02d}.png"
        shutil.copy2(source, thumbnail_dir / f"slide-{slide_number:02d}.png")
        if index == 0:
            shutil.copy2(source, thumbnail_dir / "cover.png")
    return clean, captioned
