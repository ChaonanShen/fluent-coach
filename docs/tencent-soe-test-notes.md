# Tencent Cloud SOE Test Notes

## Purpose

Record the verified Tencent Cloud SOE setup for the pronunciation assessment
provider implementation.

## Verified Environment

Local `.env` uses:

```env
PRON_PROVIDER=tencent_soe
TENCENT_APP_ID=<Tencent Cloud APPID, not UIN>
TENCENT_SECRET_ID=<CAM sub-user SecretId>
TENCENT_SECRET_KEY=<CAM sub-user SecretKey>
TENCENT_SOE_WS_URL=wss://soe.cloud.tencent.com/soe/api
TENCENT_SOE_SERVER_ENGINE_TYPE=16k_en
TENCENT_SOE_EVAL_MODE=1
TENCENT_SOE_SCORE_COEFF=3.0
```

Do not commit real values. The tested key belongs to a CAM sub-user with SOE
permission, not the root account key.

## Smoke Test Script

Script:

```bash
python3 scripts/test_tencent_soe.py
```

Default behavior:

- Reads `.env`.
- Loads `fixtures/generated/speechocean762_subset.json`.
- Selects the first manifest item whose audio file exists.
- Uses the manifest `transcript` as `ref_text`.
- Opens Tencent SOE WebSocket.
- Uploads real fixture audio.
- Waits for `final=1`.
- Prints a compact assessment summary.

Custom fixture:

```bash
python3 scripts/test_tencent_soe.py --item-id speechocean_003060229
```

Custom audio:

```bash
python3 scripts/test_tencent_soe.py \
  --audio path/to/audio.wav \
  --ref-text "your reference sentence"
```

Full raw Tencent result:

```bash
python3 scripts/test_tencent_soe.py --raw-result
```

Credential-only debug remains available:

```bash
python3 scripts/test_tencent_soe.py --handshake-only
```

## Verified Real-Audio Result

Command:

```bash
python3 scripts/test_tencent_soe.py
```

Selected fixture:

```text
fixture_id=speechocean_000010113
audio=fixtures/audio/public/speechocean762_subset/speechocean_000010113.wav
ref_text=THEN HE WENT TO THEME PARK
```

Tencent response summary:

```text
handshake: OK code=0 message=success
result: OK code=0
final=1
SuggestedScore: 64.80406188964844
PronAccuracy: 64.80406188964844
PronFluency: 0.9256572723388672
PronCompletion: 1
lowest_words:
  theme: 31.07
  then: 39.77
  he: 53.46
  to: 79.06
  went: 84.29
Audio assessment test passed.
```

This verifies:

- Tencent Cloud APPID is correct.
- CAM sub-user `SecretId` / `SecretKey` can sign requests.
- SOE service is enabled.
- CAM policy allows SOE access.
- Real WAV audio upload and final assessment response work.

## Implementation Notes

The backend provider should map Tencent's final `result` object into the
internal `PronunciationAssessment` model.

Useful Tencent fields:

- `SuggestedScore`: overall score candidate.
- `PronAccuracy`: pronunciation accuracy.
- `PronFluency`: fluency score.
- `PronCompletion`: completion score.
- `Words`: word-level details.
- `Words[].Word` / `Words[].ReferenceWord`: spoken/reference word.
- `Words[].PronAccuracy`: word-level pronunciation accuracy.
- `Words[].PhoneInfos`: phoneme-level details.

Use 16 kHz, 16-bit, mono WAV for the safest integration path. The verified
fixture file is already `RIFF WAVE PCM, 16 bit, mono 16000 Hz`.

The script uses Tencent SOE's WebSocket endpoint:

```text
wss://soe.cloud.tencent.com/soe/api/<APPID>?...
```

Signing details implemented in the script:

- Query parameters are sorted by key.
- Sign text is `host + path_with_appid + "?" + canonical_query`.
- Signature is `Base64(HMAC-SHA1(secret_key, sign_text))`.
- The signature is URL-encoded in the final request URL.

Keep tests that require real Tencent credentials marked as integration tests
or manual smoke tests. Default CI should keep using the mock provider.
