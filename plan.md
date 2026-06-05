# AI 英语口语陪练实现计划

## Summary

采用 **React/Vite + Python FastAPI**。后端优先，所有核心能力都按“输入 -> 输出”做可测试服务；前端只做简单网页接入。实时语音采用 **WebSocket 音频流通道 + 本地 faster-whisper ASR + 文本回复**，发音评测先做 **统一接口 + Mock provider**，后续再小 PR 接腾讯云/讯飞/Azure。

默认原则：

- 实时主链路只负责：录音、ASR、生成回复、展示回复。
- 学习分析旁路异步负责：语法纠错、表达优化、发音评测、课后总结、错题本。
- 测试默认不依赖前端、不依赖真实 LLM、不依赖真实发音云服务。
- 所有真实外部服务都通过 adapter 接入，测试使用 fake/mock。

## Implementation PRs

1. **PR 1：项目骨架与测试框架**
   - 建立 `backend/` FastAPI、`frontend/` React/Vite、`tests/`、`fixtures/`。
   - 后端使用 `pytest`、`httpx TestClient`；前端使用 `vitest`，后续再加 Playwright smoke。
   - 增加 `.env.example`，包含 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`ASR_MODEL_SIZE`、`PRON_PROVIDER=mock`。
   - 增加统一命令：`make test-backend`、`make test-frontend`、`make dev-backend`、`make dev-frontend`。

2. **PR 2：核心数据模型与 Schema**
   - 定义 Pydantic 模型：`Scenario`、`Session`、`Turn`、`GrammarCorrection`、`PronunciationAssessment`、`SessionSummary`、`MistakeItem`。
   - 每个模型提供 JSON Schema，测试校验示例 fixture 能 parse。
   - 输出结构固定，后续 LLM/云服务都必须转成这些内部模型。

3. **PR 3：场景配置系统**
   - 增加 `interview`、`restaurant_ordering`、`meeting` 三个场景配置。
   - 每个场景包含：AI 角色、用户角色、开场白、对话目标、目标表达、纠错重点、总结评分规则。
   - 实现 `GET /api/scenarios` 和 `POST /api/sessions`。
   - 测试：场景配置合法、创建 session 后返回开场白和目标信息。

4. **PR 4：LLM 统一客户端**
   - 实现 OpenAI-compatible LLM adapter：通过 `base_url/api_key/model` 配置。
   - 实现 `FakeLLMClient`，测试默认使用 fake，不访问网络。
   - 增加结构化 JSON 调用工具：解析失败时重试一次，仍失败则返回可记录错误。
   - 测试：fake 响应、JSON 解析、无效 JSON fallback。

5. **PR 5：语法/表达纠错服务**
   - 输入：`scenario_id`、`user_text`、`conversation_context`。
   - 输出：原句、纠正句、更好表达、错误列表、严重程度、中文解释、建议纠错时机。
   - 纠错原则：不把自然口语强行改成书面作文，不改变用户原意。
   - API：`POST /api/grammar/check`。
   - 测试：用 20 条小 fixture 校验输出 schema、span 存在于原文、严重错误能被识别。

6. **PR 6：场景化对话回复服务**
   - 输入：session 状态、上一轮用户文本、场景配置。
   - 输出：AI 回复文本、当前对话目标、下一步追问意图。
   - 对话回复不做长篇教学纠错，只负责继续自然对话。
   - API：`POST /api/sessions/{id}/turns/text`，用于后端测试和前端文本 fallback。
   - 测试：面试/点餐/会议三类场景能生成符合角色的回复。

7. **PR 7：SQLite 会话日志**
   - 使用 SQLite 存 session、turn、correction、pronunciation assessment、mistake item。
   - 本地 demo 使用单用户模式，不做登录。
   - 测试使用临时 SQLite，确保不污染开发数据库。
   - 测试：创建 session、写入 turn、关联纠错结果、查询历史会话。

8. **PR 8：WebSocket 音频流与本地 ASR**
   - 前端通过 WebSocket 发送音频 chunks，用户点击停止后发送 `end_turn`。
   - 后端保存本轮音频，调用 faster-whisper 转写，返回 `asr.final` 和 AI 回复文本。
   - 这是“流式传输 + 按轮识别”，第一版不做连续 VAD 自动断句。
   - API：`WS /ws/sessions/{id}/audio`。
   - 测试：默认用 `FakeASR`，校验 WebSocket 事件流；真实 faster-whisper 测试标记为 integration，可跳过。

9. **PR 9：发音评测统一接口与 Mock provider**
   - 输入：`reference_text`、用户跟读音频。
   - 输出：overall、accuracy、fluency、prosody、word scores、phoneme scores、issue。
   - 第一版 provider 为 mock，按 fixture 返回确定性结果。
   - API：`POST /api/pronunciation/assess`。
   - 测试：mock 结果转内部模型、低分单词生成发音错题。

10. **PR 10：错题本**
    - 从语法纠错、表达优化、发音评测中自动生成错题。
    - 错题类型：`grammar`、`expression`、`pronunciation`。
    - 字段包含：错误表达、正确表达、解释、练习句、单词、音标、掌握度、复习次数。
    - API：`GET /api/mistakes`、`POST /api/mistakes/{id}/review`。
    - 测试：重复错误合并、复习次数更新、掌握度变化。

11. **PR 11：课后总结**
    - 输入：完整 session log。
    - 输出：语法、发音、流利度、词汇、场景任务完成度分数，以及 top issues 和 next drills。
    - 总结从已有结构化结果聚合，不重新依赖自由文本猜测。
    - API：`GET /api/sessions/{id}/summary`。
    - 测试：fixture session 能生成稳定 summary，缺少发音评测时也能返回部分总结。

12. **PR 12：简单网页端**
    - 页面包含：场景选择、对话区、录音按钮、侧边栏纠错、跟读练习、课后总结、错题本。
    - 前端通过 REST/WS 调后端，不包含核心业务逻辑。
    - AI 回复第一版显示文本；可加浏览器 `speechSynthesis` 播放回复作为轻量语音输出。
    - 测试：前端组件 smoke test；后端 fake 模式下跑一条端到端 Playwright smoke。

13. **PR 13：评测与报告生成**
    - 增加 `backend/eval`，读取 fixture 数据生成量化报告 JSON/Markdown。
    - 指标包括：ASR WER、语法纠错 schema 通过率、纠错命中率、发音 mock/真实 provider 返回率、会话端到端耗时、课后总结成功率。
    - 真实外部服务评测单独标记，不影响默认 CI。
    - 输出：`reports/latest.md`，用于黑客松最终报告素材。

14. **PR 14：真实发音云服务适配器**
    - 在 Mock provider 稳定后再接真实服务。
    - 优先顺序：腾讯云或讯飞，取决于你准备的账号配置。
    - 只做 provider adapter，不改业务层。
    - 测试：contract test 使用录制/脱敏 fixture；无 key 时自动 skip。

## Public Interfaces

后端主要 API：

- `GET /api/scenarios`
- `POST /api/sessions`
- `POST /api/sessions/{id}/turns/text`
- `WS /ws/sessions/{id}/audio`
- `POST /api/grammar/check`
- `POST /api/pronunciation/assess`
- `GET /api/sessions/{id}/summary`
- `GET /api/mistakes`
- `POST /api/mistakes/{id}/review`

WebSocket 第一版事件：

- Client：`start_turn`
- Client：binary audio chunk
- Client：`end_turn`
- Server：`asr.final`
- Server：`reply.text`
- Server：`analysis.pending`
- Server：`error`

## Test Plan

默认测试不需要真实外部服务：

- **模型层测试**：Pydantic schema parse、必填字段、枚举合法性。
- **服务层测试**：grammar、dialogue、pronunciation、summary、mistake book 都使用 fake client。
- **API 测试**：FastAPI TestClient 调 REST；WebSocket 使用 fake ASR。
- **数据库测试**：临时 SQLite，验证 session/turn/correction/mistake 写入和查询。
- **评测脚本测试**：读取小 fixture，生成固定格式报告。
- **集成测试**：真实 LLM、真实 faster-whisper、真实发音云服务均通过 env 开启，默认 skip。

你需要准备的数据：

- 20 条语法/表达错误文本，包含原句、期望纠正句、错误类型。
- 10 条场景对话样例，覆盖面试、点餐、会议。
- 5-10 段短英语录音及人工转写，用于 ASR smoke test。
- 10 条跟读句和对应录音，用于后续真实发音评测。
- LLM 的 OpenAI-compatible 配置：`base_url`、`api_key`、`model`。
- 后续真实发音云服务配置：腾讯云或讯飞的 key/appid/region 等。

## Assumptions

- 技术栈固定为 React/Vite + Python FastAPI。
- 第一版是单用户本地 demo，不做账号系统。
- ASR 第一版用本地 faster-whisper；测试默认用 FakeASR。
- AI 回复第一版以文本展示为主，可用浏览器 TTS 轻量播放。
- 发音评测第一版只做统一接口和 Mock provider，真实云服务单独 PR 接入。
- 后端能力必须先能通过纯输入输出测试，再接前端。
