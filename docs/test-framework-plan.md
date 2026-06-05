# 自动化测试框架设计

> 本文是独立的测试框架设计文档,与主项目 `plan.md` 解耦,`plan.md` 不受影响。
> 目标:把"手动一句句聊"升级成**无前端、自动多轮**的后端 bench 框架,直接调用后端
> 对系统做时延 + 正确性测试。默认 `make test` 仍全程离线、确定性,真实服务走显式 flag。
>
> **修订说明(代码现状对齐)**:仓库已落地流式链路(`stream_complete()` / `generate_reply_stream()` /
> WS `reply.delta`),且 WS 回合已逐段计时并通过 `debug.timing` 事件吐出。因此本框架**不再重新埋点**,
> 改为**驱动真实 WS 路径 + 采集它已吐出的时延**;原计划中的 `timing.py`(contextvar)、改 `StructuredJSONCaller`
> 接流式计时等均已删除。

## 1. 总体设计:三个独立部件

### 部件 1 — 虚拟用户(代替"我")
一个自动"假用户",给它"场景 + AI 上一句",它生成下一句用户台词,自动跑几十轮。
两种输入通道:
- **文本通道**:`/turns/text`,快,但**非流式**,测不到 TTFT/ITL,仅用于对话/语法正确性。
- **语音通道(时延 bench 主路径)**:用户文字 → 假音频字节 + `expected_text`(离线 FakeASR)
  或 TTS 合成真音频(真实档)→ 喂进 `WS /ws/sessions/{id}/audio`,跑通
  transcode + faster-whisper + 腾讯 SOE + LLM 流式的完整链路和真实时延。

关键技巧:虚拟用户可**植入已知错误**(生成带错台词,同时给出正确版本),手里就有 ground truth,
不需要裁判模型也能算"语法纠错抓没抓到"。TTS→ASR 这一圈还白送 ASR 的 WER ground truth
(注意 TTS 嗓音 ≠ 真人口音,只是 sanity check,真实口音准确率仍靠 l2_arctic fixture)。

### 部件 2 — 指标采集(对齐现状:复用已有 `debug.timing`)
WS 回合 [main.py](../backend/app/main.py) 已用本地 `timings` dict 逐段计时并通过
`{"type": "debug.timing", ...}` 事件吐出。bench 框架**只采集、不重新埋点**。

WS 已经在测的段:

| 段 | 已有 timing 键 |
|---|---|
| 音频落盘/转码 | `audio_write_ms`、`audio_transcode_ms`、`audio_total_ms` |
| 本地 ASR | `asr_ms`、`end_turn_to_asr_final_ms` |
| LLM 对话 | `reply_first_delta_ms`(**= TTFT,已测**)、`dialogue_reply_ms`、`end_turn_to_reply_text_ms` |
| 语法纠错 | grammar 段 `debug.timing`(总时长) |
| 发音(腾讯 SOE) | pronunciation 段 `debug.timing` |

唯一缺的时延指标:**ITL(吐字间隔)** —— WS 流式循环只记了首 delta,没记后续节奏。

> 名词:**TTFT**(Time To First Token,发完请求到第一个字,决定"AI 多久开始说话");
> **ITL**(Inter-Token Latency,首字之后平均每字间隔,决定吐字快慢)。

### 部件 3 — 正确性评测(三档,优先级高→低)
1. **Ground-truth fixture(最强,已有)**:JFLEG GLEU、grammar_expression_errors span 命中、
   speechocean 真值分相关性、librispeech WER。有标准答案,不需裁判。
2. **合成错误注入(很强,新增)**:虚拟用户植入已知错误 → 算 precision/recall。也是 ground truth。
3. **LLM 裁判(最弱,仅兜底)**:仅用于开放维度(对话自然度、是否推进目标、是否啰嗦说教)。

裁判可信约束(复用 OpenAI-compatible,从 `.env` 读 `JUDGE_MODEL`):
- 裁判必须**明显强于**被测 deepseek,且**盲评**;**rubric + 结构化打分**;**多次/多裁判投票**降方差。
- **先用 fixture 标定裁判**:让它去评有标准答案的那批,看与真值一致率,够高才信它评开放题。

## 2. 代码落点
```
backend/app/testkit/
  ws_driver.py      # 用 TestClient websocket 驱动 /ws/sessions/{id}/audio,自动多轮,采集 debug.timing
  report.py         # p50/p90/p95/max/mean 聚合 + JSON/Markdown
  virtual_user.py   # (后续)persona 生成台词 + 已知错误注入
  judge.py          # (后续)裁判 client + rubric,默认 skip
scripts/run_conversation_bench.py   # CLI 入口
```
铁律:`make test` 默认全 fake/mock、不联网;真实模型/云一律 integration marker 或显式 `--real`。

## 3. 第一阶段:时延档(当前实施)

聚焦时延。因 WS 路径已把每段时延算好并 `debug.timing` 吐出,bench 不重复埋点,
而是**驱动真实 WS 路径 + 采集 + 聚合**。这恰好跑通完整语音链路(ASR + 腾讯 SOE + LLM)。

### 改动 1(很小的生产改动):WS 流式循环补 ITL
- 在 [main.py 的 `reply.delta` 循环](../backend/app/main.py)里数 delta 个数、记总流时长,
  算 `reply_itl_ms = (reply_total_stream_ms - reply_first_delta_ms) / max(deltas - 1, 1)`,
  连同 `reply_delta_count`、`reply_total_stream_ms` 塞进 `timings`。其余不动。
- 这是本档**唯一**的生产代码改动。

### 改动 2(纯新增 testkit,零生产侵入)
- `backend/app/testkit/ws_driver.py`:
  - 用 `fastapi.testclient.TestClient(app).websocket_connect(...)` 连 WS,自动跑 N 轮:
    每轮 `start_turn{expected_text}` → 发非空假音频字节 → `end_turn` → 读到 `reply.done`/`reply.text`,
    并**收集本轮所有 `debug.timing` 的 `timings`**(含 reply / grammar / pronunciation 段)。
  - 台词来源:`scripted` 复用 `dialogue_samples` 的 user 轮(确定性);轮数超出则循环。
  - **离线确定性**:`ASR_PROVIDER=fake` 使 transcript=expected_text;给 `dialogue_service` 注入
    `FakeLLMClient`(并用非 fixture 命中的台词)走流式 → 所有时延键结构完整、值很小但齐全。
  - **`--real`**:真实 faster-whisper + deepseek + 腾讯 SOE,出真实数值。
  - 返回 `ConversationRun{ scenario_id, mode, turns: [{user_text, ai_text, timings}] }`。
- `backend/app/testkit/report.py`:
  - 按 timing 键跨轮算 p50/p90/p95/max/mean/count(纯 stdlib,排序取分位)。
  - `render_markdown` + JSON,输出 `reports/bench-latest.{json,md}`。
- `scripts/run_conversation_bench.py`:
  - 参数 `--scenario --turns N --user scripted --real --output-dir`。
  - 默认离线;`--real` 时 `load_dotenv()` 并使用环境配置的真实 provider。

### 测试(默认 marker,离线)
- `tests/test_ws_bench_driver.py`:注入 FakeLLMClient + FakeASR,跑 3 轮 → N 条 turn 记录、
  每轮含 `reply_first_delta_ms`/`reply_itl_ms`/`dialogue_reply_ms` 等键;`report.aggregate` 出 p50/p90。
- `tests/test_ws_itl.py`(或并入现有 WS 测试):断言流式回合的 `timings` 含 `reply_itl_ms` 与 `reply_delta_count`。

### 生产代码影响
**只动 `main.py` WS 流式循环一处(ITL 几行)**。dialogue/grammar/llm 都不碰(流式团队已做)。
其余全是新增 `testkit/` 与 script。

### 验证
- `make test` 全绿、离线。
- `python3 scripts/run_conversation_bench.py --scenario interview --turns 10` → `reports/bench-latest.md`,
  各段(transcode/asr/TTFT/ITL/dialogue total/grammar)p50/p90 有值。
- `... --turns 10 --real` → `reply_first_delta_ms`(TTFT)、`reply_itl_ms`、`asr_ms`、pronunciation 段为真实数值。

### 提交节奏
沿用仓库小步直提 master,拆两个提交:① WS ITL(生产)+ 对应测试;② testkit driver + report + CLI。

## 4. 后续阶段(不在时延档)
- 语音通道真实档:TTS → WS → 真实 faster-whisper / 腾讯 SOE 的端到端时延 + WER。
- 虚拟用户 persona + 已知错误注入 → 语法纠错 precision/recall。
- 裁判 + rubric + fixture 标定 → 开放维度打分。
- 并发吞吐压测(C 路并发会话,时延退化)。
