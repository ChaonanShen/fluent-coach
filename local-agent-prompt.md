# Prompt for Local Dataset Agent

You are working on a Windows machine. Your task is to prepare small uploadable fixture subsets for the AI English speaking coach project. Do not upload full raw datasets to the cloud server. Extract local subsets and bundle only the generated fixture files.

## Goal

Run `scripts\prepare_fixtures.py` locally after the user downloads these raw datasets:

- LibriSpeech: `dev-clean.tar.gz` and `test-clean.tar.gz`
- SpeechOcean762: OpenSLR 101 archive
- L2-ARCTIC: official corpus archive or extracted speaker folders
- JFLEG: GitHub repository or zip archive

The script should generate:

- `fixtures\generated\librispeech_subset.json`
- `fixtures\generated\speechocean762_subset.json`
- `fixtures\generated\l2_arctic_subset.json`
- `fixtures\generated\jfleg_subset.json`
- `fixtures\generated\dataset_subset_summary.json`
- `fixtures\audio\public\...`
- `fixture-subset.zip`

Only `fixture-subset.zip` needs to be uploaded to the server.

## Expected Directory Layout

Put all raw datasets under the project-local `dataset\` directory. Example:

```text
project-root\
  dataset\
    dev-clean.tar.gz
    test-clean.tar.gz
    SpeechOcean762.tar.gz
    L2-ARCTIC.zip
    jfleg-main.zip
  scripts\
    prepare_fixtures.py
  fixtures\
```

The raw `dataset\` directory is ignored by git and should not be uploaded.

## Commands

From the project root, run:

```powershell
py scripts\prepare_fixtures.py --bundle-zip fixture-subset.zip
```

If Python launcher `py` is unavailable, run:

```powershell
python scripts\prepare_fixtures.py --bundle-zip fixture-subset.zip
```

If ffmpeg is installed and available in PATH, optionally normalize audio to 16 kHz mono WAV:

```powershell
py scripts\prepare_fixtures.py --convert-wav --bundle-zip fixture-subset.zip
```

If extraction was already done and you only want to rescan existing extracted files:

```powershell
py scripts\prepare_fixtures.py --skip-extract --bundle-zip fixture-subset.zip
```

## What the Script Does

- It safely extracts recognized archives into `dataset\extracted\...`.
- It samples LibriSpeech dev/test clean audio for ASR WER tests.
- It samples SpeechOcean762 low/medium/high score items for pronunciation scoring tests.
- It samples L2-ARCTIC non-native English items, preferring Mandarin speakers.
- It samples JFLEG dev/test examples for grammar and expression correction tests.
- It copies or converts only the selected audio into `fixtures\audio\public\...`.
- It writes portable JSON manifests under `fixtures\generated\...`.
- It creates `fixture-subset.zip` containing only generated manifests and selected subset audio.

## Success Criteria

Open `fixtures\generated\dataset_subset_summary.json` and check:

```json
{
  "counts": {
    "librispeech": 60,
    "speechocean762": 45,
    "l2_arctic": 45,
    "jfleg": 160
  }
}
```

Exact counts may be lower if a dataset is missing or if the downloaded archive has a different structure. If any dataset count is `0`, inspect `missing_or_empty` and `warnings` in the summary file.

The upload bundle should exist:

```text
fixture-subset.zip
```

Upload this zip to the cloud server and extract it at the project root. It should create/update:

```text
fixtures\generated\
fixtures\audio\public\
```

## Troubleshooting

- If all counts are `0`, confirm the raw archives are under `dataset\`.
- If LibriSpeech is `0`, confirm `dev-clean.tar.gz` or `test-clean.tar.gz` exists and extraction completed.
- If SpeechOcean762 is `0`, confirm the extracted dataset contains `scores.json` and a `WAVE` directory.
- If L2-ARCTIC is `0`, confirm extracted speaker directories contain both `wav` and `transcript` folders.
- If JFLEG is `0`, confirm extracted files include `.src` and `.ref*` files.
- If `--convert-wav` fails, install ffmpeg or rerun without `--convert-wav`.

Do not modify product code. Only prepare datasets and report the final counts plus the path to `fixture-subset.zip`.
