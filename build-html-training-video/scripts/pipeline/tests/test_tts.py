from types import SimpleNamespace

import pytest

from training_video.tts import _load_key, _request_audio


def test_load_key_rejects_missing_env_file_and_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    speech = SimpleNamespace(env_file=".env", key_env="AZURE_SPEECH_KEY")

    with pytest.raises(ValueError, match="AZURE_SPEECH_KEY is missing"):
        _load_key(tmp_path, speech)


def test_request_audio_rejects_key_characters_before_network_request():
    speech = SimpleNamespace(
        region="japanwest",
        voice="en-US-AndrewMultilingualNeural",
        rate="+0%",
        output_format="riff-24khz-16bit-mono-pcm",
        retries=1,
        timeout_seconds=1,
    )

    with pytest.raises(ValueError, match="unsupported characters"):
        _request_audio("Hello.", speech, 'unsafe"key')
