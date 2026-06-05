# AI 英语口语陪练实现计划

## Summary

采用 **React/Vite + Python FastAPI**。后端优先，所有核心能力都按“输入 -> 输出”做可测试服务；前端只做简单网页接入。实时语音采用 **WebSocket 音频流通道 + 本地 faster-whisper ASR + 文本回复（可加轻量 TTS）**，发音评测先做 **统一接口 + Mock provider（用 speechocean762 真值分回放）**，后续再小 PR 接腾讯云/讯飞/Azure。

默认原则：

- 实时主链路只负责：录音、按轮整句 ASR、生成/流式返回 AI 回复、展示回复。
- **实时性优先级已确定**：只有 LLM 对话回复需要返回流式；ASR 采用一轮结束后整句识别；语法纠错、发音评测和错题生成都做旁路异步，不阻塞对话。
- 学习分析旁路异步负责：语法纠错、表达优化、发音评测、课后总结、错题本。
- **测试从第一天搭起、伴随全程**：每个能测的模块都自带数据驱动测试；只能手动测的，写进「手动测试清单」并写明步骤与判定标准。
- 测试默认不依赖前端、不依赖真实 LLM、不依赖真实发音云服务。
- 所有真实外部服务都通过 adapter 接入，测试使用 fake/mock。
- **PR 粒度尽量小，一个 PR 只做一件事**；功能、真实适配、评测三者拆开提交。

## 数据资产（已就位，决定测试怎么搭）

`fixtures/` 已包含四个公开数据集子集（由 `scripts/extract_fixtures.py` 还原）+ 三份手写 fixture：

| 数据集 | 数量 | 关键字段 | 用于模块 | 自动指标 |
|---|---|---|---|---|
| `librispeech_subset` | 30 | 干净英音 `transcript` | ASR 主链路 | WER |
| `l2_arctic_subset` | 45 | `transcript` + `native_language` + TextGrid 错音标注 | ASR（带口音）+ 误音检测 | WER / 误音命中 |
| `speechocean762_subset` | 45 | sentence/word/**phoneme** 三级真值分 | 发音评测 | 与真值分的相关性/误差 |
| `jfleg_subset` | 160 | `source` + 多条 `references` | 语法纠错 | GLEU + schema 通过率 |
| `grammar_expression_errors.json` | 20 | 原句/纠正句/错误类型 | 语法纠错单元 | schema + span 命中 |
| `dialogue_samples.json` | 10 | 三场景对话 | 对话回复 | 角色/目标命中（自然度手动） |
| `scenarios.json` | 3 | 场景配置 | 场景系统 | 配置合法性 |

要点：speechocean762 带 **phoneme 级真值分**，发音评测不只是测 schema，Mock provider 可直接回放真值分做确定性测试，真实 provider 上线后能算相关性。

## Implementation PRs

> 标 **[MVP]** 的是关键路径（最小可演示闭环）；其余为增强/评测/真实云接入，时间紧可后置。

### Phase A — 骨架与模型

1. **PR1：项目骨架 + 数据驱动测试框架** **[MVP]**
   - 建立 `backend/` FastAPI、`frontend/` React/Vite、`tests/`、`fixtures/`。
   - 后端 `pytest` + `httpx TestClient`；前端 `vitest`，后续加 Playwright smoke。
   - 集成 `scripts/extract_fixtures.py`：`make test` 前确保 `fixtures/generated/*` 与音频就位，缺失时给清晰提示而非报错。
   - 写**统一 fixtures 加载层**：集中读 4 个 manifest + 3 份手写 json，后续测试一律从这里取数，不各自硬编码路径。
   - 写**数据可用性测试**：manifest 能 parse、引用音频文件存在、计数与 `dataset_subset_summary.json` 一致。
   - 约定 pytest marker：`unit`（默认跑）、`integration`（真实 ASR/LLM/云，默认 skip）、`manual`（写成文档化清单）。
   - `.env.example`：`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`ASR_MODEL_SIZE`、`PRON_PROVIDER=mock`、`TTS_PROVIDER=browser`。
   - 命令：`make test`、`make test-backend`、`make test-frontend`、`make dev-backend`、`make dev-frontend`。

2. **PR2：会话类数据模型** **[MVP]**
   - Pydantic：`Scenario`、`Session`、`Turn`。
   - 每个模型提供 JSON Schema，测试校验示例 fixture 能 parse。

3. **PR3：分析类数据模型** **[MVP]**
   - Pydantic：`GrammarCorrection`、`PronunciationAssessment`、`SessionSummary`、`MistakeItem`、`AnalysisError`。
   - `AnalysisError { stage: asr|grammar|pronunciation|tts, code, user_message_zh, severity, fallback_applied }`：所有 provider 原始错误码先映射成内部 canonical code，再配中文文案。
   - 输出结构固定，后续 LLM/云服务都必须转成这些内部模型。

### Phase B — 后端核心服务（可纯输入输出测试）

4. **PR4：场景配置系统** **[MVP]**
   - 接入 `scenarios.json` 的 `interview`、`restaurant_ordering`、`meeting` 三场景。
   - 每个场景含：AI 角色、用户角色、开场白、对话目标、目标表达、纠错重点、总结评分规则。
   - API：`GET /api/scenarios`、`POST /api/sessions`、`POST /api/sessions/{id}/end`（结束会话，触发 summary 聚合）。
   - 测试：场景配置合法、创建 session 返回开场白与目标信息、end 状态流转。

5. **PR5：LLM 统一客户端** **[MVP]**
   - OpenAI-compatible adapter：`base_url/api_key/model` 配置。
   - `FakeLLMClient`，测试默认使用 fake，不访问网络。
   - 结构化 JSON 调用工具：解析失败重试一次，仍失败返回可记录错误（落到 `AnalysisError`）。
   - 测试：fake 响应、JSON 解析、无效 JSON fallback。

6. **PR6：语法/表达纠错服务** **[MVP]**
   - 输入：`scenario_id`、`user_text`、`conversation_context`。
   - 输出：原句、纠正句、更好表达、错误列表、严重程度、中文解释、**建议纠错时机**。
   - 纠错原则：不把自然口语强行改成书面作文，不改变用户原意。
   - **纠错时机策略**：实时对话中**不打断**，仅旁路收集；仅严重错误即时轻提示；其余进课后总结。
   - API：`POST /api/grammar/check`。
   - 测试：用 `grammar_expression_errors.json` 20 条校验输出 schema、span 存在于原文、严重错误能被识别。

7. **PR7：语法纠错评测 harness（jfleg）**
   - 读取 `jfleg_subset`（160 条，多 reference）计算 **GLEU** 与 schema 通过率。
   - 标 `integration`（走真实/可配 LLM 时跑），默认可用 fake 跑流程冒烟。
   - 输出进入后续报告。

8. **PR8：场景化对话回复服务** **[MVP]**
   - 输入：session 状态、上一轮用户文本、场景配置。
   - 输出：AI 回复文本、当前对话目标、下一步追问意图。
   - 对话回复不做长篇教学纠错，只负责继续自然对话。
   - API：`POST /api/sessions/{id}/turns/text`（后端测试与前端文本 fallback）。
   - 测试：用 `dialogue_samples.json` 校验面试/点餐/会议三类场景回复符合角色与目标（自然度走手动清单）。

9. **PR9：SQLite 会话日志** **[MVP]**
   - SQLite 存 session、turn、correction、pronunciation assessment、mistake item、analysis_error。
   - 本地 demo 单用户模式，不做登录。
   - 测试使用临时 SQLite，不污染开发库；验证写入/关联/历史查询。

### Phase C — 实时语音

10. **PR10：WebSocket 按轮协议 + FakeASR** **[MVP]**
    - 前端 WS 发送音频 chunks，`end_turn` 结束本轮；后端保存音频、转写、返回 `asr.partial`/`asr.final` 与 AI 回复。
    - 第一版“流式传输 + 按轮识别”，不做连续 VAD 自动断句；但提供 `asr.partial` 改善感知延迟。
    - API：`WS /ws/sessions/{id}/audio`。
    - 测试：默认 `FakeASR`，校验事件流（含 partial/final）。

11. **PR11：faster-whisper 真实适配 + ASR 评测（librispeech）**
    - 真实 faster-whisper adapter，配置 `ASR_MODEL_SIZE`。
    - 用 `librispeech_subset` 30 条算 **WER**，标 `integration`，无模型时 skip。

12. **PR12：带口音 ASR / 误音检测评测（l2_arctic）**
    - 用 `l2_arctic_subset` 45 条算带口音 WER；结合 TextGrid 标注做误音命中初版。
    - 标 `integration`，默认 skip。

### Phase D — 发音评测

13. **PR13：发音评测接口 + Mock provider** **[MVP]**
    - 输入：`reference_text`、用户跟读音频。**v1 只覆盖跟读模式**；对话自由发言的发音评测标为后续。
    - 输出：overall、accuracy、fluency、prosody、word scores、phoneme scores、issue。
    - Mock provider 按 `speechocean762_subset` 真值分**确定性回放**。
    - API：`POST /api/pronunciation/assess`。
    - 测试：mock 结果转内部模型、字段完整、低分单词可被识别。

14. **PR14：发音评测相关性评测（speechocean762）**
    - 以 speechocean762 真值分为基准，算 provider 输出与真值的相关性/误差（sentence/word/phoneme 三级）。
    - 进入报告；真实 provider 上线后复用同一 harness。

15. **PR15：错题本（含发音错题生成）**
    - 从语法纠错、表达优化、发音评测自动生成错题；类型 `grammar`/`expression`/`pronunciation`。
    - 字段：错误表达、正确表达、解释、练习句、单词、音标、掌握度、复习次数。
    - API：`GET /api/mistakes`、`POST /api/mistakes/{id}/review`。
    - 测试：重复错误合并、复习次数更新、掌握度变化、低分单词→发音错题。

### Phase E — 聚合与回传

16. **PR16：异步分析编排 + 结果/错误回传通道** **[MVP]**
    - 旁路异步算完 grammar/pronunciation 后，通过 WS 事件 `analysis.result` / `analysis.error` 回传；并提供 `GET /api/sessions/{id}/analysis` 作为拉取兜底。
    - **错误就地、非弹窗**：错误以 `AnalysisError` 形式回传，前端在纠错/发音结果区渲染一条 inline 提示（把「错误占位」当作纠错卡片的一种状态）。
    - 测试：fake provider 报错 → 服务返回 `AnalysisError` 且 `fallback_applied` 正确 → WS 收到 `analysis.error` 事件。

17. **PR17：课后总结** **[MVP]**
    - 输入：完整 session log（end 后触发）。
    - 输出：语法、发音、流利度、词汇、场景任务完成度分数，及 top issues、next drills。
    - 从已有结构化结果聚合，缺少发音评测时返回部分总结。
    - API：`GET /api/sessions/{id}/summary`。
    - 测试：fixture session 生成稳定 summary；缺发音时降级。

18. **PR18：跨会话进度反馈**
    - 聚合历次 summary 分数，输出能力随时间的趋势（对应「可量化反馈/能力提升」）。
    - API：`GET /api/progress`。
    - 测试：多 session fixture 生成稳定趋势。

### Phase F — 前端（按面板拆，每个一件事）

19. **PR19：前端骨架 + 场景选择 + 对话区/录音** **[MVP]**
    - 走 REST/WS 调后端，不含核心业务逻辑；先打通选场景 → 录音/文本 → 看回复。

20. **PR20：纠错侧栏 + 错误就地展示** **[MVP]**
    - 渲染 `analysis.result` 纠错卡片；`analysis.error` 在同一区域渲染 inline 提示，**不弹窗**。

21. **PR21：跟读练习面板**
    - 跟读句 + 录音 → 发音评测结果（word/phoneme 高亮）。

22. **PR22：课后总结 + 错题本面板**
    - 展示 summary、进度趋势、错题本与复习。

23. **PR23：轻量语音输出 + partial 滚动**
    - 浏览器 `speechSynthesis` 播放 AI 回复；`asr.partial` 实时滚动显示，降低感知延迟。

### Phase G — 评测与真实云

24. **PR24：评测与报告生成**
    - `backend/eval` 读取 fixture 生成量化报告 JSON/Markdown。
    - 指标：ASR WER（librispeech/l2_arctic）、grammar GLEU + schema 通过率、发音相关性、provider 返回率、会话端到端**分段延迟**、summary 成功率。
    - 真实外部服务评测单独标记，不影响默认 CI。
    - 输出：`reports/latest.md`。

25. **PR25：真实发音云服务适配器**
    - Mock 稳定后再接；优先腾讯云或讯飞，取决于账号配置。只做 provider adapter，不改业务层。
    - **云会话按轮（per-turn）开闭**，避免单会话跨越讯飞 5 分钟上限；超长轮次切分。
    - 错误映射：讯飞 `10114/60114` → canonical `provider_session_expired` → 中文「本轮语音过长，已自动重连，请重说这一句」→ 自动重开/降级 mock，不中断主对话；同理覆盖限流、超时、音频非法。
    - 测试：contract test 用录制/脱敏 fixture，**含错误码样本**，断言映射成正确 canonical code + 文案；无 key 时自动 skip。

26. **PR26：真实 TTS 云服务适配器（可选）**
    - 与发音 provider 对称，mock-first；提升 AI 语音回复自然度。无 key 时回退浏览器 TTS。

## Public Interfaces

后端主要 API：

- `GET /api/scenarios`
- `POST /api/sessions`
- `POST /api/sessions/{id}/end`
- `POST /api/sessions/{id}/turns/text`
- `WS /ws/sessions/{id}/audio`
- `GET /api/sessions/{id}/analysis`
- `POST /api/grammar/check`
- `POST /api/pronunciation/assess`
- `GET /api/sessions/{id}/summary`
- `GET /api/progress`
- `GET /api/mistakes`
- `POST /api/mistakes/{id}/review`

WebSocket 事件：

- Client：`start_turn`
- Client：binary audio chunk
- Client：`end_turn`
- Server：`asr.partial`
- Server：`asr.final`
- Server：`reply.text`
- Server：`analysis.pending`
- Server：`analysis.result`
- Server：`analysis.error`（就地、非弹窗展示）
- Server：`error`

## 延迟预算（验收指标，非事后才看）

分段计时，PR24 报告中产出：

- `end_turn` → `asr.final`
- `asr.final` → `reply.text`
- `reply.text` → 开始播放（TTS）

每段设目标值，超标在报告中标红。

## 演示与验证方式

**实现过程中的验证一律走后端数据集子集测试，不依赖界面。** 浏览器界面只用于人工演示和手动清单。

| 测什么 | 在哪跑 | 怎么跑 | 是否需要界面 |
|---|---|---|---|
| ASR/语法/发音/对话/总结/错误降级 | 后端 pytest（fixture 子集） | `make test-backend` | ❌ 命令行 |
| 数据集指标（WER/GLEU/发音相关性/延迟） | 后端 eval harness | PR24 → `reports/latest.md` | ❌ 报告文件 |
| 前端组件 | vitest（无头） | `make test-frontend` | ❌ |
| 端到端接通性 | Playwright smoke（一条） | PR23/24 | ✅ 自动开浏览器 |
| 自然度/TTS 听感/partial 体验 | 人工，手动清单 | `make dev-frontend` 手动看听点 | ✅ |

原则：

- **开发期默认只跑 `make test`（后端子集）即可**，稳定、可复现、不依赖麦克风/网络/真实云。
- 浏览器界面是给评委演示和「手动测试清单」用的；机器能测的都不放到界面里测。
- README「评委任意时间查看应能复现」由两条共同保证：`make test` 绿 + 主分支能 `make dev` 起界面。

## Test Plan

默认测试不需要真实外部服务，marker 分层：`unit`（默认）/`integration`（默认 skip）/`manual`（文档清单）。

- **数据可用性测试**：manifest parse、音频存在、计数一致。
- **模型层**：Pydantic schema parse、必填字段、枚举合法性。
- **服务层**：grammar、dialogue、pronunciation、summary、mistake、analysis-error 都用 fake/mock client。
- **API 测试**：FastAPI TestClient 调 REST；WebSocket 使用 fake ASR，校验含 partial/final/analysis.result/analysis.error 的事件流。
- **数据库测试**：临时 SQLite，验证写入与查询。
- **评测 harness**：ASR WER（librispeech/l2_arctic）、grammar GLEU（jfleg）、发音相关性（speechocean762）。
- **错误路径**：模拟 provider 报错（含讯飞 10114/60114）→ canonical 映射 + 文案 + 降级。
- **集成测试**：真实 LLM、faster-whisper、发音/TTS 云通过 env 开启，默认 skip。

### 数据 ↔ 模块 ↔ 指标映射

见上文「数据资产」表；每个模块 PR 的「测试方式」须落到该表对应行。

### 手动测试清单（写明步骤与判定）

- **对话自然度**：跑三场景各一轮对话，人工判定回复是否符合角色、是否推进对话目标、是否冗长说教。
- **纠错时机体验**：确认实时对话**不被纠错打断**；仅严重错误即时轻提示；其余进课后总结。
- **错误就地展示**：手动触发 provider 错误，确认纠错/发音区出现 inline 提示且**无弹窗**，主对话不中断。
- **TTS 音质 / 端到端听感**：人工听 AI 回复语音是否可懂、延迟是否可接受；演示浏览器使用 Edge/Chrome，不使用 QQ 浏览器验收 TTS 听感。
- **partial 体验**：说话时确认中间转写实时滚动。

## Assumptions

- 技术栈固定为 React/Vite + Python FastAPI。
- 第一版是单用户本地 demo，不做账号系统。
- ASR 第一版用本地 faster-whisper；测试默认用 FakeASR，真实跑用 librispeech/l2_arctic 评测。
- AI 回复第一版以文本为主，浏览器 TTS 轻量播放；真实 TTS 云为可选 PR。
- 发音评测第一版只做统一接口 + Mock provider（speechocean762 真值回放），**仅跟读模式**，真实云与自由发言评测单独 PR。
- 所有云服务错误以 `AnalysisError` 就地非弹窗展示并自动降级，不中断主对话。
- 后端能力必须先能通过纯输入输出测试，再接前端。

## 2026-06-05 执行进展更新

本节用于记录原计划已经执行到哪里，以及从当前状态继续往最终可演示项目推进时，后续实际执行顺序是什么。上面的原始计划保留不改，用于回看项目是怎么一步步拆出来的。

### 当前基线

- `make test` 已通过。
- 后端：73 passed，1 个 integration/manual 测试默认跳过。
- 前端：4 passed。
- UI 已能启动并完成基础 demo：选场景、开始会话、文本对话、纠错展示、Read Aloud 发音评测展示、Summary、Mistakes。
- 本地 `.env` 已配置真实 LLM 和腾讯 SOE：
  - `LLM_PROVIDER=openai_compatible`
  - `LLM_MODEL=deepseek-v4-flash`
  - `PRON_PROVIDER=tencent_soe`
  - `ASR_PROVIDER=fake`
  - `TTS_PROVIDER=browser`
- 注意：当前后端默认不会自动读取 `.env`，直接 `make dev-backend` 时仍可能走代码默认 fake/mock；真实链路启动仍需要先 `source .env`。

### 原计划完成度

| 原计划项 | 当前状态 | 说明 |
|---|---|---|
| PR1 项目骨架 + 数据驱动测试框架 | 已完成 | 后端、前端、fixtures、Makefile、默认测试和评测脚本都已就位。 |
| PR2 会话类数据模型 | 已完成 | `Scenario`、`Session`、`Turn` 已实现并有测试。 |
| PR3 分析类数据模型 | 已完成 | `GrammarCorrection`、`PronunciationAssessment`、`SessionSummary`、`MistakeItem`、`AnalysisError` 已实现。 |
| PR4 场景配置系统 | 已完成 | 三个场景、创建/结束 session、场景 API 已实现。 |
| PR5 LLM 统一客户端 | 基本完成 | OpenAI-compatible adapter 和 fake client 已实现；还缺统一错误映射和启动时 `.env` 自动加载。 |
| PR6 语法/表达纠错服务 | 基本完成 | fixture 优先、真实 LLM fallback 已实现；还需去掉前端重复调用并强化 schema/error handling。 |
| PR7 语法纠错评测 harness | 已完成 | JFLEG fixture 评测流程已在报告中产出。 |
| PR8 场景化对话回复服务 | 基本完成 | 文本回合已能走 fixture/LLM/fallback；还需让真实 LLM 成为自由输入主路径并优化 prompt。 |
| PR9 SQLite 会话日志 | 已完成 | session、turn、grammar、pronunciation、mistake、analysis error 表已实现。 |
| PR10 WebSocket 按轮协议 + FakeASR | 部分完成 | 后端 WS 协议和 FakeASR 已实现；前端当前发送的是模拟音频和 `expected_text`，不是真麦克风。 |
| PR11 faster-whisper 真实适配 + ASR 评测 | 部分完成 | adapter 已有；还没完成真实浏览器录音转码后的 end-to-end smoke。 |
| PR12 带口音 ASR / 误音检测评测 | 未完成 | 当前报告可用 fake ASR 跑通流程，但没有真实带口音 ASR/误音检测能力。 |
| PR13 发音评测接口 + Mock provider | 已完成 | Mock provider 可按 SpeechOcean fixture 回放分数。 |
| PR14 发音评测相关性评测 | 已完成 | fixture-backed 相关性/MAE 报告已可生成。 |
| PR15 错题本 | 已完成 | 语法、表达、发音错题生成、合并、review 已实现。 |
| PR16 异步分析编排 + 结果/错误回传 | 部分完成 | WS 已回传 grammar `analysis.result/error`；还不是真异步编排，也未覆盖真实 pronunciation error。 |
| PR17 课后总结 | 部分完成 | Summary 已有；但当前主要基于语法重新计算，未聚合本 session 发音评测结果。 |
| PR18 跨会话进度反馈 | 基本完成 | `/api/progress` 已有基础趋势；前端展示还比较弱。 |
| PR19 前端骨架 + 场景选择 + 对话区/录音 | 部分完成 | 骨架、场景、对话已完成；录音仍是模拟。 |
| PR20 纠错侧栏 + 错误就地展示 | 部分完成 | 基础纠错展示已完成；真实 provider 错误 inline 展示还需补齐。 |
| PR21 跟读练习面板 | 部分完成 | UI 能展示评测结果；当前固定 fixture，不是用户现场录音。 |
| PR22 课后总结 + 错题本面板 | 基本完成 | Summary 和 Mistakes 已展示；Progress 趋势展示还需加强。 |
| PR23 轻量语音输出 + partial 滚动 | 基本完成 | 浏览器 TTS 和 partial 展示已有；partial 当前来自 fake/expected text。 |
| PR24 评测与报告生成 | 部分完成 | 默认 fixture fake 报告已完成；真实服务 smoke、分段延迟报告还没做。 |
| PR25 真实发音云服务适配器 | 部分完成 | Tencent SOE provider 和手动 smoke 已完成；还缺用户上传音频入口、错误映射、前端真实录音接入。 |
| PR26 真实 TTS 云服务适配器 | 未完成 | 当前保留浏览器 TTS fallback，云 TTS 作为可选后置项。 |

### 当前主要缺口

1. 真实录音没有接入
   - 前端 `Voice` 当前是模拟链路：发送 `expected_text` 和假字节。
   - 需要换成 `getUserMedia` + `MediaRecorder` 真实录音。

2. ASR 仍是 fake
   - `.env` 当前 `ASR_PROVIDER=fake`。
   - `FasterWhisperASR` 已有代码，但还没有和浏览器录音、ffmpeg 转码、WS 回合完整串起来。

3. 跟读评测还在评 fixture
   - Read Aloud 当前固定请求 `fixture_id=speechocean_000010113`。
   - 即使 `PRON_PROVIDER=tencent_soe` 生效，评测的也是 fixture 音频，不是用户现场录音。

4. `.env` 启动体验不完整
   - 真实 key 已在本地 `.env`，但后端不会自动加载。
   - 需要让 `make dev-backend` 的行为和本地配置一致，并在 `/api/health` 暴露非敏感 provider 状态。

5. 真实 provider 错误映射不完整
   - LLM JSON 解析已有 fallback。
   - 腾讯 SOE、ASR、转码等错误还应统一变成 `AnalysisError`，前端 inline 展示，不中断主对话。

6. 前端文本纠错重复调用
   - `/api/sessions/{id}/turns/text` 后端内部已经做 grammar check。
   - 前端 `sendTurn()` 又额外调用 `/api/grammar/check`，后续要去重。

### 新的执行计划

后续执行以“把现有 demo 变成真实可演示链路”为目标。保持原计划的测试原则：默认测试仍不访问真实云、不依赖麦克风、不依赖浏览器手动操作。

#### P0：配置和状态可观测

1. 后端自动加载项目根目录 `.env`。
2. 扩展 `/api/health`，返回非敏感 provider 状态：
   - `llm_provider`
   - `llm_model`
   - `asr_provider`
   - `pronunciation_provider`
   - `tts_provider`
   - `external_services_enabled`
3. README 更新真实链路启动方式。
4. 保证 `make test` 默认仍不调用真实 LLM/腾讯云。

验收：

- 直接 `make dev-backend` 后，`/api/health` 能看到当前 provider 配置状态。
- 输出中不包含 key、secret、完整 base URL 或其他敏感信息。

#### P0：真实浏览器录音和音频落盘

1. 前端把 `simulateVoiceTurn()` 替换为真实录音：
   - `navigator.mediaDevices.getUserMedia({ audio: true })`
   - `MediaRecorder`
   - 按 chunk 发送到 `WS /ws/sessions/{id}/audio`
2. UI 增加录音状态：
   - idle
   - recording
   - processing
   - error
3. 后端把收到的音频按 session/turn 保存到 `.local/audio/`。
4. `Turn` 记录 `mode=audio` 和 `audio_path`。
5. 后端处理空音频、过短音频、非法格式，并返回清晰错误。

验收：

- 浏览器真实说一句话，后端能保存非空音频文件。
- WS 不再依赖 `expected_text`。

#### P0：音频转码和真实 ASR

1. 引入 ffmpeg 转码流程：
   - 浏览器常见 `webm/opus` 转 `16kHz mono wav`。
   - 缺少 ffmpeg 时给出清晰错误。
2. 启用 `ASR_PROVIDER=faster_whisper` 真实识别链路。
3. 对缺依赖、模型加载失败、转写失败、超时做 `AnalysisError(stage=asr)`。
4. 保留 `FakeASR` 用于默认测试。

验收：

- 真实麦克风录音能返回 `asr.final`。
- ASR 文本进入 AI 回复和语法纠错。

#### P0：真实 LLM 主路径与纠错去重

1. 自由输入优先走真实 `openai_compatible` LLM。
2. 保留 fixture 优先逻辑用于测试稳定性。
3. 优化 dialogue prompt：
   - 回复短。
   - 保持场景角色。
   - 推进当前目标。
   - 不在 AI 回复里长篇讲语法。
4. 强化 grammar JSON schema 解析和错误映射。
5. 前端去掉对 `/api/grammar/check` 的重复调用，改用 `/turns/text` 产生的 analysis 或 WS `analysis.result`。

验收：

- 输入 fixture 之外的自然句子时，AI 回复不再总是固定 fallback。
- LLM 失败时前端 inline 展示错误，主对话不中断。

#### P0：真实跟读发音评测

1. 新增用户音频评测入口，二选一：
   - `POST /api/pronunciation/assess/upload`：multipart 上传 `reference_text` + audio。
   - 或通过安全 `turn_id` 引用后端已落盘音频触发评测。
2. 前端 Read Aloud 面板使用真实录音。
3. 后端转 WAV 后调用 Tencent SOE。
4. 映射腾讯 SOE 错误：
   - 握手失败。
   - 签名/鉴权失败。
   - 超时。
   - 音频格式错误。
   - 服务限流。
5. 发音低分单词继续进入错题本。

验收：

- 用户现场读参考句，腾讯 SOE 返回真实评分。
- 评测失败只影响发音面板，不中断主对话。

#### P1：Summary、Progress 和前端演示体验

1. Summary 优先使用本 session 已有 analysis/pronunciation 结果，不再盲目重新跑 grammar check。
2. Summary 加入本次发音分数和发音 top issues。
3. Progress 前端展示历史趋势。
4. 前端清理状态：
   - 新 session 清空上一轮 partial/pronunciation/summary。
   - End 后禁用录音和发送。
   - 录音权限失败给清晰提示。
5. Coach 面板统一渲染 correction、pronunciation、summary、mistakes、analysis error。

验收：

- 评委可以顺着 UI 完成：选场景 -> 录音对话 -> 跟读评测 -> 错题 -> 结束总结。

#### P1：真实链路报告

1. 保留默认 fixture fake report。
2. 新增真实服务 smoke report，不影响默认 CI：
   - LLM 成功率和平均延迟。
   - ASR 一句话 smoke。
   - 腾讯 SOE smoke。
   - UI e2e smoke。
3. 记录分段延迟：
   - `end_turn -> asr.final`
   - `asr.final -> reply.text`
   - `reply.text -> tts_start`
   - pronunciation upload -> final result

验收：

- 默认 `reports/latest.md` 仍是稳定、可复现的 fixture 指标。
- 真实 smoke report 单独生成，失败时不影响默认测试。

#### P2：可选后置项

1. 云 TTS provider。
2. 自由对话每轮自动发音评测。
3. 更细的场景目标状态机和对话控制。

### 后续 PR 切分

1. PR-A：自动加载 `.env` + `/api/health` provider 状态。
2. PR-B：前端真实 `MediaRecorder` 录音 + WS 发送真实音频。
3. PR-C：后端音频落盘、ffmpeg 转 WAV、Turn 记录 `audio_path`。
4. PR-D：`ASR_PROVIDER=faster_whisper` 真实链路 smoke。
5. PR-E：文本对话去重纠错调用，统一 analysis 回传。
6. PR-F：LLM 错误统一映射 `AnalysisError`。
7. PR-G：跟读评测上传用户录音并调用 Tencent SOE。
8. PR-H：Tencent SOE 错误映射和前端 inline 展示。
9. PR-I：Summary 接入真实 analysis/pronunciation 结果。
10. PR-J：真实服务 smoke report 和手动测试清单更新。

### 后续执行注意事项

- 原始计划保留作为历史，不再覆盖删除。
- 每次推进新任务时，以本节“新的执行计划”为当前优先级。
- 默认测试必须保持稳定、离线、可复现。
- 真实 key 不能写进 README、plan、测试输出或报告。
- 腾讯 SOE 是发音评测，不是 ASR；ASR provider 要单独处理。
- 浏览器录音格式和腾讯/whisper 需要的 WAV 格式不同，转码链路是必须项。

### 2026-06-05 后续执行记录

以下为基于“新的执行计划”已经完成的小步提交：

| 提交 | 对应计划 | 状态 | 说明 |
|---|---|---|---|
| `1e57f7b` | PR-A | 已完成 | 后端自动加载 `.env`，`/api/health` 返回非敏感 provider 状态；默认测试禁用真实 provider。 |
| `784e9f5` | PR-B | 已完成 | 前端 `Voice` 改为真实 `MediaRecorder` 录音，通过现有 WS 发送音频 chunk。 |
| `4a421d4` | PR-C | 已完成 | 后端保存 WS 音频，尽力转 WAV，用户 turn 记录 `mode=audio` 和 `audio_path`。 |
| `1e8a28e` | PR-D | 已完成基础 smoke | 增加 ASR provider smoke 脚本，`FasterWhisperASR` 支持直接转写 fixture 文件路径；提交当时未装 `faster-whisper`，后续已补完真实 CUDA smoke。 |
| `c04b19e` | PR-E | 已完成 | `/turns/text` 返回 `grammar_result`，前端不再重复调用 `/api/grammar/check`。 |
| `799c15b` | PR-F | 已完成第一步 | LLM provider 异常统一映射为 `AnalysisError`，避免 provider 异常直接冒泡。 |
| `f9740b8` | PR-G | 已完成后端入口 | 新增 `/api/pronunciation/assess/upload`，支持 `reference_text` + `audio_base64` + `mime_type`。 |
| `3903904` | PR-G | 已完成前端入口 | Read Aloud 改为真实录音并上传用户音频进行评测。 |
| `91882a9` | PR-H | 已完成第一步 | 发音 provider `RuntimeError` 映射为结构化 `AnalysisError`，前端可显示中文错误文案。 |
| `f20f674` | PR-D | 已完成依赖记录 | README 和计划记录 `faster-whisper`、`ffmpeg` 的用途、安装方式和手动模型下载要求。 |
| `91d4ac4` | PR-D | 已完成模型目录准备 | 新增 `models/` 目录说明和忽略规则，README 记录本地模型路径与 V100/CUDA smoke 示例。 |
| `e28bef4` | PR-D | 已完成真实 CUDA smoke | `models/faster-whisper-small.en/` 已落位，V100/CUDA 上通过 `scripts/test_asr_provider.py`。 |
| `d349116` | PR-D2 | 已完成 | WebSocket 音频回合改为使用保存/转码后的 `stored_audio.preferred_path` 调用文件级 ASR，并补默认离线测试验证路径调用。 |
| `f5d7ca8` | PR-H2 | 已完成后端分类 | 腾讯 SOE 发音评测失败映射为稳定 canonical code，覆盖配置缺失、鉴权失败、连接失败、超时、限流和音频格式错误；默认测试通过 mock provider 覆盖。 |
| `543bd1e` | PR-G2 | 已完成后端入口 | 发音评测请求支持可选 `session_id`，成功后写入 session 级 `pronunciation_results`，并通过 `/api/sessions/{id}/analysis` 返回。 |
| `9e4d46f` | PR-G2 | 已完成前端传参 | Read Aloud 在 active session 下上传 `session_id`，无 session 时保持原独立评测请求。 |
| `d3bb415` | PR-I | 已完成 Summary 第一版 | Summary 优先使用 session 已有 grammar/pronunciation analysis；发音结果进入 `pronunciation_score`、`top_issues` 和 `next_drills`，无已有 grammar 时保留 fallback。 |
| `877a7a7` | PR-J | 已完成离线骨架 | 新增 fixture-backed smoke report 和脚本，默认覆盖 ASR、Grammar、Pronunciation、dialogue fixture、UI 手动清单与延迟字段占位，不访问真实服务。 |
| `1167e08` | PR-K | 已完成第一步 | End session 后禁用文本发送、语音 Record 和 Read Aloud，前端测试覆盖 ended session 控件状态。 |
| `a24d91f` | PR-D/PR-H | 已完成 | WebSocket ASR 和发音 provider 异常统一映射为 `AnalysisError`；发音失败会关联当前 session analysis。 |
| `974ebba` | PR-J | 已完成 | 新增显式真实 provider smoke report：LLM、ASR、腾讯 SOE 状态和延迟写入 `reports/smoke-real-latest.*`。 |
| `9bac9a1` | PR-I2/PR-K | 已完成 | 前端 progress 摘要、provider 错误 inline 展示、summary loading/error、新 session 状态清理已补齐。 |
| `dcdda1a` | PR-D | 已完成 | 默认测试覆盖 ffmpeg 缺失、ASR provider 异常、ASR 空转写等真实录音链路失败路径。 |
| `c6769b2` | PR-J | 已完成 | 真实 smoke report 错误信息脱敏，避免报告写入完整 URL 或敏感配置。 |

本轮收口后的当前状态：

- PR-D 的依赖已在当前环境安装：`faster-whisper` 作为本地 ASR 推理库，`ffmpeg` 作为音频解码/转码工具。
- PR-D 的模型文件已放入 `models/faster-whisper-small.en/`，并已通过 V100/CUDA smoke：
  `CUDA_VISIBLE_DEVICES=0 ASR_PROVIDER=faster_whisper ASR_MODEL_SIZE=/home/scn/xe2/models/faster-whisper-small.en ASR_DEVICE=cuda ASR_COMPUTE_TYPE=float16 python3 scripts/test_asr_provider.py`。
- PR-H2 后端腾讯 SOE 错误分类已完成，前端 inline 展示已覆盖权限失败、WS `analysis.error`、pronunciation 502/provider 错误。
- PR-I Summary 服务层已接入已有 analysis/pronunciation 结果，前端 summary loading/error 状态已补。
- PR-J 离线 smoke report 和真实 provider smoke report 均已完成。当前真实 smoke 结果：LLM passed、faster-whisper ASR passed、Tencent SOE passed；ASR fixture WER 约 `0.0588`。
- 默认测试仍使用 fake/mock provider；真实 provider 只通过 `python3 scripts/run_smoke_report.py --mode real` 显式触发。
- 浏览器麦克风现场演示仍属于手动验收：打开 UI 后按 checklist 录一轮对话和一次 Read Aloud 即可，不需要新增数据集或提交录音。

### 2026-06-05 可执行计划 v2：真实服务可用后的收口计划

当前前提：

- `.env` 已具备真实 LLM 与腾讯 SOE 配置；文档、测试输出和报告仍不能泄露真实 key。
- `faster-whisper`、`ffmpeg` 已安装；`models/faster-whisper-small.en/` 已由维护者手动上传。
- 本机 V100/CUDA 已通过 ASR smoke，后续可实现真实本地 ASR、真实 LLM、真实腾讯 SOE 和浏览器录音 UI 的完整链路。
- 默认测试仍必须离线、确定性、可复现；真实服务只走显式 integration/manual smoke。

测试框架约束：

- 默认验证命令继续是 `make test`，只使用 fake/mock provider 和 fixtures，不访问外网，不依赖真实 key。
- 真实链路统一使用 `pytest.mark.integration`、独立脚本或 manual smoke；失败不能影响默认测试。
- 新增额外测试库必须先在 README 和本计划记录用途。当前先不新增浏览器 e2e 依赖；前端继续用 Vitest mock `MediaRecorder`、`WebSocket`、`fetch`。
- 所有测试数据优先来自现有 fixtures：
  - `fixtures/audio/public/librispeech_subset/`：ASR 英语母语音频 smoke 和准确率 sanity。
  - `fixtures/audio/public/l2_arctic_subset/`：ASR 二语口音 sanity。
  - `fixtures/generated/speechocean762_subset.json` 与 `fixtures/audio/public/speechocean762_subset/`：发音评测 mock、腾讯 SOE 手动 smoke、错题生成。
  - `fixtures/generated/jfleg_subset.json` 与 `fixtures/grammar_expression_errors.json`：语法纠错和表达改写。
  - `fixtures/scenarios.json`、`fixtures/dialogue_samples.json`：对话、总结、进度和 UI 状态。

后续小 PR 切分：

1. **PR-D2：WebSocket 真实 ASR 路径加固**
   - 目标：WS 收到浏览器音频后，优先使用 `save_turn_audio()` 转出的 `preferred_path` 调用文件级 ASR，避免把 webm/opus bytes 误写成临时 wav。
   - 测试：默认测试用 monkeypatch provider 验证 WS 传入的是转码后文件路径；integration 用 `faster-whisper-small.en` + LibriSpeech fixture 验证 `transcribe_file()`。
   - 数据：LibriSpeech fixture；必要时用现有音频文件模拟 WS binary chunk。

2. **PR-H2：腾讯 SOE 错误分类与前端展示**
   - 目标：把鉴权失败、握手失败、超时、限流、音频格式错误映射成稳定 canonical code；前端 inline 展示中文错误，不中断对话。
   - 测试：默认单测 mock Tencent 返回/异常；manual smoke 用 `scripts/test_tencent_soe.py` 跑 SpeechOcean762 fixture。
   - 数据：SpeechOcean762 fixture。

3. **PR-G2：发音评测结果和 session 关联**
   - 目标：Read Aloud 上传结果可关联当前 session，Summary/Progress 能读取本 session 的 pronunciation assessment。
   - 测试：后端 API 单测覆盖 session_id 透传与 storage/analysis_store；前端 Vitest 覆盖评测后总结面板可读到最新分数。
   - 数据：SpeechOcean762 fixture。

4. **PR-I：Summary 使用已有 analysis/pronunciation**
   - 目标：Summary 优先使用 session 已有 grammar/pronunciation 结果，不再对历史 turn 盲目重新跑 grammar；加入发音 top issues。
   - 测试：构造 session + analysis_store fixture 结果，断言不会再次调用 grammar provider；API 测试覆盖 text turn、audio turn、pronunciation result 混合场景。
   - 数据：JFLEG/grammar fixture、SpeechOcean762 fixture、dialogue_samples。

5. **PR-I2：Progress 与错题趋势**
   - 目标：Progress 展示历史趋势，发音低分单词和语法错误都能进入错题复习统计。
   - 测试：storage/progress 单测覆盖多次 session、多次 review、语法与发音混合 mistake。
   - 数据：SpeechOcean762 fixture、grammar_expression_errors。

6. **PR-J：真实服务 smoke report**
   - 目标：新增不影响默认 CI 的真实 smoke 报告，记录 LLM、ASR、Tencent SOE、UI 手动链路状态和分段延迟。
   - 测试：报告生成器默认可用 fake fixture 生成；真实模式显式读取 `.env` 和本地模型路径。
   - 数据：LibriSpeech fixture、SpeechOcean762 fixture、dialogue_samples。

7. **PR-K：前端收尾状态**
   - 目标：新 session 清空上一轮 partial/pronunciation/summary；End 后禁用录音和发送；录音权限失败、provider 错误、summary loading 都有明确状态。
   - 测试：Vitest 扩展现有 `App.test.jsx`，mock 权限拒绝、WS error、pronunciation 502、session end。
   - 数据：前端 mock payload 来自 scenarios、dialogue_samples、SpeechOcean762 fixture 字段结构。

当前不需要新增公开数据集。若后续要做更接近演示现场的真实 UI 手动测试，只需要用浏览器麦克风录一两句，不需要把录音提交到仓库。

### 2026-06-05 真实试用反馈与可执行计划 v3

当前可运行基线已打 tag：

- `v0.1.0-demo-baseline`：指向 `c727379`，记录“基本能跑起来”的版本。包含场景选择、浏览器录音、faster-whisper ASR、LLM 回复、语法纠错、Read Aloud 发音评测入口、summary/progress、默认/真实 smoke report。

用户真实试用反馈：

1. **时延过高**
   - 现象：说一句后整体回复需要约 `5-10s`，用户体验不够好。
   - 需要检查后端调用链：ASR、LLM 对话回复、LLM 语法纠错、腾讯云发音评测是否串行等待。
   - 期望：主路径优先返回 AI 回复；mistakes、语法纠错、发音分析等学习反馈可以异步逐步出现，哪个完成先展示哪个，不要阻塞对话。

2. **界面需要简化**
   - 现象：当前左/中/右三栏偏复杂。
   - 期望：去掉左侧 scenario 栏，把场景选择放到 Conversation 栏顶部，作为选择框：`Job Interview` / `Restaurant Ordering` / `Work Meeting` / 自选。
   - Start 和 End 合并为 Conversation 顶部的同一个会话按钮：未开始时显示 `Start`，点击后创建会话并变成 `End`；点击 `End` 结束会话后再变回 `Start`。

3. **AI 回复朗读声音生硬**
   - 现象：浏览器 `speechSynthesis` 声音不像真人，听感不流畅。
   - 期望：替换更自然的 TTS，优先真实云 TTS 或更自然的浏览器 voice 选择策略；同时保留 browser fallback。

4. **Read Aloud 腾讯云发音评测鉴权失败**
   - 现象：右侧 `Record Reading` 返回“腾讯云发音评测鉴权失败，请检查密钥和签名配置”。
   - 需要单独做腾讯云发音评测诊断：签名参数、音频格式、评测模式、账号权限、请求 URL、服务区域/产品权限。

5. **对话区要改成聊天软件样式**
   - 现象：对话变长后展示不理想。
   - 期望：Conversation 区固定尺寸，消息像微信/QQ 气泡，默认显示最近几条，可上滑查看历史；容器高度随浏览器大小适配但整体不撑爆页面。

同时保留之前未完成的重要增强：

- 真正流式 ASR partial / VAD 自动断句。
- 自由对话每轮可选自动发音评测。
- L2-ARCTIC 口音 ASR / 误音检测评测。
- 自动浏览器 E2E smoke。
- 更细的场景目标状态机。
- 更完整的真实服务延迟报告，包括浏览器端 TTS start 和 UI 端分段耗时。

#### v3 优先级和 PR 切分

1. **PR-L1：后端对话链路分段计时与调用关系审计**
   - 目标：明确当前一轮语音从 `end_turn` 到 `reply.text` 的真实耗时组成。
   - 实现：
     - WS 每轮记录 `audio_save_ms`、`transcode_ms`、`asr_ms`、`dialogue_llm_ms`、`grammar_ms`、`reply_emit_ms`。
     - 将 timing 通过 `debug.timing` WS 事件和真实 smoke report 输出。
     - 日志不包含用户 key、secret、完整 base URL。
   - 测试：
     - 默认 fake provider 测 timing 字段存在且数值合法。
     - 真实 smoke 记录 ASR/LLM 分段耗时。

2. **PR-L2：对话主路径优先，语法/错题异步旁路**
   - 目标：降低首个 AI 回复等待时间。
   - 实现：
     - WS `end_turn` 后顺序只保留：保存音频 -> ASR final -> 生成 AI reply -> 立即发 `reply.text`。
     - grammar correction、mistake generation、summary store 放入后台 task，完成后发 `analysis.result`。
     - 若 grammar 失败，只发 `analysis.error`，不影响已返回的 AI 回复。
   - 测试：
     - Fake grammar 延迟时，`reply.text` 必须先于 `analysis.result` 到达。
     - provider 报错仍写入 session analysis。

3. **PR-L3：LLM 对话回复流式输出**
   - 目标：进一步降低感知延迟。
   - 实现：
     - OpenAI-compatible client 增加 streaming adapter。
     - WS 新增事件：`reply.delta`、`reply.done`。
     - 前端边收到边展示 AI 气泡文本；`reply.done` 后再触发 TTS。
     - 这里的流式是“返回流式”：请求仍一次发送当前 session 上下文和本轮用户文本，服务端逐段返回模型输出。
     - FakeLLMClient 保持确定性 streaming 测试。
   - 测试：
     - fake streaming 多段 delta 顺序合并成最终 turn。
     - 非 streaming provider fallback 到现有 `reply.text`。

4. **PR-L4：腾讯 SOE 单独诊断脚本与签名修复**
   - 目标：解决 Read Aloud 鉴权失败。
   - 实现：
     - 新增或增强 `scripts/test_tencent_soe.py --verbose-safe`，输出脱敏后的签名参数摘要、voice_format、engine、eval_mode、音频采样率检查结果、错误分类。
     - 校验腾讯 SOE URL path、appid 拼接、query 排序、signature encode、`ref_text` 编码。
     - 用 SpeechOcean fixture WAV 做固定诊断；不使用浏览器录音作为第一步。
   - 测试：
     - 默认测试 mock 鉴权错误、签名错误、音频格式错误映射。
     - 手动真实 smoke：腾讯 SOE fixture assessment passed 后再接 UI。

5. **PR-L5：TTS provider 抽象与自然声音**
   - 目标：替换生硬浏览器朗读。
   - 实现：
     - 后端新增真实 TTS provider adapter（优先腾讯云 TTS 或 OpenAI-compatible TTS，取决于可用账号）。
     - 前端优先播放后端返回音频 URL/base64；失败回退 `speechSynthesis`。
     - browser fallback 增加 voice 选择：优先英文、自然度较高、语速 `0.92-0.98`。
   - 测试：
     - provider fallback 单测。
     - 前端 mock 音频播放和 browser fallback。

6. **PR-U1：布局简化为两栏**
   - 目标：去掉左侧 scenario 栏。
   - 实现：
     - Conversation 顶部增加 scenario select。
     - Conversation 顶部增加一个会话状态按钮：`Start` / `End` 复用同一位置和控件，避免左栏 Start 与中栏 End 分散。
     - 支持 `custom` 自选场景入口：第一版可作为文本输入生成临时 scenario，或先展示 disabled/coming state 但不破坏现有三场景。
     - Coach 保持右栏；移动端仍单列。
   - 测试：
     - 选择不同 scenario 后新 session 使用对应场景。
     - Start 后按钮文案变为 End；End 后 session 结束、按钮文案变回 Start。
     - 新 session 清理旧状态。

7. **PR-U2：聊天气泡与固定滚动对话区**
   - 目标：对话像微信/QQ，长对话不撑爆页面。
   - 实现：
     - `.message-list` 固定高度：基于 viewport 的 `clamp()` 或 grid/flex 剩余空间。
     - AI 左侧气泡、用户右侧气泡。
     - 新消息默认滚到底部；用户可上滑看历史。
     - 文本长句 `overflow-wrap:anywhere`，按钮和输入区固定尺寸。
   - 测试：
     - 前端测试消息追加后仍渲染最新消息。
     - 可选 Playwright 截图检查 desktop/mobile 不重叠。

8. **PR-L6：自由对话发音评测可选异步任务**
   - 目标：普通语音对话也能评估发音，但不能阻塞回复。
   - 实现：
     - 每个 audio turn 可配置是否触发 pronunciation task。
     - 默认可先只对短音频启用；超长音频跳过并提示。
     - 腾讯 SOE 不进入主链路实时路径；按完整录音异步评测即可，不要求流式传输或实时中间结果。
     - 结果通过 `analysis.result stage=pronunciation` 进入 Coach 和 mistakes。
   - 测试：
     - Fake provider 验证 reply 先返回，pronunciation 后返回。

9. **PR-E2E：浏览器自动 smoke**
   - 目标：减少人工回归成本。
   - 实现：
     - 引入 Playwright 前先更新 README/plan 说明用途。
     - 使用 fake/mock provider 环境，mock 麦克风或使用 fixture 音频。
     - 验证：进入页面 -> start session -> 发送文本或模拟音频 -> AI 回复 -> summary。
   - 测试：
     - 默认可选，不阻塞 `make test`；CI 或手动命令显式运行。

10. **PR-Eval2：口音/误音评测**
    - 目标：补原计划中的 L2-ARCTIC 口音 ASR 和误音检测。
    - 实现：
      - faster-whisper 在 L2-ARCTIC subset 上计算 WER。
      - 初版误音检测先从 TextGrid 标注生成可解释报告，不直接影响实时 UI。
    - 测试：
      - integration marker，默认 skip。

#### v3 验收标准

- 首个 AI 回复感知延迟目标：`end_turn -> reply first token` 小于 `2.5s`（真实 ASR 仍可能受模型影响，先以分段报告定位瓶颈）。
- `reply.text` 或 `reply.delta` 必须早于 grammar/pronunciation analysis 结果。
- Read Aloud 腾讯 SOE fixture smoke 必须 passed，UI 才算发音评测可用。
- Conversation 页面改为两栏，场景选择在 Conversation 顶部。
- 对话区固定高度、气泡样式、默认滚动到底部。
- TTS 听感优先使用真实 provider 或更自然 browser voice，不再只依赖默认系统朗读。
- 默认 `make test` 仍离线稳定；真实服务测试只显式运行。

#### v3 执行记录

| 提交 | 对应计划 | 状态 | 说明 |
|---|---|---|---|
| `1700f51` | PR-L1 | 已完成第一步 | WS 语音回合新增 `debug.timing`，覆盖音频写入、转码、ASR、对话回复、语法分析耗时；ASR 错误路径也返回 timing。 |
| `5066aa5` | PR-L2 | 已完成第一步 | 语音回合 `reply.text` 返回后异步执行 grammar/mistake 分析；前端收到回复后立即恢复录音按钮。 |
| `317b783` | PR-L4 | 已完成诊断入口 | `scripts/test_tencent_soe.py --verbose-safe` 输出脱敏签名和音频诊断；SpeechOcean fixture 真实 Tencent SOE smoke 已通过。 |
| `0180256` | PR-U1 | 已完成第一步 | UI 从三栏改为 Conversation + Coach 两栏；scenario select 移到 Conversation 顶部；Start/End 合并为一个按钮。 |
| `b60bfed` | PR-U2 | 已完成第一步 | Conversation 消息区改为固定高度滚动容器，AI/用户左右气泡展示，新消息自动滚到底部。 |
| `cf52215` | PR-L5 | 已完成 browser fallback 优化 | 浏览器 TTS 优先选择英文自然 voice，设置 `rate=0.94`、`lang=en-US`；真实云 TTS provider 仍待后续。 |
| `050a973` | PR-L1 | 已完成前端展示 | 前端 Coach 面板显示最近一轮 ASR、Reply、Grammar、Total timing，便于现场定位延迟瓶颈。 |
| `fce3f62` | 测试维护 | 已完成 | 更新 analysis WebSocket 测试以覆盖新增 timing 事件顺序。 |
| `6806cbe` | PR-L3 | 已完成第一步 | LLM client、DialogueService、WS 和前端支持 `reply.delta` / `reply.done`；fixture/fallback 仍可走 `reply.text`。 |
| `5503eaa` | PR-L6 | 已完成第一步 | 普通语音回合可异步触发发音评测，回复先返回，pronunciation 结果后到达 Coach/Mistakes。 |
| `b4f452c` | PR-L5 | 已完成云 TTS 入口 | 新增 OpenAI-compatible TTS provider，前端优先播放后端音频，失败回退浏览器 TTS。 |
| `90a63ca` | PR-Eval2 | 已完成第一步 | 默认评测报告增加 L2-ARCTIC native language 分布和手工标注覆盖率；真实口音 ASR/误音命中仍待后续。 |
| `5242501` | PR-E2E | 已完成 | 新增 Playwright UI smoke，显式覆盖进入页面、Start、文本回合、End 和 Summary；不加入默认 `make test`。 |
| `bceb3c2` | PR-U1 | 已完成 custom 入口 | Scenario 下拉框的 `Custom` 已可用，用户输入主题后创建临时 scenario；后续 turn、summary、progress 都能解析。 |
| `a4705c6` | PR-Eval2 | 已完成真实 ASR smoke 第一版 | 真实 smoke report 增加少量 L2-ARCTIC 口音 ASR 抽测，记录平均 WER 和耗时；默认 fake 模式不访问真实 ASR。 |
| `7647e94` | PR-Eval2 | 已完成 TextGrid readiness | 默认 eval report 增加 L2-ARCTIC TextGrid 可用性和解析统计；当前 fixture 包未携带原始 TextGrid，hit rate 明确标为 not computed。 |
| `de74508` | PR-L1 | 已完成前端 TTS timing | Coach timing 面板新增 `reply -> TTS start`，合并浏览器端播放启动耗时与后端分段计时。 |
| `261e3e8` | PR-L3/VAD | 已完成自动断句第一版 | 浏览器录音端通过 Web Audio RMS 检测“说话后持续静音”，自动 stop 并发送 `end_turn`；不支持 Web Audio 时仍保留手动 Stop。 |
| 当前修改 | PR-UX/VAD | 已改为手动结束 | 面向初学者，去掉浏览器 VAD 自动断句，语音回合完全由用户点击 Record/Stop 判断开始和结束。 |

### 2026-06-05 主链路和 provider 决策确认

最终主链路确认如下：

```text
浏览器录音 -> 用户点击 Stop/end_turn -> 整句 ASR -> LLM 流式返回/展示 -> 朗读
                         -> 语法纠错/发音评测/错题生成异步补充
```

| 模块 | 决策 | 原因 |
|---|---|---|
| ASR | 保持按轮整句识别 | 本地 faster-whisper 真流式 partial 会增加重复推理、GPU 占用和延迟抖动；对当前对话体验，用户说完一句再识别是合理边界。 |
| LLM 回复 | 只要求返回流式 | AI 回复是用户等待感最强的部分；请求仍一次发送上下文和本轮文本，返回端用 `reply.delta` / `reply.done` 逐步展示。 |
| TTS | `reply.done` 后朗读 | 逐 token 朗读会碎，当前 Edge/Chrome 的 browser TTS 可用于演示；后续若要更快，优先做句子级缓冲朗读。 |
| 语法纠错 | 旁路异步 | 纠错是学习反馈，不应阻塞对话回复。 |
| 腾讯 SOE 发音评测 | 旁路异步整段评测 | 发音错误反馈不需要实时；按完整录音评测更简单稳定，也避免把腾讯 SOE 放进主链路。 |

当前仍待继续：

- 真正连续流式 ASR partial 明确不作为当前目标；当前采用用户手动 Stop 后 `end_turn`，再整句识别，避免初学者停顿思考时被自动截断。
- PR-L5 后续：真实云 TTS 代码入口已完成；当前 browser TTS 在 Edge/Chrome 下听感可接受，演示避免使用 QQ 浏览器。
- PR-Eval2 后续：完整 TextGrid 误音命中率需要原始 L2-ARCTIC TextGrid 文件和一个实时误音 detector；当前默认报告只统计 readiness，避免假算。
- 更细的场景目标状态机仍未做，当前 custom scenario 是主题驱动的临时场景。
- 截图级 UI 视觉回归可继续增强；当前已有功能型 Playwright smoke。

### 2026-06-05 UI 精简与错题本入口计划（待确认后执行）

> 说明：本节只记录待执行计划，尚未改 UI。执行前需用户明确确认。

#### 目标

当前页面是左侧 Conversation、右侧 Coach 信息栏。下一步目标是减少演示时的调试/工程痕迹，让右侧反馈更像学习产品：

- 顶部品牌和对话区说明更简洁。
- 发音评测、纠错、错误提示、总结的层级更清楚。
- Timing 不再占用大块视觉空间，仅作为底部浅色调试信息。
- Mistakes 不在右栏直接展开，改成“错题本”入口和独立视图。
- Progress 暂时从主界面隐藏或弱化，避免和当前会话反馈混在一起。

#### 计划

1. **页面标题和顶部清理**
   - `frontend/index.html`：浏览器标题从 `XEngineer Speaking Coach` 改为 `Speaking Coach`。
   - 页面顶部去掉 `XEngineer` eyebrow。
   - 主标题建议改为 `Speaking Coach`。
   - 对话框上方的 `selectedScenario.user_role`（如 `Candidate`）去掉。
   - 保留 `Conversation` 标题、场景选择、Start/End。

2. **对话区精简**
   - 删除 `scenario-strip` 中展示的 conversation goals 胶囊。
   - 保留：
     - 场景选择。
     - Start/End。
     - 对话历史。
     - 文本输入。
     - 录音按钮。
     - partial 识别提示。

3. **Read Aloud 模块明确命名**
   - 当前 Read Aloud/Record Reading 是“指定句跟读发音评测”，不是自由对话识别。
   - 在右栏给它一个和 `Correction`、`Timing` 同级的小标题，建议命名为 `Pronunciation`。
   - 结构建议：
     - `Pronunciation`
     - 参考句：`THEN HE WENT TO THEME PARK`
     - 按钮：`Record Reading`
     - 结果区：
       - `Overall`
       - `Accuracy`
       - `Fluency`
       - `Low-score words`，低于 60 分的词标红。
   - 注意：标红表示腾讯 SOE 给该词的准确度低，不严格等同于“读错”。

4. **Timing 降级为底部浅色文本**
   - 不再使用大的 `coach-block`。
   - 放到 Coach 右栏最底部。
   - 小号、浅灰、低优先级显示，例如：

     ```text
     Timing: ASR 820ms · Reply 1400ms · Grammar 600ms · Pronunciation 1200ms · TTS 80ms
     ```

   - 没有 timing 数据时不显示。

5. **Mistakes 改成独立“错题本”视图**
   - 不在右栏直接展示错题列表。
   - 右栏只保留入口按钮/链接：
     - `Mistake Book`
     - 可显示数量：`Mistake Book (3)`。
   - 点击后切换到独立视图；第一版可用 React state 实现，不必新增路由：

     ```text
     mainView = "practice" | "mistakes"
     ```

   - 错题本视图内容：
     - 标题：`Mistake Book`
     - 返回按钮：`Back to Practice`
     - 错题列表。
     - 每条展示：
       - 类型：grammar / expression / pronunciation。
       - 错误内容。
       - 正确表达。
       - 中文解释。
       - Review 按钮。
   - 当前后端 `/api/mistakes` 是全局错题，不是严格按 session 过滤。第一版先展示现有错题；若要“只显示本次会话错题”，后续需给 mistake 加 session 关联，或前端在会话开始时记录 baseline 后只展示新增项。

6. **Progress 处理**
   - `Progress` 当前表示跨会话历史进度，如完成 session 数、平均语法分、平均发音分。
   - 它和当前会话即时反馈关系不强，演示时解释成本高。
   - 建议先从右栏主界面隐藏。
   - 后续如做“学习报告 / 历史记录”页面，再把 Progress 放进去。

7. **右栏最终结构建议**
   - `Pronunciation`
   - `Correction`
   - `Issues`（仅出错时显示）
   - `Summary`（结束会话后显示）
   - `Mistake Book` 入口
   - 底部浅色 `Timing: ...`

8. **测试计划**
   - 更新前端测试，覆盖：
     - 页面标题为 `Speaking Coach`。
     - 顶部不再出现 `XEngineer`。
     - 对话区不再显示 `Candidate`/user role 和 conversation goal 胶囊。
     - 发音评测区有 `Pronunciation` 小标题。
     - Timing 以底部浅色文本出现，而不是大块面板。
     - Mistakes 不直接出现在右栏，点击 `Mistake Book` 后进入错题本视图。
   - 执行：

     ```bash
     cd frontend && npm test -- --run
     ```

   - 手动检查：
     - 首页顶部没有 `XEngineer`。
     - 对话区没有 `Candidate` 和 goal 胶囊。
     - 发音评测区有 `Pronunciation` 标题。
     - Timing 只在底部浅色显示。
     - Mistakes 不直接出现在右栏，点击入口进入错题本视图。

### 2026-06-05 固定应用式布局与对话真实感优化计划

> 说明：本节基于上一轮 UI 精简后的进一步计划。目标是让页面更像一个固定高度的应用界面，而不是普通网页向下撑开。

#### 目标

- 左侧对话框减少 UI 标签感，提升真实对话感。
- 右侧 Coach 信息更紧凑，不让分数和 timing 抢占空间。
- 点击 Start 后 AI 开场白也要朗读，和后续 AI 回复行为一致。
- 浏览器页面本身不滚动；左侧消息区和右侧 Coach 栏各自内部滚动。
- End 后 Summary 变多时不拉长左侧对话框。

#### PR 拆分

1. **PR-UI-A：精简对话区 chrome**
   - 功能描述：
     - 去掉左侧顶部 `Conversation` 标题。
     - 去掉消息气泡中的 `AI` / `You` 标签。
     - 点击 Start 后自动朗读后端返回的 opening line。
   - 实现思路：
     - 删除 conversation toolbar 中的标题节点，仅保留 Scenario 选择与 Start/End。
     - 删除 message speaker `<span>` 渲染和对应 CSS。
     - `startSession()` 成功后从 `body.opening_line` 或第一条 AI turn 取文本，调用现有 `speak()`。
   - 测试方式：
     - 前端测试断言不显示 `Conversation`、`AI`、`You` 标签。
     - 前端测试断言 Start 后 `speechSynthesis.speak` 被调用，且文本为 opening line。
     - 执行 `cd frontend && npm test -- --run`。

2. **PR-UI-B：压缩 Coach 反馈展示**
   - 功能描述：
     - Pronunciation 中 `Overall` / `Accuracy` / `Fluency` 改为一行紧凑展示。
     - Timing 改为底部弱化多行格式：

       ```text
       Timing:
         ASR xxx ms
         Reply xxx ms
         Grammar xxx ms
         Pronunciation xxx ms
         TTS xxx ms
       ```

   - 实现思路：
     - 用 compact score row 替代 pronunciation 的三行 `dl`。
     - `formatTimingRows()` 返回有值的 timing 项，JSX 渲染为小号浅色列表。
   - 测试方式：
     - 前端测试断言 pronunciation 分数存在于 compact 区域。
     - 前端测试断言 Timing 显示多行文本，且不作为大块 `coach-block` 标题。
     - 执行 `cd frontend && npm test -- --run`。

3. **PR-UI-C：固定页面高度和内部滚动**
   - 功能描述：
     - 桌面端浏览器页面本身保持一屏，不因对话、Summary 或 Issues 增多而整体滚动。
     - 左侧消息区内部滚动，Send/Record 始终可见。
     - 右侧 Coach 栏内部滚动，不拉长左侧对话框。
   - 实现思路：
     - `body` / `#root` / `.app-shell` 使用 `height: 100vh`，桌面端 `overflow: hidden`。
     - `.app-shell` 使用 flex column，`.workspace` 占满剩余高度并设置 `min-height: 0`。
     - `.conversation-panel` 和 `.coach-panel` 高度受 workspace 约束。
     - `.message-list` 使用 `flex: 1; min-height: 0; overflow-y: auto`。
     - `.coach-panel` 使用 `overflow-y: auto; min-height: 0`。
     - 移动端恢复普通文档流或降低固定限制，避免两栏堆叠后高度过小。
   - 测试方式：
     - 前端测试继续覆盖核心交互。
     - 手动检查桌面端：
       - 页面本身不滚动。
       - 左侧消息区可独立滚动。
       - 右侧 Coach 可独立滚动。
       - End 后 Summary 不拉长左栏。
     - 执行 `cd frontend && npm test -- --run`。

#### 验收标准

- 页面顶部和对话区没有多余的 `Conversation`、`AI`、`You` 文本标签。
- Start 后第一句开场白会朗读。
- Pronunciation 分数紧凑显示在一行。
- Timing 是底部浅色多行调试文本。
- 桌面浏览器页面本身不需要滚动；只允许消息区和 Coach 栏内部滚动。
- 小屏下仍能正常访问内容，不因固定高度导致不可用。
