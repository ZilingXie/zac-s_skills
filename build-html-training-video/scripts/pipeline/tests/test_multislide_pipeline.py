import json
import math
import struct
import wave

from PIL import Image, ImageDraw

from training_video.media import artifact_directory, assemble_narration, render_selection
from training_video.models import (
    NarrationPlan,
    ProjectConfig,
    SentencePlan,
    SlidePlan,
)
from training_video.utils import run


def _sentence(slide: int, text: str) -> SentencePlan:
    return SentencePlan(
        id=f"{slide:02d}-01",
        slide=slide,
        order=1,
        paragraph=1,
        source_text=text,
        caption_text=text,
        spoken_text=text,
    )


def _tone(path, frequency: float) -> None:
    sample_rate = 24_000
    frame_count = round(0.25 * sample_rate)
    frames = b"".join(
        struct.pack("<h", round(4000 * math.sin(2 * math.pi * frequency * index / sample_rate)))
        for index in range(frame_count)
    )
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(frames)


def test_two_slide_timeline_render_and_chapters(tmp_path):
    project_dir = tmp_path / "project"
    root = project_dir / "build"
    slides_dir = root / "slides"
    audio_dir = root / "audio" / "sentences"
    slides_dir.mkdir(parents=True)
    audio_dir.mkdir(parents=True)
    for number, color in [(1, "#174f3a"), (2, "#294a70")]:
        image = Image.new("RGB", (320, 180), color)
        ImageDraw.Draw(image).text((20, 20), f"Slide {number}", fill="white")
        image.save(slides_dir / f"{number:02d}.png")
        _tone(audio_dir / f"{number:02d}-01.wav", 300 + number * 100)

    config = ProjectConfig.model_validate(
        {
            "name": "two-slide-test",
            "deck": "deck.html",
            "transcript": "transcript.md",
            "build_dir": "build",
            "pauses": {"leading": 0.05, "sentence": 0.05, "paragraph": 0.05, "trailing": 0.05},
            "video": {
                "width": 320,
                "height": 180,
                "fps": 10,
                "codec": "libx264",
                "preset": "ultrafast",
                "crf": 28,
                "transition_seconds": 0.05,
            },
            "captions": {"font_size": 18, "max_chars_per_line": 40},
        }
    )
    plan = NarrationPlan(
        project=config.name,
        approved=True,
        slides=[
            SlidePlan(id="01", number=1, title="First", sentences=[_sentence(1, "First slide.")]),
            SlidePlan(id="02", number=2, title="Second", sentences=[_sentence(2, "Second slide.")]),
        ],
    )
    artifact_dir = artifact_directory(root, [1, 2], 2)
    narration, timings = assemble_narration(project_dir, config, plan, [1, 2], artifact_dir)
    clean, captioned = render_selection(
        project_dir, config, plan, [1, 2], narration, timings, artifact_dir
    )

    assert clean.is_file()
    assert captioned.is_file()
    assert [slide.slide for slide in timings.slides] == [1, 2]
    probe = run(
        ["ffprobe", "-v", "error", "-show_chapters", "-of", "json", str(captioned)],
        capture=True,
    )
    chapters = json.loads(probe.stdout)["chapters"]
    assert [chapter["tags"]["title"] for chapter in chapters] == ["First", "Second"]
