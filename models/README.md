# Local Models

Put manually downloaded local model files here. Model weights are large and must
stay out of git.

Recommended layout:

```text
models/
  asr/
    faster-whisper-tiny.en/
    faster-whisper-small.en/
    faster-whisper-medium.en/
  tts/
    piper/
      en_US-lessac-medium.onnx
      en_US-lessac-medium.onnx.json
    kokoro/
```

For ASR in the English speaking coach, use the faster-whisper `.en` models first:

- `faster-whisper-tiny.en`: quick smoke test
- `faster-whisper-small.en`: default local development model
- `faster-whisper-medium.en`: better accuracy when GPU latency is acceptable

Each faster-whisper model directory should contain files such as `config.json`, `model.bin`,
`tokenizer.json`, and `vocabulary.txt`.

TTS model directories are reserved for local providers such as Piper or Kokoro.
The exact files depend on the provider.

Example GPU smoke test:

```bash
CUDA_VISIBLE_DEVICES=0 \
ASR_PROVIDER=faster_whisper \
ASR_MODEL_SIZE=/home/scn/fluent-coach/models/asr/faster-whisper-small.en \
ASR_DEVICE=cuda \
ASR_COMPUTE_TYPE=float16 \
python3 scripts/test_asr_provider.py
```
