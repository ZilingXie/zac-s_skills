from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SpeechConfig(StrictModel):
    region: str = "japanwest"
    voice: str = "en-US-AndrewMultilingualNeural"
    output_format: str = "riff-24khz-16bit-mono-pcm"
    rate: str = "+0%"
    env_file: str = "../../../.env"
    key_env: str = "AZURE_SPEECH_KEY"
    timeout_seconds: int = Field(default=45, gt=0)
    retries: int = Field(default=4, ge=1)


class PauseConfig(StrictModel):
    leading: float = Field(default=0.8, ge=0)
    sentence: float = Field(default=0.28, ge=0)
    paragraph: float = Field(default=0.55, ge=0)
    trailing: float = Field(default=0.9, ge=0)


class CaptionConfig(StrictModel):
    font: str = "Arial"
    font_size: int = Field(default=34, gt=0)
    max_chars_per_line: int = Field(default=92, gt=10)
    margin_horizontal: int = Field(default=110, ge=0)
    margin_vertical: int = Field(default=54, ge=0)


class VideoConfig(StrictModel):
    width: int = Field(default=1920, gt=0)
    height: int = Field(default=1080, gt=0)
    fps: int = Field(default=30, gt=0)
    codec: str = "libx264"
    preset: str = "medium"
    crf: int = Field(default=18, ge=0, le=51)
    transition_seconds: float = Field(default=0.15, ge=0)


class CaptureConfig(StrictModel):
    hide_selectors: list[str] = Field(default_factory=list)
    settle_ms: int = Field(default=1000, ge=0)


class FocusCue(StrictModel):
    slide: int = Field(gt=0)
    selector: str
    start_sentence: int = Field(default=1, gt=0)
    end_sentence: int | None = Field(default=None, gt=0)


class ProjectConfig(StrictModel):
    name: str
    deck: str
    transcript: str
    pronunciations: str = "pronunciations.yaml"
    build_dir: str = "../../build/queenlive"
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    pauses: PauseConfig = Field(default_factory=PauseConfig)
    captions: CaptionConfig = Field(default_factory=CaptionConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    focus_cues: list[FocusCue] = Field(default_factory=list)
    golden_dir: str | None = None
    golden_rms_tolerance: float = Field(default=8.0, ge=0)


class SentencePlan(StrictModel):
    id: str
    slide: int
    order: int
    paragraph: int
    source_text: str
    caption_text: str
    spoken_text: str


class SlidePlan(StrictModel):
    id: str
    number: int
    title: str
    sentences: list[SentencePlan]


class NarrationPlan(StrictModel):
    project: str
    approved: bool = False
    slides: list[SlidePlan]

    @field_validator("slides")
    @classmethod
    def slide_numbers_are_sequential(cls, slides: list[SlidePlan]) -> list[SlidePlan]:
        numbers = [slide.number for slide in slides]
        expected = list(range(1, len(slides) + 1))
        if numbers != expected:
            raise ValueError(f"Slide numbers must be sequential: expected {expected}, got {numbers}")
        return slides


class SentenceTiming(StrictModel):
    id: str
    slide: int
    start: float
    end: float
    duration: float
    caption_text: str
    audio_file: str


class SlideTiming(StrictModel):
    slide: int
    start: float
    end: float
    duration: float


class TimingPlan(StrictModel):
    total_duration: float
    sentences: list[SentenceTiming]
    slides: list[SlideTiming]


class SynthesizedSentence(StrictModel):
    id: str
    slide: int
    characters: int
    duration: float
    cache_hit: bool
    request_id: str | None = None
    audio_file: str


class SynthesisResult(StrictModel):
    region: str
    voice: str
    output_format: str
    requested_sentences: int
    generated_sentences: int
    cache_hits: int
    submitted_characters: int
    sentences: list[SynthesizedSentence]
