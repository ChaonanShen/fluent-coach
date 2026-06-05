# Smoke Report

Generated at: `2026-06-05T08:37:47.818484+00:00`
Mode: `fixture_fake`
External services used: `false`

## Checks

- ASR: passed (fake)
- Grammar: passed
- Pronunciation: passed (mock)
- Dialogue fixture: passed
- UI manual: not_run

## Latency

- end_turn -> asr.final: not measured
- asr.final -> reply.text: not measured
- reply.text -> tts_start: not measured
- pronunciation upload -> result: not measured

## Manual UI Checklist

- Start a session from the browser UI.
- Record one voice turn and confirm asr.final plus reply.text appear.
- Record Read Aloud and confirm pronunciation score appears.
- End the session and confirm summary renders.

Default smoke report uses fixtures and fake/mock providers only.
