import pytest

from training_video.cli import _parse_slides


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("all", [1, 2, 3, 4]),
        ("3", [3]),
        ("2-4", [2, 3, 4]),
        ("1,3,3", [1, 3]),
        ("1-2,4", [1, 2, 4]),
    ],
)
def test_parse_slides(value, expected):
    assert _parse_slides(value, 4) == expected


@pytest.mark.parametrize("value", ["", "0", "5", "4-2"])
def test_parse_slides_rejects_invalid_selection(value):
    with pytest.raises(ValueError):
        _parse_slides(value, 4)
