import pytest

from training_video import prepare


@pytest.mark.parametrize("system", ["Darwin", "Linux"])
def test_supported_platforms_do_not_require_a_specific_architecture(monkeypatch, system):
    monkeypatch.setattr(prepare.platform, "system", lambda: system)
    monkeypatch.setattr(prepare.platform, "machine", lambda: "test-architecture")

    prepare.validate_supported_platform()


def test_unsupported_platform_is_rejected(monkeypatch):
    monkeypatch.setattr(prepare.platform, "system", lambda: "Windows")
    monkeypatch.setattr(prepare.platform, "machine", lambda: "AMD64")

    with pytest.raises(RuntimeError, match="supports macOS and Linux"):
        prepare.validate_supported_platform()
