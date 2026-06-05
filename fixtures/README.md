# Fixture Data

This directory contains small text fixtures for the AI English speaking coach demo.
The generated audio/data subsets are produced from raw public datasets by:

```bash
python scripts/prepare_fixtures.py
```

On Windows, run the same command from PowerShell or CMD:

```powershell
py scripts\prepare_fixtures.py --bundle-zip fixture-subset.zip
```

Raw datasets should be placed under `dataset/`, which is ignored by git. The
script can be created and run before all downloads are complete; missing datasets
are reported and skipped.

Generated outputs:

- `fixtures/generated/librispeech_subset.json`: ASR baseline manifest.
- `fixtures/generated/speechocean762_subset.json`: pronunciation scoring manifest.
- `fixtures/generated/l2_arctic_subset.json`: L2 English ASR/mispronunciation manifest.
- `fixtures/generated/jfleg_subset.json`: grammar/expression correction manifest.
- `fixtures/audio/public/`: copied or converted subset audio.
- `fixture-subset.zip`: optional upload bundle when `--bundle-zip` is used.

Existing hand-written text fixtures are retained for backend smoke tests and
front-end demo flows:

- `scenarios.json`: scenario configuration text for interview, restaurant ordering, and meeting practice.
- `grammar_expression_errors.json`: 20 grammar/expression correction cases.
- `dialogue_samples.json`: 10 scenario dialogue examples across the three scenarios.
- `asr_smoke_transcripts.json`: 8 short manual transcripts for optional ASR smoke-test recordings.
- `pronunciation_reading_prompts.json`: 10 read-aloud reference sentences for optional pronunciation assessment recordings.
