# Local ASR Models

Put manually downloaded faster-whisper model directories here. Model weights are
large and must stay out of git.

Recommended layout:

```text
models/
  faster-whisper-tiny.en/
  faster-whisper-small.en/
  faster-whisper-medium.en/
```

For the English speaking coach, use the `.en` models first:

- `faster-whisper-tiny.en`: quick smoke test
- `faster-whisper-small.en`: default local development model
- `faster-whisper-medium.en`: better accuracy when GPU latency is acceptable

Each model directory should contain files such as `config.json`, `model.bin`,
`tokenizer.json`, and `vocabulary.txt`.

Example GPU smoke test:

```bash
CUDA_VISIBLE_DEVICES=0 \
ASR_PROVIDER=faster_whisper \
ASR_MODEL_SIZE=/home/scn/xe2/models/faster-whisper-small.en \
ASR_DEVICE=cuda \
ASR_COMPUTE_TYPE=float16 \
python3 scripts/test_asr_provider.py
```
