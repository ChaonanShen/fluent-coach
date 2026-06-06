# 脚本索引

除非特别说明，脚本都从项目根目录运行。需要导入后端代码的脚本通过
`scripts/_bootstrap.py` 支持直接执行。

## 日常开发与检查

- `check_fixtures.py`：检查 generated fixtures 和 fixture 音频是否存在。`make test` 与 `make dev-backend` 会自动调用。
  ```bash
  python3 scripts/check_fixtures.py
  ```
- `run_smoke_report.py`：生成离线或真实 provider smoke report，输出到 `reports/`。
  ```bash
  python3 scripts/run_smoke_report.py
  python3 scripts/run_smoke_report.py --mode real
  ```
- `run_eval.py`：运行 fixture-backed evaluation harness，输出 `reports/latest.json` 和 `reports/latest.md`。
  ```bash
  python3 scripts/run_eval.py
  ```
- `chat_session.py`：命令行文字对话客户端，用来在没有浏览器和麦克风时快速测试一个场景。需要后端已启动。
  ```bash
  python3 scripts/chat_session.py
  python3 scripts/chat_session.py --scenario meeting --base-url http://127.0.0.1:8000
  ```

## Bench 与 Dashboard

- `run_conversation_bench.py`：运行后端多轮 WebSocket bench，生成 JSON/Markdown 报告。
  ```bash
  python3 scripts/run_conversation_bench.py --scenario interview --turns 10
  python3 scripts/run_conversation_bench.py --mode real --audio-file /path/to/audio.wav
  ```
- `bench_dashboard.py`：启动只读 bench dashboard，默认读取 `reports/runs/`。
  ```bash
  python3 scripts/bench_dashboard.py
  BENCH_DASHBOARD_PORT=8101 python3 scripts/bench_dashboard.py
  ```

## Fixture 维护

- `extract_fixtures.py`：把仓库里的 `fixture-subset.zip` 解压回 `fixtures/generated/` 和 `fixtures/audio/public/`。
  ```bash
  python3 scripts/extract_fixtures.py
  ```
- `prepare_fixtures.py`：维护者脚本，从 `dataset/` 下的原始数据集重新抽取小样本 fixtures。
  ```bash
  python3 scripts/prepare_fixtures.py --bundle-zip fixture-subset.zip
  ```

## Provider Smoke Test

- `test_asr_provider.py`：用 fixture 音频检查 fake 或 faster-whisper ASR。
  ```bash
  python3 scripts/test_asr_provider.py --provider fake
  ASR_PROVIDER=faster_whisper ASR_MODEL_SIZE=/path/to/model python3 scripts/test_asr_provider.py
  ```
- `test_kokoro_tts.py`：生成一段 Kokoro TTS 音频，供人工听感检查。
  ```bash
  TTS_PROVIDER=kokoro KOKORO_MODEL_DIR=/path/to/Kokoro-82M python3 scripts/test_kokoro_tts.py --output /tmp/kokoro-smoke.wav
  ```
- `test_tencent_soe.py`：后端集成路径的腾讯云 SOE 发音评测 smoke test，默认读取 `.env`。
  ```bash
  python3 scripts/test_tencent_soe.py
  python3 scripts/test_tencent_soe.py --handshake-only --verbose-safe
  ```
- `tencent_soe_standalone_test.py`：不导入后端代码的腾讯云 SOE 原始 WebSocket 诊断脚本。
  ```bash
  python3 scripts/tencent_soe_standalone_test.py --mode handshake
  python3 scripts/tencent_soe_standalone_test.py --mode recorded --verbose-safe
  ```

## 内部辅助

- `_bootstrap.py`：给直接执行的脚本设置项目导入路径。内部辅助文件，不直接运行。
