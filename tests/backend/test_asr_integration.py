import pytest

from backend.app.core.fixtures import load_generated_manifest, resolve_fixture_audio
from backend.app.services.asr import FasterWhisperASR


@pytest.mark.integration
def test_faster_whisper_can_transcribe_librispeech_fixture() -> None:
    pytest.importorskip("faster_whisper")
    item = load_generated_manifest("librispeech")["items"][0]
    audio_path = resolve_fixture_audio(item["audio_file"])

    transcript = FasterWhisperASR(model_size="tiny").transcribe_file(audio_path)

    assert transcript
