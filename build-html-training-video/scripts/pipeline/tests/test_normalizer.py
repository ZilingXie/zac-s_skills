import pytest

from training_video.normalizer import normalize_spoken, validate_spoken


MAPPINGS = {
    "rtc.video.vte_freeze_detect_threshold": "R T C dot video dot V T E freeze detect threshold",
    "CSD": "C S D",
}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("3.5 hours", "three point five hours"),
        ("CSD-78679", "C S D seven eight six seven nine"),
        ("4,187 kbps", "four thousand one hundred and eighty seven kbps"),
        ("30 fps", "thirty fps"),
        (
            "rtc.video.vte_freeze_detect_threshold",
            "R T C dot video dot V T E freeze detect threshold",
        ),
        ("8 → 15", "eight to fifteen"),
    ],
)
def test_normalize_spoken(source, expected):
    assert normalize_spoken(source, MAPPINGS) == expected


@pytest.mark.parametrize("value", ["three.5 hours", "CSD-78679", "rtc.video_vte"])
def test_rejects_raw_technical_notation(value):
    with pytest.raises(ValueError):
        validate_spoken(value)

