from types import SimpleNamespace

import pytest
from PIL import Image

from training_video.golden import approve_goldens
from training_video.models import ProjectConfig
from training_video.qa import _golden_checks, _has_unexpected_silence


def test_golden_approval_requires_explicit_confirmation(tmp_path):
    config = ProjectConfig(name="test", deck="deck.html", transcript="transcript.md")
    with pytest.raises(ValueError, match="--confirm"):
        approve_goldens(tmp_path, config, [1], {}, confirmed=False)
    assert not (tmp_path / "golden").exists()


def test_golden_checks_report_unapproved_slides_as_pending(tmp_path):
    golden_dir = tmp_path / "golden"
    captured_dir = tmp_path / "captured"
    golden_dir.mkdir()
    captured_dir.mkdir()
    image = Image.new("RGB", (16, 16), "white")
    image.save(golden_dir / "03.png")
    image.save(captured_dir / "03.png")
    image.save(captured_dir / "04.png")
    config = SimpleNamespace(golden_dir="golden", golden_rms_tolerance=1.0)

    result = _golden_checks(tmp_path, config, [3, 4], captured_dir)

    assert result["status"] == "partial"
    assert result["rms"] == {"3": 0.0}
    assert result["pending_slides"] == [4]


def test_golden_checks_report_all_unapproved_slides_as_pending(tmp_path):
    (tmp_path / "golden").mkdir()
    config = SimpleNamespace(golden_dir="golden", golden_rms_tolerance=1.0)

    result = _golden_checks(tmp_path, config, [4], tmp_path / "captured")

    assert result["status"] == "pending"
    assert result["rms"] == {}
    assert result["pending_slides"] == [4]


def test_silence_across_slide_boundary_is_expected():
    metrics = {
        "two_second_silence_intervals": [
            {"start": 80.89, "end": 83.03, "duration": 2.14}
        ]
    }
    timings = SimpleNamespace(slides=[SimpleNamespace(end=82.13), SimpleNamespace(end=167.97)])

    assert not _has_unexpected_silence(metrics, timings)


def test_silence_away_from_slide_boundary_is_unexpected():
    metrics = {
        "two_second_silence_intervals": [
            {"start": 40.0, "end": 42.1, "duration": 2.1}
        ]
    }
    timings = SimpleNamespace(slides=[SimpleNamespace(end=82.13), SimpleNamespace(end=167.97)])

    assert _has_unexpected_silence(metrics, timings)
