# Smoke Report

Generated at: `2026-06-07T09:38:26.751141+00:00`
Mode: `fixture_fake`
External services used: `false`

## Checks

- ASR: passed (fake)
- ASR L2-ARCTIC: passed (fake), avg WER 0.0000, count 5
- Grammar: passed
- Pronunciation: passed (mock)
- Dialogue fixture: passed
- Text streaming: passed
- Known info session: passed
- UI manual: not_run

## Latency

- end_turn -> asr.final: not measured
- asr.final -> reply.done: not measured
- reply.done -> tts_start: not measured
- pronunciation upload -> result: not measured

## Manual UI Checklist

- Start a session from the browser UI.
- Fill Scenario Briefing, collapse it, and confirm the context-aware opening line appears.
- Send one text turn and confirm user.final plus reply.delta/reply.done appear.
- Record one voice turn and confirm asr.final plus reply.delta/reply.done appear.
- Record Read Aloud and confirm pronunciation score appears.
- End the session and confirm summary renders.

Default smoke report uses fixtures and fake/mock providers only.
