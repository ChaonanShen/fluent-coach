# 自动化测试框架设计

> 本文是独立的测试框架设计文档,与主项目 `plan.md` 解耦,`plan.md` 不受影响。
> 目标:把"手动一句句聊"升级成**无前端、自动多轮**的后端 bench 框架,自动驱动后端、
> **记录每轮全量数据 + 延迟指标**,并通过**独立只读面板**可视化。
> 默认 `make test` 仍全程离线、确定性,真实服务走显式 flag。

## 0. 数据流(一句话理解)

```
虚拟用户台词 / 录音
      │  喂进 WS（真实链路：transcode → ASR → LLM 流式 → 语法 → 腾讯 SOE 发音）
      ▼
ws_driver 每轮采集三类数据  ──►  一份结构化 RunRecord(JSON, 落 reports/runs/<id>.json)
   ① 输入：音频文件路径 + ASR 转写文本
   ② 各家返回：LLM 回复 / 语法纠错 / 腾讯 SOE 发音分(word/phoneme) / 错题 / 错误
   ③ 指标：每段延迟(transcode/ASR/TTFT/ITL/腾讯往返/grammar) + WER + (以后)裁判分
      ▼
独立只读面板(单独 FastAPI app) 读 reports/runs/*.json + 回放音频 → 表格 + 延迟分位图
```

> **要点**:系统已用 SQLite 持久化了 session/turn(含 `audio_path`)以及部分分析结果
> ([storage.py](../backend/app/services/storage.py));当前 `/api/sessions/{id}/analysis` 读的是进程内
> `analysis_store`,适合同一进程 bench driver 二次校准 grammar/pronunciation/errors,不适合跨进程补拉历史分析。
> **唯独"延迟"没落盘**——只在 WS `debug.timing` 事件里飘过。bench 框架的核心价值之一,
> 就是把"音频+评测+延迟"合并成一份可回放、可对比的 RunRecord。

## 1. 总体设计:三个独立部件

### 部件 1 — 虚拟用户(代替"我")
自动"假用户":给它"场景 + AI 上一句",生成下一句用户台词,自动跑几十轮。两通道:
- **文本通道**:`/turns/text`,快,但**非流式**,测不到 TTFT/ITL,仅用于对话/语法正确性。
- **语音通道(时延 bench 主路径)**:用户文字 → 假音频字节 + `expected_text`(离线 FakeASR)
  或 fixture/TTS 真音频(真实档)→ 喂进 `WS /ws/sessions/{id}/audio`,跑通
  transcode + ASR + LLM 流式 + 语法分析,真实档可显式开启腾讯 SOE 发音评测。

关键技巧:虚拟用户可**植入已知错误**(生成带错台词,同时给出正确版本)→ 手里就有 ground truth,
不需裁判也能算"语法纠错抓没抓到"。TTS→ASR 还白送 ASR 的 WER ground truth(TTS 嗓音 ≠ 真人口音,
只是 sanity check,真实口音准确率仍靠 l2_arctic fixture)。

### 部件 2 — 指标采集(对齐现状:复用已有 `debug.timing`,不重新埋点)
WS 回合 [main.py](../backend/app/main.py) 已逐段计时并通过 `{"type":"debug.timing",...}` 吐出。
bench **只采集、不重新埋点**。已在测的段:

| 段 | 已有 timing 键 |
|---|---|
| 音频落盘/转码 | `audio_write_ms`、`audio_transcode_ms`、`audio_total_ms` |
| 本地 ASR | `asr_ms`、`end_turn_to_asr_final_ms` |
| LLM 对话 | 流式时有 `reply_first_delta_ms`(**= TTFT**)、`dialogue_reply_ms`、`end_turn_to_reply_text_ms` |
| 语法纠错 | grammar 段 `debug.timing`(总时长) |
| 发音(腾讯 SOE) | pronunciation 段 `debug.timing` |

唯一缺的时延指标:**ITL(吐字间隔)** —— WS 流式循环只记了首 delta,没记后续节奏。

> 名词:**TTFT**(发完请求到第一个字,决定"AI 多久开始说话");**ITL**(首字后平均每字间隔,决定吐字快慢)。

### 部件 3 — 正确性评测(三档,优先级高→低)
1. **Ground-truth fixture(最强,已有)**:JFLEG GLEU、grammar span 命中、speechocean 真值分相关性、librispeech WER。
2. **合成错误注入(很强,新增)**:虚拟用户植入已知错误 → precision/recall。
3. **LLM 裁判(最弱,仅兜底)**:仅开放维度(自然度/推进目标/啰嗦)。复用 OpenAI-compatible,`.env` 读 `JUDGE_MODEL`;
   裁判须**明显更强 + 盲评 + rubric + 多投票**,且**先用 fixture 标定一致率**再信。
   > 业界对照:DeepEval `ConversationSimulator`、τ-bench(用户模拟器)、MT-Bench(GPT-4 裁判,与人类一致 ~80%)、
   > Speechmatics 五层框架(Layer1 音频基础设施 + P50/P95 延迟)、Coval(CI 回归)。

## 2. 可视化:独立只读面板(已选第 2 档)

**结论:单独一套面板,只共享"数据契约"(RunRecord JSON),不共享 UI 代码。**
理由:测试面板受众是开发/评测者、跟着指标频繁变;产品 UI 给终端用户/评委。两者数据与生命周期都不同,
业界(Langfuse/Braintrust/Confident AI)无一例外把 eval dashboard 与产品分开。**复用发生在数据层,不在视图层。**

实现(零耦合产品):
- **独立 FastAPI app**:`backend/app/testkit/dashboard.py`,**只读** `reports/runs/*.json`,不 import 产品业务逻辑。
  - `GET /` → 静态面板页;`GET /api/runs` → run 列表;`GET /api/runs/{id}` → run 详情 JSON;
    `GET /api/runs/{id}/turns/{i}/audio` → 按 RunRecord 里记录的路径**只读回放音频**。
- **前端**:单个自包含静态页(`dashboard/index.html` + 原生 JS,延迟分位用内联 SVG/轻量图),**无构建步骤**,
  与产品 `frontend/` 完全隔离。
- 启动:`python3 scripts/bench_dashboard.py`(独立进程,与产品 `make dev-backend` 互不影响)。

> 升级路径:若以后要多 run 趋势对比/做成正式 Vite app,数据契约不变,只换视图层即可。

## 3. RunRecord schema(面板与 bench 的共享契约)

```jsonc
{
  "run_id": "20260606-interview-...", "scenario_id": "interview",
  "mode": "offline_fake | real", "generated_at": "...",
  "providers": { "llm": "...", "asr": "...", "pronunciation": "..." },
  "turns": [{
    "index": 0,
    "input":  { "audio_path": ".local/audio/.../x.wav", "asr_text": "...", "expected_text": "..." },
    "outputs":{ "reply_text": "...", "grammar": {...}, "pronunciation": {...}, "errors": [...] },
    "timings_ms": { "audio_transcode_ms": .., "asr_ms": .., "reply_first_delta_ms": .., "reply_itl_ms": ..,
                    "dialogue_reply_ms": .., "grammar_ms": .., "pronunciation_ms": ..,
                    "end_turn_to_reply_text_ms": .. },
    "wer": 0.0
  }],
  "latency_summary": { "<segment>": { "p50":.., "p90":.., "p95":.., "max":.., "mean":.., "count":.. } }
}
```
RunRecord **只写 `reports/runs/`,不进产品 SQLite**(保持解耦)。bench 跑 WS 时仍会创建产品
session/turn,因此默认会进入当前 `APP_DB_PATH`;如需完全隔离,脚本/测试必须在 import app 前设置独立
`APP_DB_PATH`。grammar/pronunciation 可通过同进程 WS 事件或 `GET /api/sessions/{id}/analysis`
并入 RunRecord;音频路径来自 WS 回合保存的 `.local/audio/...`。

## 4. 第一阶段实施计划(时延档 + run 记录 + 只读面板)

### 改动 1(很小的生产改动):WS 流式循环补 ITL
- 在 [main.py 的 `reply.delta` 循环](../backend/app/main.py)里数 delta 个数、记录首/末 delta 时间,算
  `reply_itl_ms = (last_delta_at - first_delta_at) / max(delta_count - 1, 1)`,
  连同 `reply_delta_count`、`reply_total_stream_ms` 塞进 `timings`。其余不动。**本档唯一生产改动。**

### 改动 2(纯新增 testkit / script,零生产侵入)
- `backend/app/testkit/ws_driver.py`:`TestClient(app).websocket_connect(...)` 自动跑 N 轮
  (`start_turn{expected_text}` → 发非空假音频 → `end_turn` → 读 `asr.final`/`reply.done`/`debug.timing`),
  再 `GET /api/sessions/{id}/analysis` 并入 grammar/pronunciation/errors → 组装 RunRecord。
  - 离线确定性:`ASR_PROVIDER=fake`(transcript=expected_text)+ 给 `dialogue_service` 注入 `FakeLLMClient`
    + 使用**不命中** `dialogue_samples` 的固定台词,保证走流式 → TTFT/ITL 等键齐全。
  - `--real`:必须先 `load_dotenv()` 再 import app/provider 单例;音频不能再用假 bytes,需使用 fixture wav
    或后续 TTS 合成真音频,并可显式开启腾讯 SOE。
- `backend/app/testkit/run_store.py`:RunRecord 读写 `reports/runs/<id>.json`。
- `backend/app/testkit/report.py`:跨轮算 p50/p90/p95/max/mean → 填 `latency_summary`,并出 `reports/bench-latest.{json,md}` 汇总。
- `backend/app/testkit/dashboard.py` + `dashboard/index.html`:独立只读面板(见 §2)。
- `scripts/run_conversation_bench.py`:CLI(`--scenario --turns --user --real --output-dir`)→ 跑 bench、写 RunRecord + 汇总。
- `scripts/bench_dashboard.py`:启动只读面板。

### 测试(默认 marker,离线)
- `tests/test_ws_bench_driver.py`:注入 FakeLLMClient+FakeASR 跑 3 轮 → N 条 turn、每轮含
  `reply_first_delta_ms`/`reply_itl_ms`/`dialogue_reply_ms` 等键;RunRecord schema 完整;`report` 出 p50/p90。
- `tests/test_ws_itl.py`:断言流式回合 `timings` 含 `reply_itl_ms` 与 `reply_delta_count`。
- `tests/test_bench_dashboard.py`:用 TestClient 打独立面板 app,放一份 fixture RunRecord → `/api/runs`、`/api/runs/{id}` 正常,音频回放返回正确路径内容。

### 生产代码影响
**只动 `main.py` WS 流式循环一处(ITL 几行)**。dialogue/grammar/llm/storage 都不碰。其余全是新增 `testkit/` 与 script;面板是独立 app,零耦合产品。

### 验证
- `make test` 全绿、离线。
- `python3 scripts/run_conversation_bench.py --scenario interview --turns 10` → `reports/runs/<id>.json` + `reports/bench-latest.md`,离线段 p50/p90 有值。
- `python3 scripts/bench_dashboard.py` → 浏览器看 run 列表、每轮表格(音频回放 + ASR + 回复 + 语法;真实/显式发音档含发音分)+ 延迟分位图。
- `... --turns 10 --real` → 需真实音频输入、`.env`、本地 ASR 模型;TTFT/ITL/ASR/可选腾讯发音段为真实数值。

### 提交节奏(小步直提 master)
① WS ITL(生产)+ 测试 → ② ws_driver + run_store + report + CLI + 测试 → ③ 只读面板 dashboard + 启动脚本 + 测试。

## 5. 第二阶段目标:grammar_tts 全自动 bench

第一阶段已经能自动驱动 WS、记录 RunRecord、展示只读面板。第二阶段要把 bench 从"固定台词/人工音频"
升级为**真正无人值守的语法错误对话 bench**:

```text
AI/模板虚拟用户生成一句自然回复(clean_text)
      │
确定性错误注入器把 clean_text 改成带语法/表达错误的 injected_text
      │        同时产出 ground truth: expected_corrected_text + expected_error_types
      ▼
本地 Kokoro TTS 把 injected_text 合成为音频 bytes
      │
喂给 WS /ws/sessions/{id}/audio
      │
真实链路: 音频落盘/转码 → faster-whisper ASR → 对话 LLM 流式回复 → grammar_service 纠错
      ▼
RunRecord 记录: clean/injected/asr/reply/grammar/timing/grammar 命中率
```

### 明确边界

- **本阶段只测语法/表达错误**。TTS 发音通常标准,不适合制造真实发音错误;发音错误检测单独用
  L2-ARCTIC / SpeechOcean / 真人录音做 pronunciation eval。
- `grammar_tts` 是真实链路 bench,默认应使用真实 ASR、真实对话 LLM、本地/云端 TTS。单测仍用 mock/fake
  provider 保持 `make test` 离线。
- 错误 ground truth 不能靠 LLM 自说自话,必须由**确定性错误注入器**生成,这样才能算 recall/precision。

### 本地 TTS 选型

当前本地模型目录:

```text
models/tts/Kokoro-82M/
  kokoro-v1_0.pth
  voices/af_heart.pt
  config.json
```

第二阶段先接 `TTS_PROVIDER=kokoro`,用 Kokoro 作为服务端本地 TTS。它和 faster-whisper 类似:

```text
faster-whisper: 音频 -> 本地 ASR 模型 -> 文本
kokoro:         文本 -> 本地 TTS 模型 -> wav 音频
```

环境变量建议:

```bash
TTS_PROVIDER=kokoro
KOKORO_MODEL_DIR=/home/scn/xe2/models/tts/Kokoro-82M
KOKORO_VOICE=af_heart
KOKORO_LANG_CODE=a
KOKORO_SAMPLE_RATE=24000
```

### 新增 RunRecord 字段

在现有 `TurnRecord` 上追加可选字段,保持兼容旧 run:

```jsonc
{
  "clean_text": "I have three years of experience.",
  "injected_text": "I has three year experience.",
  "expected_corrected_text": "I have three years of experience.",
  "expected_error_types": ["subject_verb_agreement", "plural_noun"],
  "grammar_metrics": {
    "expected_error_recall": 1.0,
    "corrected_text_match": true,
    "asr_preserved_injected_error": true
  },
  "tts": {
    "provider": "kokoro",
    "voice": "af_heart",
    "mime_type": "audio/wav"
  },
  "timings_ms": {
    "tts_ms": 820.4,
    "audio_transcode_ms": 1.2,
    "asr_ms": 430.0,
    "reply_first_delta_ms": 600.0,
    "reply_itl_ms": 40.0,
    "grammar_ms": 900.0
  }
}
```

### 典型命令

真实全自动语法 bench:

```bash
APP_DB_PATH=/tmp/grammar-tts.sqlite \
APP_AUDIO_DIR=/tmp/grammar-tts-audio \
ASR_PROVIDER=faster_whisper \
ASR_MODEL_SIZE=/home/scn/xe2/models/asr/faster-whisper-small.en \
LLM_PROVIDER=openai_compatible \
TTS_PROVIDER=kokoro \
KOKORO_MODEL_DIR=/home/scn/xe2/models/tts/Kokoro-82M \
python3 scripts/run_conversation_bench.py \
  --mode grammar_tts \
  --scenario interview \
  --turns 10 \
  --output-dir reports
```

查看:

```bash
python3 scripts/bench_dashboard.py
```

### 后续仍单独做的事情

- pronunciation eval: L2-ARCTIC / SpeechOcean / 真人录音 → 腾讯 SOE / pronunciation provider → 真值相关性。
- 面板:多 run 趋势对比、回归基线红线。
- 并发吞吐压测(C 路并发,时延退化)。
- LLM 裁判:仅用于自然度/对话推进等开放维度,且必须先用 fixture 标定。
