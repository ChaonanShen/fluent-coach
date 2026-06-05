from __future__ import annotations


class FakeASR:
    default_transcript = "I have worked on backend systems for three years."

    def partial(self, expected_text: str | None = None) -> str:
        transcript = expected_text or self.default_transcript
        words = transcript.split()
        return " ".join(words[: min(4, len(words))])

    def transcribe(self, audio_bytes: bytes, expected_text: str | None = None) -> str:
        del audio_bytes
        return expected_text or self.default_transcript


fake_asr = FakeASR()
