# 自动化测试框架设计

> 本文是独立的测试框架设计文档,与主项目 `plan.md` 解耦,`plan.md` 不受影响。
> 目标:把"手动一句句聊"升级成**无前端、自动多轮**的后端 bench 框架,直接调用后端
> 对系统做时延 + 正确性测试。默认 `make test` 仍全程离线、确定性,真实服务走显式 flag。

## 1. 总体设计:三个独立部件

### 部件 1 — 虚拟用户(代替"我")
一个自动"假用户",给它"场景 + AI 上一句",它生成下一句用户台词,自动跑几十轮。
两种输入通道:
- **文本通道**:直接打 `/turns/text`,快,测对话/语法/LLM 时延。
- **语音通道**:虚拟用户文字 → TTS 合成音频 → 当作真麦克风喂进 `WS /ws/sessions/{id}/audio`,
  跑通 transcode + faster-whisper + 腾讯 SOE 的完整链路和真实时延。

关键技巧:虚拟用户可**植入已知错误**(生成带错台词,同时给出正确版本),手里就有 ground truth,
不需要裁判模型也能算"语法纠错抓没抓到"。TTS→ASR 这一圈还白送 ASR 的 WER ground truth
(注意 TTS 嗓音 ≠ 真人口音,只是 sanity check,真实口音准确率仍靠 l2_arctic fixture)。

### 部件 2 — 指标采集
原则:**contextvar 作用域**收集,不用模块全局(并发多会话不串)。
- `with record_span("asr_infer"):` 写入当前请求/轮次独立的收集器,无收集器时是 no-op(生产零负担)。
- 时延档先**只在 bench driver 里采集**,生产 REST/WS 不改。后续如需前端看时延,再加 REST opt-in。

可测指标:

| 段 | 指标 |
|---|---|
| ASR | transcode_ms、infer_ms、total(faster-whisper GPU) |
| 腾讯 SOE | ws_connect_ms、first_result_ms、total_ms |
| LLM 对话 | **TTFT**、total、output_tokens、**ITL**、tokens/sec |
| LLM 语法纠错 | TTFT、total |
| 端到端单轮 | end_turn → reply.text / http_turn_ms |
| DB 写入 | save_turn_ms |
| 聚合 | 几十轮的 p50/p90/p95/max;并发 C 路下的吞吐 |

> 名词:**TTFT**(Time To First Token,发完请求到第一个字,决定"AI 多久开始说话");
> **ITL**(Inter-Token Latency,首字之后平均每字间隔,决定吐字快慢)。现 LLM 非流式,
> 测不了 TTFT —— 故需给 LLM 加流式(边生成边收才能掐到第一个字)。

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
backend/app/core/timing.py     # contextvar span 收集器
backend/app/testkit/
  driver.py    # 自动多轮 driver(service 直调 / http TestClient 两种喂法)
  report.py    # p50/p90 聚合 + JSON/Markdown
  virtual_user.py   # (后续)persona 生成台词 + 已知错误注入
  judge.py          # (后续)裁判 client + rubric,默认 skip
scripts/run_conversation_bench.py   # CLI 入口
```
铁律:`make test` 默认全 fake/mock、不联网;真实模型/云一律 integration marker 或显式 `--real`。

## 3. 第一阶段:时延档(当前实施)

聚焦时延,用户已确认:driver 两种喂法都要、计时只在 driver 里测、出完整时延档。

### 两种模式各产出什么(避免误读数字)
- **service 模式(默认,离线确定性)**:每轮内部分段 `llm.dialogue.{ttft_ms,itl_ms,total_ms,output_chars}`、
  `llm.grammar.*`、`grammar_check_ms`、`dialogue_reply_ms`。
- **`--http` 模式**:跨 FastAPI 线程池,contextvar 传不进端点,故**只测每轮端到端总墙钟** `http_turn_ms`
  (含路由+DB+grammar+dialogue,不拆分段)。两种数据互补。

### 改动清单
| # | 文件 | 内容 |
|---|---|---|
| 1 | `backend/app/core/timing.py` | contextvar 计时器:`TimingCollector`/`start_collection`/`record_span`/`record_metric`;无 collector 全 no-op |
| 2 | `backend/app/services/llm.py` | 两个 client 加 `stream()`;`StructuredJSONCaller` 改为消费流并记 TTFT/ITL/total。**唯一计时切点**([llm.py StructuredJSONCaller.call](../backend/app/services/llm.py));dialogue/grammar 调用点零改动 |
| 3 | `backend/app/testkit/driver.py` | `run_text_conversation(scenario_id, turns, *, transport, user)`;台词复用 `dialogue_samples` user 轮(确定性、命中 fixture 回复) |
| 4 | `backend/app/testkit/report.py` | 按 span/metric 名跨轮算 p50/p90/p95/max/mean(纯 stdlib),输出 `reports/bench-latest.{json,md}` |
| 5 | `scripts/run_conversation_bench.py` | CLI:`--scenario --turns --transport service\|http --user scripted --real --output-dir` |
| 6 | `tests/test_timing.py` `test_llm_streaming.py` `test_bench_driver.py` | 默认离线 marker,fake/mock |

### 生产代码影响
**只动 `llm.py` 一个生产文件**(加流式)。`timing.py` 纯新增且 no-op 安全。
REST/WS、dialogue.py、grammar.py、main.py 都不碰。

### 流式 + 计时如何接(关键实现点)
两处 LLM 调用都收口在 `StructuredJSONCaller.call()` → `client.complete()`。改为内部 `_complete()`:
- 有活动 collector 且 client 有 `stream` → 消费流,首个非空 delta 记 `llm.{stage}.ttft_ms`,
  结束记 `total_ms`、`output_chars`,算 `itl_ms`;拼回完整字符串返回。
- 否则回退 `complete()`。JSON 解析逻辑不动,返回仍是完整 content。
- `FakeLLMClient.stream()` 按小块 yield 固定响应,默认测试也走流式路径且确定性。
- `OpenAICompatibleLLMClient.stream()` 用 httpx `stream("POST", ..., json={..., "stream": True})` 解析 SSE `data:` 行,遇 `[DONE]` 结束。

### 验证
- `make test` 全绿、离线。
- `python3 scripts/run_conversation_bench.py --scenario interview --turns 10` → `reports/bench-latest.md`,分段 p50/p90 有值。
- `... --transport http` → 有 `http_turn_ms` 分位。
- `... --turns 10 --real` → `llm.dialogue.ttft_ms`/`itl_ms` 为真实 deepseek 数值;确认 dialogue 与 grammar 两段 TTFT 都采到。

### 提交节奏
沿用仓库小步直提 master,拆两个提交:① timing + llm 流式 + 测试;② driver + report + CLI。

## 4. 后续阶段(不在时延档)
- 语音通道:TTS → WS → 真实 faster-whisper / 腾讯 SOE 的端到端时延 + WER。
- 虚拟用户 persona + 已知错误注入 → 语法纠错 precision/recall。
- 裁判 + rubric + fixture 标定 → 开放维度打分。
- 并发吞吐压测(C 路并发会话,时延退化)。
