# AI 英语口语陪练实现计划

## Summary

采用 **React/Vite + Python FastAPI**。后端优先，所有核心能力都按“输入 -> 输出”做可测试服务；前端只做简单网页接入。实时语音采用 **WebSocket 音频流通道 + 本地 faster-whisper ASR + 文本回复（可加轻量 TTS）**，发音评测先做 **统一接口 + Mock provider（用 speechocean762 真值分回放）**，后续再小 PR 接腾讯云/讯飞/Azure。

默认原则：

- 实时主链路只负责：录音、ASR（partial/final）、生成回复、展示回复。
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
- **TTS 音质 / 端到端听感**：人工听 AI 回复语音是否可懂、延迟是否可接受。
- **partial 体验**：说话时确认中间转写实时滚动。

## Assumptions

- 技术栈固定为 React/Vite + Python FastAPI。
- 第一版是单用户本地 demo，不做账号系统。
- ASR 第一版用本地 faster-whisper；测试默认用 FakeASR，真实跑用 librispeech/l2_arctic 评测。
- AI 回复第一版以文本为主，浏览器 TTS 轻量播放；真实 TTS 云为可选 PR。
- 发音评测第一版只做统一接口 + Mock provider（speechocean762 真值回放），**仅跟读模式**，真实云与自由发言评测单独 PR。
- 所有云服务错误以 `AnalysisError` 就地非弹窗展示并自动降级，不中断主对话。
- 后端能力必须先能通过纯输入输出测试，再接前端。
