# Fixture Data

This directory contains small fixtures for the AI English speaking coach demo.
The public audio/text test subsets are restored from `fixture-subset.zip` by:

```bash
python scripts/extract_fixtures.py
```

The subset bundle is generated locally, not on the cloud server, from raw public
datasets by:

```bash
python scripts/prepare_fixtures.py
```

On Windows, run the prepare command from PowerShell or CMD:

```powershell
py scripts\prepare_fixtures.py --bundle-zip fixture-subset.zip
```

Raw datasets should be placed under `dataset/`, which is ignored by git and is
not needed on the cloud server. The cloud/server workflow should use
`scripts/extract_fixtures.py` and the tracked `fixture-subset.zip`.

Generated outputs:

- `fixtures/generated/librispeech_subset.json`: ASR baseline manifest.
- `fixtures/generated/speechocean762_subset.json`: pronunciation scoring manifest.
- `fixtures/generated/l2_arctic_subset.json`: L2 English ASR/mispronunciation manifest.
- `fixtures/generated/jfleg_subset.json`: grammar/expression correction manifest.
- `fixtures/audio/public/`: copied or converted subset audio.
- `fixture-subset.zip`: tracked upload bundle with the selected subset.

Existing hand-written text fixtures are retained for backend smoke tests and
front-end demo flows:

- `scenarios.json`: scenario configuration text for interview, restaurant ordering, and meeting practice.
- `grammar_expression_errors.json`: 20 grammar/expression correction cases.
- `dialogue_samples.json`: 10 scenario dialogue examples across the three scenarios.

The old manual-recording placeholders were removed because the ASR and
pronunciation tests now use the public dataset manifests under
`fixtures/generated/`.
