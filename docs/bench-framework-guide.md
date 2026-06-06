# 自动化 Bench 测试框架使用说明

这份文档解释当前后端自动化测试框架是什么、文件结构怎么分、怎么运行，以及 dashboard 页面里的每个数据是什么意思。

## 一句话理解

这个框架不是产品前端，也不是 `make test` 的普通单元测试页面。它是一个后端 bench 工具，用脚本自动模拟多轮语音 WebSocket 对话，把每轮的输入、ASR、AI 回复、语法分析、错误和延迟指标记录成 JSON，然后用一个只读页面查看这些 run。

数据流是：

```text
固定用户台词 / 真实音频 / grammar_tts 合成音频
  -> scripts/run_conversation_bench.py
  -> backend WS /ws/sessions/{id}/audio
  -> 收集 WS 事件和 debug.timing
  -> reports/runs/<run_id>.json
  -> scripts/bench_dashboard.py 只读展示
```

## 什么时候用它

适合用来回答这些问题：

- 后端语音 WebSocket 链路能不能自动跑多轮。
- 每轮 ASR、AI 回复、语法分析有没有返回。
- TTFT、ITL、ASR、grammar 等延迟大概是多少。
- 改代码后和上一轮 bench 数据相比有没有明显退化。
- 真实 provider 模式下，ASR 或腾讯 SOE 有没有明显失败或超时。
- `grammar_tts` 模式下，系统能不能在无人值守时发现预先注入的语法/表达错误。

不适合把它理解成：

- 不是面向普通用户的产品 UI。
- 不是完整的人类口语能力评分系统。
- 离线模式不代表真实语音质量，因为离线默认用 FakeASR 和假音频。
- 默认 dashboard 没有鉴权，不建议直接暴露公网。

## 相关文件结构

```text
backend/app/testkit/
  models.py              RunRecord / TurnRecord / LatencyStat 数据契约
  scripts_data.py        离线 scripted 固定用户台词
  grammar_cases.py       grammar_tts 的 clean/injected/corrected 真值样例
  grammar_injection.py   把 clean_text 确定性改成带错 injected_text，并计算命中率
  virtual_user.py        模板/LLM 虚拟用户，生成下一句用户台词
  tts_audio.py           调 TTS provider 合成音频 bytes
  ws_driver.py           自动驱动 WebSocket 多轮对话
  report.py              汇总延迟分位数，渲染 Markdown 报告
  run_store.py           读写 reports/runs/<run_id>.json
  dashboard.py           独立只读 FastAPI dashboard app
  dashboard/index.html   dashboard 单文件静态页

scripts/
  run_conversation_bench.py  跑一次 bench，写 RunRecord 和报告
  bench_dashboard.py         启动只读 dashboard

reports/
  runs/<run_id>.json         每次 bench 的完整记录
  bench-latest.json          最近一次 bench 的 JSON 备份
  bench-latest.md            最近一次 bench 的 Markdown 汇总
```

第一阶段只改了一处生产代码：`backend/app/main.py` 的流式回复循环会额外记录
`reply_itl_ms`、`reply_total_stream_ms` 和 `reply_delta_count`。第二阶段新增了
服务端 Kokoro TTS provider，供 `grammar_tts` bench 合成音频；其余 bench 逻辑都在
`testkit` 和 `scripts` 里。

## 最常用的离线流程

离线模式默认不访问真实 LLM、ASR、腾讯云，也不需要浏览器麦克风。

先跑一次 bench：

```bash
python3 scripts/run_conversation_bench.py --scenario interview --turns 10
```

可选场景：

```text
interview
restaurant_ordering
meeting
```

运行完成后会看到类似输出：

```text
wrote /home/scn/xe2/reports/runs/20260606T084445Z-interview-offline_fake.json
wrote /home/scn/xe2/reports/bench-latest.json
wrote /home/scn/xe2/reports/bench-latest.md
reply_first_delta_ms: p50=...
reply_itl_ms: p50=...
grammar_ms: p50=...
```

然后启动 dashboard：

```bash
python3 scripts/bench_dashboard.py
```

浏览器打开：

```text
http://localhost:8100/
```

如果你是在服务器上运行，并且用 SSH 做端口转发，本地电脑执行：

```bash
ssh -L 8100:127.0.0.1:8100 <user>@<server>
```

服务器上仍然只需要：

```bash
python3 scripts/bench_dashboard.py
```

本地浏览器访问：

```text
http://localhost:8100/
```

要跑全自动语法错误真实链路，看下面的 `grammar_tts` 模式。

## 默认输出目录

默认 bench 输出到：

```text
reports/runs/
reports/bench-latest.json
reports/bench-latest.md
```

dashboard 默认读取：

```text
reports/runs/*.json
```

如果你想把某次 bench 输出到临时目录：

```bash
python3 scripts/run_conversation_bench.py \
  --scenario interview \
  --turns 5 \
  --output-dir /tmp/my-bench
```

对应 dashboard 要指定同一个 runs 目录：

```bash
BENCH_RUNS_DIR=/tmp/my-bench/runs python3 scripts/bench_dashboard.py
```

## 端口已经被占用怎么办

如果看到：

```text
ERROR: [Errno 98] error while attempting to bind on address ('127.0.0.1', 8100): address already in use
```

说明 8100 已经有服务在跑，大概率就是 dashboard 已经启动了。

查看占用：

```bash
ss -ltnp | rg ':8100'
```

停止已有 dashboard：

```bash
kill <pid>
```

或者换端口：

```bash
BENCH_DASHBOARD_PORT=8101 python3 scripts/bench_dashboard.py
```

如果你用服务器端口映射、容器端口映射或需要监听外部网卡，可以这样启动：

```bash
BENCH_DASHBOARD_HOST=0.0.0.0 python3 scripts/bench_dashboard.py
```

更推荐 SSH tunnel，因为 dashboard 只读但没有登录鉴权。

## Dashboard 页面怎么看

页面分三块：左侧 Runs，右侧 Summary、Latency、Turns。

### 左侧 Runs

每一行是一次 bench run。

显示内容：

- `run_id`：这次 bench 的唯一 ID，通常包含 UTC 时间、场景和模式。
- `scenario_id`：场景，例如 `interview`。
- `mode`：模式，例如 `offline_fake`、`real` 或 `grammar_tts`。
- `turn_count`：这次 bench 跑了多少轮用户输入。

点击某个 run，右侧会切换到这次 run 的详情。

### Summary

Summary 是这次 run 的总览。

字段含义：

| 字段 | 含义 |
|---|---|
| Run | 当前 run 的 ID |
| Scenario | 场景 ID |
| Mode | bench 模式 |
| Generated | 生成时间 |
| Turns | 总轮数 |
| Providers | 本次记录到的 provider 配置 |
| Median TTFT | `reply_first_delta_ms` 的 p50 |
| Median ITL | `reply_itl_ms` 的 p50 |
| Median TTS | `tts_ms` 的 p50，仅 `grammar_tts` 或服务端 TTS 模式有值 |
| Avg Grammar Recall | 平均命中多少预先注入的错误类型，仅 `grammar_tts` 有值 |
| Corrected Match | grammar 输出的 corrected text 与真值完全一致的比例，仅 `grammar_tts` 有值 |

注意：离线模式的 provider 通常是 fake/mock。真实模式是否真的走真实 provider，要看 `.env` 和启动参数。
`grammar_tts` 默认会拒绝 fake ASR、fake LLM 和 browser fallback TTS，除非你显式传
`--allow-fake-providers`。

### Latency

Latency 展示所有 `*_ms` 延迟指标的分位数。

表格列含义：

| 列 | 含义 |
|---|---|
| Segment | 延迟指标名称 |
| p50 | 中位数，50% 的样本小于等于这个值 |
| p90 | 90% 的样本小于等于这个值 |
| p95 | 95% 的样本小于等于这个值 |
| Max | 最大值 |
| Mean | 平均值 |
| Count | 有这个指标的轮数 |

上方的条形图主要画关键指标的 p95，方便快速看哪个阶段比较慢。

### Turns

Turns 是逐轮明细。每一行是一轮用户说话和 AI 回复。

列含义：

| 列 | 含义 |
|---|---|
| # | 第几轮，从 0 开始 |
| Audio | 本轮保存下来的音频文件，可回放 |
| Input / ASR | 本轮输入文本和 ASR 实际识别文本 |
| Reply | AI 对话回复 |
| Grammar | 语法纠错结果或错误 |
| Pronunciation | 发音评测结果，离线默认为空 |
| Timing | 本轮关键延迟 |

离线模式里：

- `Expected` 是 scripted 固定台词。
- `ASR` 来自 FakeASR，所以通常和 Expected 完全一致。
- `WER` 通常是 `0.0000`。
- `Audio` 是后端保存的假 wav bytes，只用于跑通文件路径和回放链路，不代表真实录音。
- `Pronunciation` 默认为空，因为 mock provider 下普通音频回合默认不跑发音评测。

`grammar_tts` 模式里：

- `Clean` 是虚拟用户本来想说的正确句子。
- `Injected` 是错误注入器改坏后的句子，也是 TTS 实际朗读的文本。
- `Expected` 是 grammar 应该纠正回来的标准答案。
- `ASR` 是真实 ASR 听完 TTS 音频后的转写。
- `WER` 是 ASR 相对 `Injected` 的词错误率，主要用来判断 TTS→ASR 是否把错误保留下来。
- `Grammar` 会显示预期错误类型、实际检测到的问题、expected error recall 和 corrected text 是否匹配。

真实模式里：

- `ASR` 来自真实 ASR。
- `Expected` 当前默认为空，因为真实音频还没有自动绑定 ground truth。
- `WER` 当前通常为空，后续如果给真实音频加 transcript 才能计算。
- `Pronunciation` 只有真实发音 provider 或显式 `PRON_ASSESS_AUDIO_TURNS=1` 时才会出现。

## 每个指标是什么意思

### 音频和 ASR

| 指标 | 含义 |
|---|---|
| `audio_write_ms` | 后端把本轮音频 bytes 写入文件的耗时 |
| `audio_transcode_ms` | ffmpeg 转码到 wav 的耗时。离线 wav 假音频通常接近 0 |
| `audio_total_ms` | 写文件加转码的总耗时 |
| `tts_ms` | 服务端 TTS 从文本合成音频的耗时，主要出现在 `grammar_tts` |
| `asr_ms` | ASR provider 识别音频的耗时 |
| `end_turn_to_asr_final_ms` | 收到 `end_turn` 到发出 `asr.final` 的总耗时 |

### AI 回复

| 指标 | 含义 |
|---|---|
| `reply_first_delta_ms` | TTFT，开始生成回复到第一个 `reply.delta` 的耗时 |
| `reply_itl_ms` | ITL，多个 `reply.delta` 之间的平均间隔 |
| `reply_total_stream_ms` | 流式回复从进入 stream 循环到完成的总耗时 |
| `dialogue_reply_ms` | 对话回复整体耗时 |
| `end_turn_to_reply_text_ms` | 收到 `end_turn` 到完整回复文本可用的总耗时 |
| `reply_delta_count` | 本轮流式 delta 数量，不是毫秒延迟，不进入 Latency 分位汇总 |

TTFT 影响“AI 多久开始出字”。ITL 影响“开始出字之后吐字是否平滑”。如果走非流式 `reply.text`，就不会有 TTFT/ITL。

### 分析阶段

| 指标 | 含义 |
|---|---|
| `grammar_ms` | 语法分析耗时 |
| `pronunciation_ms` | 发音评测耗时 |

语法和发音是旁路异步分析，不阻塞 AI 回复。dashboard 会把它们合并到同一轮里展示。

`grammar_tts` 还会在每轮 `grammar_metrics` 里记录：

| 指标 | 含义 |
|---|---|
| `expected_error_recall` | 预先注入的错误类型里，有多少被 grammar 结果命中 |
| `matched_error_types` | 命中的预期错误类型 |
| `detected_error_types` | grammar 实际返回的问题类型，做过简单别名归一 |
| `corrected_text_match` | grammar 的 corrected text 是否与 `expected_corrected_text` 完全一致 |
| `asr_preserved_injected_error` | ASR 文本是否还保留了注入错误，用来区分 grammar 漏检和 ASR/TTS 抹平错误 |

## RunRecord JSON 怎么看

每次 bench 的完整数据在：

```text
reports/runs/<run_id>.json
```

大致结构：

```json
{
  "run_id": "...",
  "scenario_id": "interview",
  "mode": "offline_fake",
  "generated_at": "...",
  "providers": {
    "llm": "fake",
    "asr": "fake",
    "pronunciation": "mock",
    "tts": "browser"
  },
  "turns": [
    {
      "index": 0,
      "user_text": "...",
      "asr_text": "...",
      "expected_text": "...",
      "clean_text": "...",
      "injected_text": "...",
      "expected_corrected_text": "...",
      "expected_error_types": ["subject_verb_agreement"],
      "audio_path": ".local/audio/...",
      "reply_text": "...",
      "grammar": {},
      "grammar_metrics": {},
      "tts": {},
      "pronunciation": null,
      "errors": [],
      "timings_ms": {},
      "wer": 0.0
    }
  ],
  "latency_summary": {}
}
```

如果 dashboard 看不懂，可以先打开 JSON。JSON 是最完整、最原始的 bench 结果，页面只是把它表格化。

## grammar_tts 全自动语法错误模式怎么跑

这个模式最接近你想要的真实自动测试：

```text
虚拟用户生成 clean_text
  -> 错误注入器改成 injected_text，并保存 expected_corrected_text / expected_error_types
  -> Kokoro 本地 TTS 合成 wav
  -> WebSocket 音频链路
  -> faster-whisper ASR
  -> LLM 流式对话回复
  -> grammar_service 纠错
  -> RunRecord 计算 WER、grammar recall、corrected match
```

先安装本地 TTS 依赖。Kokoro 需要 Python 包和 `espeak-ng`：

```bash
python3 -m pip install -e ".[tts]"
conda install -y -c conda-forge espeak-ng
```

如果不用 conda，也可以在 Linux 系统环境安装 `espeak-ng`：

```bash
sudo apt-get install -y espeak-ng
```

模型目录按现在的项目约定放在：

```text
models/tts/Kokoro-82M/
  kokoro-v1_0.pth
  voices/af_heart.pt
```

可先做一次 TTS smoke test：

```bash
TTS_PROVIDER=kokoro \
KOKORO_MODEL_DIR=/home/scn/xe2/models/tts/Kokoro-82M \
python3 scripts/test_kokoro_tts.py --output /tmp/kokoro-smoke.wav
```

然后跑完整 `grammar_tts` bench：

```bash
APP_DB_PATH=/tmp/grammar-tts.sqlite \
APP_AUDIO_DIR=/tmp/grammar-tts-audio \
ASR_PROVIDER=faster_whisper \
ASR_MODEL_SIZE=/home/scn/xe2/models/asr/faster-whisper-small.en \
LLM_PROVIDER=openai_compatible \
LLM_BASE_URL=... \
LLM_API_KEY=... \
LLM_MODEL=... \
TTS_PROVIDER=kokoro \
KOKORO_MODEL_DIR=/home/scn/xe2/models/tts/Kokoro-82M \
KOKORO_MODEL_PATH=/home/scn/xe2/models/tts/Kokoro-82M/kokoro-v1_0.pth \
KOKORO_VOICE=af_heart \
KOKORO_LANG_CODE=a \
python3 scripts/run_conversation_bench.py \
  --mode grammar_tts \
  --scenario interview \
  --turns 10 \
  --output-dir /tmp/grammar-tts-report
```

`--virtual-user template` 是默认值，使用固定 clean_text，最稳定、最容易对比回归。
如果要让用户回复内容也由 LLM 根据上下文生成，可以加：

```bash
--virtual-user llm
```

但错误注入仍是确定性的，最终真值仍来自 `expected_corrected_text` 和
`expected_error_types`，不是让 LLM 自己裁判自己。

查看结果：

```bash
BENCH_RUNS_DIR=/tmp/grammar-tts-report/runs \
APP_AUDIO_DIR=/tmp/grammar-tts-audio \
python3 scripts/bench_dashboard.py
```

`grammar_tts` 的重点看：

- Summary 里的 `Avg Grammar Recall` 和 `Corrected Match`。
- Turns 里 `Injected`、`ASR`、`Grammar` 是否能对应上。
- `WER` 是否很高。如果 WER 高，说明 ASR 没听准 TTS，grammar 分数要谨慎解释。
- Timing 里的 `tts_ms`、`asr_ms`、`reply_first_delta_ms`、`grammar_ms`。

这个模式不制造发音错误。TTS 声音通常是标准发音，适合测语法/表达纠错；发音错误检测性能应单独用
L2-ARCTIC、SpeechOcean 或真人录音做 pronunciation eval。

## 真实模式怎么跑

真实模式不会用假音频。必须传真实音频文件或目录：

```bash
python3 scripts/run_conversation_bench.py \
  --scenario interview \
  --turns 5 \
  --real \
  --audio-dir fixtures/audio/public/l2_arctic_subset
```

或者指定单个文件：

```bash
python3 scripts/run_conversation_bench.py \
  --scenario interview \
  --turns 3 \
  --real \
  --audio-file fixtures/audio/public/l2_arctic_subset/l2_arctic_ABA_arctic_a0003.wav
```

真实模式会先读取 `.env`，所以 `.env` 中要配置真实 provider，例如：

```bash
ASR_PROVIDER=faster_whisper
ASR_MODEL_SIZE=/home/scn/xe2/models/asr/faster-whisper-small.en
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=...
LLM_API_KEY=...
LLM_MODEL=...
```

如果要采集腾讯 SOE 发音评测：

```bash
PRON_ASSESS_AUDIO_TURNS=1 python3 scripts/run_conversation_bench.py \
  --scenario interview \
  --turns 5 \
  --real \
  --audio-dir fixtures/audio/public/l2_arctic_subset
```

真实模式的常见情况：

- 如果 LLM provider 没有真实流式 client，可能只有 `reply.text`，没有 TTFT/ITL。
- 如果 ASR_PROVIDER 仍是 fake，就不是完整真实 ASR bench。
- 如果音频格式不是 wav，后端会尝试 ffmpeg 转码。
- 如果 ffmpeg 不存在或转码失败，run 里会记录 ASR/analysis error。

## 如何隔离本地数据

bench 会创建产品 session/turn，因此默认可能写入：

```text
.local/speaking_coach.sqlite
.local/audio/
```

如果只想临时跑，不污染默认 `.local`：

```bash
APP_DB_PATH=/tmp/bench.sqlite \
APP_AUDIO_DIR=/tmp/bench-audio \
python3 scripts/run_conversation_bench.py --scenario interview --turns 10 --output-dir /tmp/bench-report
```

再启动 dashboard：

```bash
BENCH_RUNS_DIR=/tmp/bench-report/runs \
APP_AUDIO_DIR=/tmp/bench-audio \
python3 scripts/bench_dashboard.py
```

`APP_AUDIO_DIR` 要保持一致，否则 dashboard 可能找不到音频或出于安全限制拒绝回放。

## 常见问题

### 页面左侧没有 run

原因通常是 dashboard 读取的 `BENCH_RUNS_DIR` 和 bench 输出目录不一致。

检查：

```bash
find reports/runs -maxdepth 1 -type f
```

如果 run 在 `/tmp/my-bench/runs`，要这样启动：

```bash
BENCH_RUNS_DIR=/tmp/my-bench/runs python3 scripts/bench_dashboard.py
```

### 页面里 Pronunciation 为空

离线模式默认就是空的。普通音频回合发音评测默认关闭，避免 `make test` 或离线 bench 访问真实服务。

真实 provider 下要看 `.env` 和：

```bash
PRON_ASSESS_AUDIO_TURNS=1
```

### 没有 TTFT/ITL

TTFT/ITL 只在流式回复路径出现。如果本轮走 `reply.text` 非流式，就没有这些指标。

离线 bench 已经用不命中 fixture 的固定台词和 FakeLLM 流式输出，正常应有 TTFT/ITL。真实模式下要确认 LLM provider 支持 `stream_complete`。

### Audio 播不了

离线模式的音频是 fake wav bytes，某些浏览器可能不能正常播放声音，但路径和回放接口是通的。

真实模式下如果音频路径在 `APP_AUDIO_DIR` 之外，dashboard 会因为安全白名单返回 404。启动 dashboard 时带上同一个 `APP_AUDIO_DIR`。

### `localhost:8100` 打不开

如果 dashboard 在服务器上，浏览器在你本地电脑上，需要 SSH tunnel 或端口映射。

推荐：

```bash
ssh -L 8100:127.0.0.1:8100 <user>@<server>
```

服务器上：

```bash
python3 scripts/bench_dashboard.py
```

本地浏览器：

```text
http://localhost:8100/
```

### `address already in use`

说明 dashboard 已经在跑，或者 8100 被别的进程占用。

查看：

```bash
ss -ltnp | rg ':8100'
```

停止：

```bash
kill <pid>
```

或换端口：

```bash
BENCH_DASHBOARD_PORT=8101 python3 scripts/bench_dashboard.py
```

## 推荐日常流程

每次改后端 WS、ASR、LLM、grammar、TTS 或 pronunciation 相关逻辑后：

```bash
make test
python3 scripts/run_conversation_bench.py --scenario interview --turns 10
python3 scripts/bench_dashboard.py
```

然后看：

- `Latency` 里 `reply_first_delta_ms`、`reply_itl_ms`、`asr_ms`、`grammar_ms` 是否异常升高。
- `Turns` 里每轮是否都有 ASR、Reply、Grammar。
- `errors` 是否为空。
- 如果是真实模式，看 `asr_ms`、`pronunciation_ms` 和错误信息。
- 如果是 `grammar_tts`，看 `Avg Grammar Recall`、`Corrected Match`、`tts_ms` 和 `WER`。

如果只想快速确认 CLI：

```bash
python3 scripts/run_conversation_bench.py --scenario interview --turns 2 --output-dir /tmp/bench-test
BENCH_RUNS_DIR=/tmp/bench-test/runs python3 scripts/bench_dashboard.py
```

如果只想快速确认 `grammar_tts` 参数和报告结构、但还没装真实 TTS/ASR，可以临时加
`--allow-fake-providers`。这个结果只能验证框架结构，不能代表真实测试效果。
