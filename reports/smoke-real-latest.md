# Smoke Report

Generated at: `2026-06-05T08:35:50.614991+00:00`
Mode: `real_provider_smoke`
External services used: `true`

## Providers

- LLM: openai_compatible (deepseek-v4-flash)
- ASR: faster_whisper
- Pronunciation: tencent_soe
- TTS: browser

## Checks

- LLM: passed (openai_compatible)
- ASR: passed (faster_whisper)
- Pronunciation: passed (tencent_soe)
- UI manual: not_run

## Latency

- end_turn -> asr.final: 4656.8 ms
- asr.final -> reply.text: 1234.0 ms
- reply.text -> tts_start: not measured
- pronunciation upload -> result: 1050.7 ms

## Manual UI Checklist

- Open the browser UI and start a scenario session.
- Record one voice turn and confirm asr.final plus reply.text appear.
- Record Read Aloud and confirm a provider-backed pronunciation result appears.
- End the session and confirm summary includes stored grammar/pronunciation results.

Default smoke report uses fixtures and fake/mock providers only.
