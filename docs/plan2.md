# 对话流式、场景资料与界面升级实现计划

## 目标

本计划覆盖三项改进：

1. 对话区体验修正：ASR 完成后用户回复立即出现在 conversation 区；AI 回复在 conversation 区流式出现。Conversation Assessment 仍保持非流式，等语法、表达、发音结果完整返回后再展示。
2. 场景已知信息：所有场景都支持填写背景资料，并支持 PDF 上传。资料会作为 AI 已知背景，让面试官、服务员、会议主持等角色从一开始就掌握用户提供的信息。
3. UI 升级：`ui1.png` 和 `ui2.png` 只作为竞品观察，用来识别“对话主次、场景资料承载、状态标签”等问题，不直接复刻它们的版式、颜色或组件风格。最终界面要形成 Fluent Coach 自己的视觉语言：像一个专注的口语训练工作台，对话区是主舞台，纠错和阅读练习是辅助 coach rail。

执行原则：

- 每个 PR 只做一件事，功能按小步提交。
- 每个 PR 都必须补测试；能自动测的必须自动测，不能自动测的写进手动检查清单。
- 先改行为正确性，再改数据能力，最后改视觉。避免 UI 大改掩盖链路问题。
- 不让语法、表达、发音评测阻塞主对话。
- 新增的场景资料面板必须能展开和收起；收起后只保留简短摘要和重新打开入口。
- UI 不能照搬竞品。竞品图只用于提炼信息层级和交互需求；视觉表达、布局比例、色彩系统、组件形态要重新设计。

## 当前问题定位

### 对话流式

相关文件：

- `backend/app/main.py`
- `backend/app/services/dialogue.py`
- `frontend/src/App.jsx`
- `tests/backend/test_audio_websocket.py`
- `tests/backend/test_ws_itl.py`
- `frontend/src/App.test.jsx`

当前后端 WebSocket 已经有 `asr.final`、`reply.delta`、`reply.done` 事件，但实际表现不稳定：

- 音频链路里，后端先发 `asr.final`（`backend/app/main.py:541`），此时只带 `text`，没有 `user_turn_id`；真实 user turn 要等 reply 生成那步才创建（非流式 `main.py:550`、流式 `main.py:570`）。
- 命中 fixture reply 时，`DialogueService.generate_reply_stream()` 返回 `None`，后端走 `reply.text`（`main.py:559`），AI 回复一次性展示。
- fallback reply 也会一次性返回。
- 文本发送仍走 REST `POST /api/sessions/{id}/turns/text`，天然是一次性返回完整 session。

**现状校准（避免重复造轮子）：**

- 前端 `App.jsx` 已经实现了完整的流式渲染链路：`reply.delta` 增量拼接（`upsertTurnText`，`App.jsx:896-909`）、`reply.done` 用服务端 id 替换本地 streaming turn（`replaceTurnIdAndText`，`App.jsx:910-929`）、`asr.final` 已读取 `message.user_turn_id` 并在缺失时 fallback 到本地临时 id（`App.jsx:861-878`）、`reconcileVoiceUserTurnId` 已做 turn id 对账与 corrections 重新 keying。
- 因此“AI 回复一次性出现”的**根因在后端**：fixture / 无 LLM 走 `reply.text` 一次性返回，以及 `asr.final` 不带 `user_turn_id`。前端**唯一缺失**的是 AI 首个 delta 之前的 typing 占位。
- 结论：本轮真正的工作量在 PR1（后端统一流式协议）；PR2 收窄为“typing 占位 + 测试 + 边界对账”。

因此需要把“用户 turn 创建”和“AI 回复流式输出”统一成稳定协议。

### 场景资料

相关文件：

- `backend/app/api.py`
- `backend/app/models/session.py`
- `backend/app/services/sessions.py`
- `backend/app/services/dialogue.py`
- `backend/app/services/custom_scenarios.py`
- `frontend/src/App.jsx`
- `frontend/src/App.test.jsx`

当前只有 custom scenario 有一个很小的 textarea，内置场景没有资料输入。后端也只有 `custom_prompt`，没有“已知信息/简历/场景资料”的持久化字段。

### UI

相关文件：

- `frontend/src/App.jsx`
- `frontend/src/styles.css`
- `frontend/e2e/smoke.spec.js`
- `frontend/src/App.test.jsx`

当前 UI 功能完整，但视觉层级偏弱：

- 对话、评估、阅读练习都像同权重的白色框。
- 对话区不像主舞台，辅助信息区抢占注意力。
- 场景选择区太小，无法承载“已知资料”和 PDF 状态。
- 错题本页面信息密度可以保留，但卡片与状态标签需要更清晰。

UI 升级的方向不是复制竞品，而是建立自己的产品气质：

- 产品关键词：专注、实时、教练感、练习场、可复盘。
- 视觉主线：conversation 是“练习舞台”，assessment 是“教练笔记”，briefing 是“场景资料夹”。
- 组件语言：气泡、资料夹、进度标签、语音波形/typing indicator、评分条可以形成统一识别，而不是简单 card 堆叠。
- 色彩策略：避免单一深色大屏或竞品的蓝紫科技感；使用克制的浅底工作台，加少量高对比 accent 标识交互状态。
- 布局策略：保留高效工作流，不做营销式 hero，不把页面做成纯场景大厅。

## PR 拆分

### PR1：后端统一音频 WebSocket 的 turn 创建与流式回复

目标：语音 ASR 一结束，后端立刻创建并保存 user turn，然后带 `user_turn_id` 发 `asr.final`。AI 回复无论来自 fixture、真实 LLM 还是 fallback，都通过 `reply.delta` / `reply.done` 输出。

代码改动：

- 在 `backend/app/main.py` 的 `/ws/sessions/{session_id}/audio` 中调整顺序：
  - ASR 得到 `transcript` 后立即 `session.add_turn(speaker=USER, ...)`。
  - `session_store.save(session)`。
  - 发送：
    ```json
    {
      "type": "asr.final",
      "text": "...",
      "user_turn_id": "..."
    }
    ```
  - 再生成 AI 回复。
- 去掉音频主路径中“reply 生成时才创建 user turn”的逻辑。
- 在 `backend/app/services/dialogue.py` 增加统一流式 helper：
  - fixture reply：先用现有逻辑拿到完整 reply 文本，再按词或短句切 chunk（fixture 是“伪流式”，文本一次拿全后分块发，仅为 UX 一致）。
  - LLM stream：直接透传 chunk。
  - fallback reply：按词或短句切 chunk。
- 把现在耦合在 `DialogueService.add_text_turns()` 里的“建 user turn + 建 AI turn + generate_reply”拆成可独立调用的原子函数（例如 `create_user_turn` / `stream_reply` / `commit_ai_turn`），让音频路径和后续 PR3 的文本 WebSocket 复用同一套，避免各写一份。`add_text_turns()` 作为兼容封装保留给 REST `/turns/text`。
- 后端音频 WebSocket 主路径统一发送：
  - `reply.delta`
  - `reply.done`
  - `debug.timing`
  - `analysis.pending`
  - 后续异步 `analysis.result` / `analysis.error`
- `reply.text` 暂时保留为兼容事件，但不作为新主路径。

必须处理的隐患（落地时容易踩）：

- **prompt 中 user 消息重复**：现在 `generate_reply_stream(..., user_text=transcript)` 是在 user turn 入库**之前**调用的，dialogue 用 `session.turns[-8:]` 再额外拼上 `user_text` 组 prompt。一旦把 user turn 前移到 `asr.final` 之前再生成回复，user 这句会同时出现在 `session.turns` 和 `user_text` 参数中，导致 LLM prompt 里 user 消息出现两次。**已定方案 B**（对 `DialogueService` 外部接口改动最小）：保留 `user_text` 参数，构造 history 时排除最后一条刚入库的 user turn（例如组 prompt 用 `session.turns[:-1][-8:]` 或显式跳过 `id == user_turn.id` 的那条），并写一条“user 这句在 prompt 中只出现一次”的断言测试。
- **audio_path 不丢**：前移创建 user turn 时仍要带 `mode="audio"`、`audio_path=str(stored_audio.preferred_path)`（`stored_audio` 在 ASR 之前已生成，可用）。
- **bench/driver 兼容**：除 `test_audio_websocket.py` / `test_ws_itl.py` 外，`tests/backend/test_ws_bench_driver.py`、`test_ws_bench_driver_grammar_tts.py` 以及 `scripts/` 下的 ws driver 很可能 assert 在 `reply.text` 上。本 PR 必须同步更新它们改读 `reply.delta` / `reply.done`，否则会回归失败。

测试：

- 更新 `tests/backend/test_audio_websocket.py`：
  - `asr.final` 必须包含 `user_turn_id`。
  - 收到 `asr.final` 后，后端 session 已经能查到该 user turn。
  - fixture reply 也必须产生至少一个 `reply.delta` 和一个 `reply.done`。
  - fallback reply 也必须产生 `reply.delta` / `reply.done`。
  - 慢 grammar 不影响 `asr.final` 和 `reply.delta` 的发送。
- 更新 `tests/backend/test_ws_itl.py`：
  - fixture/fallback/LLM stream 三种路径都记录 `reply_delta_count`。
  - `reply_first_delta_ms`、`reply_total_stream_ms` 字段稳定存在。
- 更新 `tests/backend/test_ws_bench_driver.py`、`tests/backend/test_ws_bench_driver_grammar_tts.py` 及 `scripts/` 下的 ws driver：改为消费 `reply.delta` / `reply.done`，不再依赖 `reply.text`。
- 新增 dialogue 层测试：拆分后的 `create_user_turn` / `stream_reply` / `commit_ai_turn` 各自可独立调用；验证前移 user turn 后 LLM prompt 中 user 这句**只出现一次**（防重复隐患）。
- 新增顺序测试（用**偏序**断言，不要求事件相邻，因为 `reply.done` 与 `analysis.pending` 之间还会插一条 `debug.timing`）：
  - `asr.final` 早于首个 `reply.delta`。
  - 首个 `reply.delta` 早于 `reply.done`。
  - `reply.done` 早于 `analysis.pending`。
  - 完整序列形如 `asr.partial* -> asr.final -> reply.delta* -> reply.done -> debug.timing -> analysis.pending`，但断言只检查上述先后关系。

验收：

- 语音 turn 的用户文本不再等 AI 回复一起出现。
- fixture 测试文本也能看到流式 AI 回复。

### PR2：前端 typing 占位与 asr.final 即时显示收尾

范围校准：`App.jsx` 的 delta/done 流式渲染、`upsertTurnText` / `replaceTurnIdAndText` / `reconcileVoiceUserTurnId` 已经存在（见“现状校准”）。本 PR **不是**从零做流式渲染，而是配合 PR1 的新协议补齐缺口并加测试。

目标：只改变 conversation 区展示节奏，不改变 Conversation Assessment 的非流式结果展示。

代码改动：

- 对接 PR1：`asr.final` 现在带 `user_turn_id`，音频路径直接用该 id 创建本地 user turn，不再依赖 `local-user-{ts}` fallback；并保证后续 `analysis.result` / `reply.done` 的 `user_turn_id` 与之一致。`reconcileVoiceUserTurnId` / 通用 reconcile helper **保留**——文本路径（PR3 用本地临时 id 再换服务端 id）和 `reply.text` 兼容事件仍需要它，只是音频主路径不再走它。
- 新增 typing 占位（当前缺失）：
  - ASR 完成、AI 尚未首个 delta：显示 `AI is thinking...` 或 typing indicator。
  - 收到首个 `reply.delta` 后移除。
- 复核已有去重逻辑在新协议下仍成立：
  - 如果 `asr.final` 的 `user_turn_id` 已存在，不重复插入。
  - `reply.done` 到达时不重复插入 AI turn。
- 保留 `reply.text` 兼容处理，但测试主路径改为 delta/done。
- `analysis.result`：维持现状，仍按 `turn_id` 写入 `turnCorrections` / `turnPronunciations`，不做流式展示。

测试：

- 更新 `frontend/src/App.test.jsx`：
  - 语音 stop 后，先出现用户 ASR 文本；此时 AI 回复可以还没出现。
  - 延迟发送 `reply.delta` 时，用户文本仍然已经显示。
  - 多个 `reply.delta` 会增量拼接成一个 AI 气泡。
  - `reply.done` 后本地 streaming turn id 被替换为服务端 id。
  - `analysis.result` 到达前，Conversation Assessment 仍显示 `No assessment yet.`。
  - `analysis.result` 到达后，Conversation Assessment 一次性显示纠错/发音结果。
- 增加回归测试：
  - `reply.text` 兼容事件仍可渲染。
  - `analysis.error` 不影响已显示的 conversation 气泡。

验收：

- 语音识别结束后，用户回复立即在左侧 conversation 主区出现。
- AI 回复逐字/逐块出现。
- Conversation Assessment 不出现半截纠错结果。

### PR3：文本发送也改成流式 AI 回复

目标：`Send` 文本和 `Record` 语音体验一致。用户点击 Send 后，用户文本立即显示；AI 回复流式出现；纠错结果完整返回后再进 Conversation Assessment。

推荐实现：

- 新增后端 WebSocket：`/ws/sessions/{session_id}/conversation`
- Client 事件：
  ```json
  {
    "type": "text_turn",
    "text": "..."
  }
  ```
- Server 事件：
  - `user.final`
  - `reply.delta`
  - `reply.done`
  - `debug.timing`
  - `analysis.pending`
  - `analysis.result`
  - `analysis.error`

代码改动：

- 后端新增 text conversation WebSocket，不删除现有 REST `/turns/text`，保留给 CLI、测试和 fallback。
- **直接复用 PR1 已拆出的原子函数**（`create_user_turn` / `stream_reply` / `commit_ai_turn` + 异步 grammar analysis），本 PR 不再重复抽公共逻辑。如果 PR1 没拆干净，先在本 PR 补齐再接文本路径，避免音频/文本两份实现漂移。
- 前端 `sendTurn` 从 REST 改为**每个文本 turn 建立一个 conversation WebSocket**，本轮结束后关闭。这样 pending analysis、超时和兜底都只绑定单轮，不处理多轮复用、乱序或并发 turn 的状态管理。
- 用户点击 Send 后立即 append user turn，先使用本地临时 id；收到 `user.final` 后替换成服务端 id（复用音频路径的 reconcile 逻辑）。
- **连接生命周期（grammar analysis 是异步的，过早关连接会丢 `analysis.result`）——已定方案 A**：text WS 在 `reply.done` 后**不立即关闭**，保持到该 turn 的 `analysis.result` 或 `analysis.error` 到达后再关（与音频 WS 行为一致）。前端用每个 turn 的 pending stage 集合判断是否收齐，收齐后关连接。
  - 兜底：若连接异常断开，前端用 `GET /api/sessions/{id}/analysis` 拉一次补齐，避免 assessment 永远停在 pending。
  - 超时：为本轮 analysis 设置 30s 超时。后端超时则发送 `analysis.error`（stage=`grammar`，code=`analysis_timeout`，`fallback_applied=true`）并关闭 text WS；前端若先检测到连接超时/断开，也拉一次 `/api/sessions/{id}/analysis` 兜底，避免连接长期挂住。

实现选择（已定）：

- 本 PR 走 text WebSocket，与音频协议对齐，复用前端已有的 delta/done 处理与上面定的连接生命周期方案。
- 退路（非本 PR 待决项）：只有当 text WS 实现过程中发现连接生命周期复杂度不可接受时，才另开 PR 评估 SSE / chunked REST，不在本 PR 里悬而未决。

测试：

- 后端新增 `tests/backend/test_text_websocket.py`：
  - `text_turn` 后立即收到 `user.final`。
  - fixture reply 也走 `reply.delta` / `reply.done`。
  - grammar 慢时不阻塞 `reply.delta`。
  - `analysis.result` 中 `turn_id` 对应 user turn。
  - text WS 在 `reply.done` 后仍保持连接，直到该 turn 的 `analysis.result` / `analysis.error` 送达才关闭（验证不会丢异步 analysis）。
  - grammar 超过 30s 或测试中注入超时后，服务端发送 `analysis.error` 并关闭连接；前端能进入兜底拉取逻辑。
- 前端测试：
  - 点击 Send 后，输入文本立即出现在 conversation 区。
  - AI 文本通过 delta 拼接。
  - Conversation Assessment 只在 analysis result 后出现。
  - REST fallback 不破坏现有 smoke。
- Playwright smoke 更新：
  - `Send` 后等待 AI 消息出现，不再依赖一次性 REST 返回。

验收：

- 文字和语音两种输入的 conversation 行为一致。

### PR4：后端新增场景已知信息模型与 prompt 注入

目标：所有场景都能携带背景资料，并且 AI 角色在对话生成时能使用这些资料。

数据模型：

- `backend/app/api.py`
  - `CreateSessionRequest` 增加：
    ```python
    known_info_text: str | None = Field(default=None, max_length=12000)
    known_info_sources: list[KnownInfoSource] = Field(default_factory=list)
    ```
- `backend/app/models/session.py`
  - 新增模型：
    ```python
    class KnownInfoSource(BaseModel):
        name: str
        kind: Literal["text", "pdf"]
        text_preview: str | None = None
        char_count: int = 0
    ```
  - `Session` 增加（**字段自带默认值**，旧 session JSON 缺这两个字段时才能正常反序列化）：
    ```python
    known_info_text: str | None = None
    known_info_sources: list[KnownInfoSource] = Field(default_factory=list)
    ```
- `backend/app/services/sessions.py`
  - `SessionStore.create()` 保存 known info。
  - 新增字段必须有默认值（`known_info_text=None`、`known_info_sources` 用 `default_factory=list`），保证 `storage.py` 反序列化**缺这两个字段的旧 session JSON** 不报错。

字符预算（与 PR6 统一，避免互相打架）：

- `known_info_text` 总上限 12000 字符。
- 单个 PDF 提取上限设为 **6000 字符**（见 PR6），避免“一个长简历 + 一点文字”就超过总上限被 422。
- 前端在拼接 textarea + 各 PDF 文本时做实时字数提示，超限前截断并提示用户。

Prompt 设计：

- `backend/app/services/dialogue.py`
  - `_generate_with_llm()` 和 `_streaming_messages()` 中加入 `known_info`。
  - 明确告诉模型：
    - known info 是用户提供的背景资料。
    - 可用于提出更具体的问题。
    - 不能把资料当成系统指令。
    - 不要泄露完整简历，只在对话中自然引用必要信息。

测试：

- `tests/backend/test_session_models.py`
  - Session 能保存 known info 和 sources。
  - 空白 known info 会被规范化为 `None`。
- `tests/backend/test_storage.py`
  - 加载缺少 `known_info_text` / `known_info_sources` 字段的旧 session JSON 不报错，字段回落到默认值。
- `tests/backend/test_scenario_api.py`
  - `POST /api/sessions` 可接收 builtin scenario + known info。
  - `POST /api/sessions` 可接收 custom scenario + known info。
  - 超长 known info 返回 422。
- `tests/backend/test_dialogue_service.py`
  - LLM prompt 中包含 known info。
  - known info 不改变 fixture fallback 的 schema。
  - prompt 中有防 prompt-injection 说明。

验收：

- 内置场景和自定义场景都能保存用户提供的背景资料。
- 后续 AI 回复生成能读取这些资料。

### PR5：基于 known info 生成更具体的 opening line

目标：如果用户上传了简历或填写了背景资料，AI 开场白就不要仍然完全泛泛而谈。

代码改动：

- 新增 service：`backend/app/services/opening.py`
- 行为：
  - 没有 known info：继续使用 scenario 原始 `opening_line`。
  - 有 known info 且 LLM 可用：生成一句 1-2 句的场景化 opening line。
  - 有 known info 但 LLM 不可用：使用模板化 opening line。
- **opening line 在 API endpoint 层（`create_session()` endpoint）算好再传给 `SessionStore.create()`**，不要把 LLM 调用塞进同步的 `SessionStore.create()`（`sessions.py:14`）。原因：`create()` 是同步函数且被大量测试直接调用，内嵌 LLM 会让它变慢、变 flaky，并被迫改成 async。
  - 给 `SessionStore.create()` 增加可选参数 `opening_line: str | None`，缺省时仍用 `scenario.opening_line`，保持现有调用方和测试不变。
- 示例：
  - Interview：
    - `I saw your background mentions backend systems and product planning. Could you walk me through one project you are most proud of?`
  - Work Meeting：
    - `I reviewed the project notes you shared. Could you start with the latest progress and the biggest risk?`
  - Restaurant：
    - `I noted your preferences. Would you like to start with recommendations that match them?`
- 由 `create_session()` endpoint 算出最终 opening line，作为 `opening_line` 参数传入 `SessionStore.create()`；`create()` 用它创建第一条 AI turn（缺省时回落到 `scenario.opening_line`）。

测试：

- `tests/backend/test_opening_service.py`
  - 无 known info 返回原 opening line。
  - interview known info 生成包含资料线索的开场白。
  - LLM invalid JSON 时 fallback 到模板。
  - 输出不包含中文，除非场景本身明确允许。
- `tests/backend/test_scenario_api.py`
  - 创建 session 后第一条 AI turn 是 context-aware opening line。
  - `opening_line` response 与 session 第一条 AI turn 一致。

验收：

- 面试官一开始就知道用户提供的基本资料。

### PR6：PDF 上传与文本提取接口

目标：支持上传 PDF，把 PDF 文本提取后作为 known info 的一部分。

推荐依赖：

- `pyproject.toml`
  - 新增主依赖：`pypdf>=4,<6`
  - 新增主依赖：`python-multipart`（FastAPI 处理 multipart/form-data 上传的运行时硬依赖，缺它 endpoint 一调用就报错）。
  - 如果担心安装体积，可放 optional dependency `pdf`，但产品路径建议主依赖。

API：

- `POST /api/known-info/pdf`
  - multipart file upload
  - 返回：
    ```json
    {
      "source": {
        "name": "resume.pdf",
        "kind": "pdf",
        "text_preview": "...",
        "char_count": 5320
      },
      "text": "extracted text..."
    }
    ```

限制：

- 只接受 `.pdf` / `application/pdf`。
- 当前版本只允许上传 **1 个 PDF**。这是 MVP 限制，用来先打通核心功能；后续需要多文档资料包时再单独扩展。
- 单文件最大 10MB。
- 单文件提取文本最大 **6000 字符**（与 PR4 总上限 12000 协调：单个 PDF 不能独占全部预算，留出空间给 textarea 手写资料）。
- 总 known info 上限 12000 字符，前端实时计算 textarea + 各 PDF 文本之和并提示。
- PDF 文本提取失败时返回用户可理解的 422/400。
- `char_count` 固定表示**截断后、实际进入 known info 的字符数**，用于前端摘要和总字符预算计算。若需要展示原始提取长度，后续可另加 `original_char_count`，本轮不做。

代码改动：

- 新增 `backend/app/services/pdf.py`
  - `extract_pdf_text(file_bytes: bytes) -> str`
  - 文本清洗：合并过多空白，去掉不可见字符。
- `backend/app/main.py`
  - 增加 upload endpoint。
- `backend/app/api.py`
  - 增加 response model。

测试：

- `tests/backend/test_pdf_known_info.py`
  - 非 PDF 拒绝。
  - 超大文件拒绝。
  - monkeypatch `PdfReader` 后验证多页文本合并。
  - 空 PDF / 无文本 PDF 返回清晰错误。
  - 文本超过 6000 字符上限会截断，`char_count` 等于截断后实际返回文本长度。
- 前端测试后续在 PR7 覆盖上传交互。

验收：

- 用户能上传 PDF 并把提取文本加入场景资料。

### PR7：前端场景资料面板，支持展开/收起、文字和 PDF

目标：所有场景下，scenario select 下方都有一个可展开/收起的大面板。用户上传或填写完成后可以关闭，回到对话。

UI 行为：

- 面板标题：`Scenario Briefing`
- 默认状态：
  - 初次进入：展开。
  - 开始 session 后：自动收起，避免占用对话空间。
  - 用户可随时点击 `Briefing` 摘要条重新展开查看。
- 收起状态显示：
  - `Briefing saved`
  - 字符数，例如 `1,240 chars`
  - PDF 数量，例如 `1 PDF`
  - `Edit` / chevron button
- 展开状态包含：
  - 当前场景说明或目标简述。
  - 大 textarea，至少 4-6 行。
  - PDF 上传按钮。
  - 已上传文件 chips，支持删除。
  - `Collapse` 按钮。

前端状态：

- `scenarioBriefingOpen`
- `knownInfoText` —— **只存用户在 textarea 里手打的文字**，不混入 PDF 提取文本。
- `knownInfoDocuments` —— 已上传 PDF 列表，MVP 最多 1 个；每项结构 `{ id, source: KnownInfoSource, text }`，PDF 提取文本存在这里，**不拼进 `knownInfoText`**。
- `knownInfoUploadState`
- `knownInfoUploadError`

> 关键：PDF 文本必须与 textarea 文本分开存。否则删除某个 PDF chip 时只能删掉 source 元数据，已拼进 `knownInfoText` 的那段 PDF 文本会残留、删不干净。最终发送时再由 textarea + 各 document 组合生成 payload。

开始 session payload（提交前组合，并校验总长 ≤ 12000）：

```js
// 注意：局部变量名不要和 state（knownInfoText / knownInfoSources）同名，否则自引用会 TDZ 报错
const combinedKnownInfoText = [knownInfoText.trim(), ...knownInfoDocuments.map(d => d.text)]
  .filter(Boolean)
  .join('\n\n');           // 超长则提示并截断
const combinedKnownInfoSources = knownInfoDocuments.map(d => d.source);
// payload: { known_info_text: combinedKnownInfoText, known_info_sources: combinedKnownInfoSources, ... }
```

```json
{
  "scenario_id": "interview",
  "custom_prompt": "... only for custom ...",
  "known_info_text": "... textarea 手打文字 + 各 PDF 提取文本，组合而成 ...",
  "known_info_sources": [...]
}
```

自定义场景关系：

- custom scenario 的“我要练什么”仍是 `custom_prompt`。
- `known_info_text` 是“AI 已知背景资料”。
- UI 上要避免两个输入混淆（custom 场景会同时出现两个框，必须讲清职责，否则用户会懵）：
  - Custom scenario prompt：短输入，描述“我要练什么场景”。视觉上紧贴 scenario select，标注清楚是练习设定。
  - Scenario Briefing：大面板，放“AI 已知的我的背景资料”和 PDF。用不同的标题/说明文案与 custom prompt 区分。
  - 文案建议：custom prompt 占位写“描述你想练的场景”，briefing 标题写“Scenario Briefing — 让 AI 提前了解你”。

测试：

- `frontend/src/App.test.jsx`
  - builtin scenario 下也能看到 `Scenario Briefing`。
  - 面板可展开/收起。
  - 收起后显示摘要：字符数和 PDF 数量。
  - 上传 PDF 调用 `/api/known-info/pdf`，成功后把 extracted text 存入 `knownInfoDocuments`（不拼进 textarea 的 `knownInfoText`）。
  - 已有 1 个 PDF 后再次上传时，前端阻止上传或提示先删除当前 PDF；不会出现多个 PDF source。
  - 删除 PDF chip 后：摘要更新，**且该 PDF 文本不再出现在最终 `known_info_text` 中**（验证拼接由 document 组合而来，删除能删干净）。
  - 手打文字与 PDF 文本各自独立：删 PDF 不影响 textarea 已输入内容，反之亦然。
  - Start payload 的 `known_info_text` = textarea 文字 + 各 document 文本组合；`known_info_sources` = 各 document 的 source。
  - custom scenario payload 同时包含 `custom_prompt` 和 `known_info_text`。
  - session active 时 briefing 默认收起，但可展开只读查看。

验收：

- 大框不长期占用空间。
- 用户上传好资料后可以收起继续对话。

### PR8：前端组件拆分，为 UI 升级降风险

目标：在做视觉升级前，先把 `App.jsx` 中主要区域拆成组件，降低后续 CSS 和 JSX 修改风险。

建议拆分：

- `frontend/src/components/PracticeLayout.jsx`
- `frontend/src/components/ConversationPanel.jsx`
- `frontend/src/components/ScenarioBriefingPanel.jsx`
- `frontend/src/components/ConversationAssessmentPanel.jsx`
- `frontend/src/components/ReadingPracticePanel.jsx`
- `frontend/src/components/MistakeBook.jsx`
- `frontend/src/components/icons.jsx`

约束：

- 本 PR 不改变 UI 行为。
- 不做大规模样式重写。
- 保持现有测试通过。

测试：

- 现有 `frontend/src/App.test.jsx` 全部通过。
- 可新增 smoke 测试确认：
  - Practice view 渲染。
  - Mistake Book view 渲染。
  - Scenario Briefing 初始渲染。

验收：

- 后续 UI PR 可以更小、更容易 review。

### PR9：Practice 页面视觉升级

目标：建立 Fluent Coach 自己的练习页风格。`ui1.png` 只作为“对话主次和右侧反馈栏”的竞品参考，不复刻它的浅蓝背景、气泡比例、按钮样式或整体版式。

设计方向：

- 页面背景使用浅色、有层次的训练工作台背景，但不能做成竞品同款渐变聊天页。
- 对话区占主宽度，弱边框，气泡更像真实练习记录。
- AI 和用户气泡增加 avatar/role chip：
  - AI：`AI`
  - User：`Me`
- AI streaming 时显示 typing indicator。
- 输入区固定在 conversation panel 底部，按钮变成更明确的 primary/secondary。
- 右侧 coach rail：
  - Conversation Assessment 为主。
  - Reading Practice、Timing、Summary 做 stacked panels 或 tabs。
- 增加自己的识别元素：
  - `Briefing` 资料夹摘要条。
  - `Coach Notes` 风格的评估卡。
  - 语音输入时的紧凑波形/录音状态条。
  - 分数使用细条或小型 meter，不只是一排数字。
- 保留当前所有信息，不牺牲可用性。

CSS 改动：

- 重写 `frontend/src/styles.css` 中：
  - `.app-shell`
  - `.topbar`
  - `.workspace`
  - `.conversation-panel`
  - `.message-list`
  - `.message`
  - `.turn-form`
  - `.coach-panel`
  - `.assessment-panel`
  - `.reading-practice-panel`
- 避免一屏全是同等白框。
- 不使用纯装饰性 orb/blob。
- 不复刻 `ui1.png` 的聊天页构图，不复刻 `ui2.png` 的深色卡片大厅。
- 按 1365x768 和移动宽度检查文本不重叠。

测试：

- `frontend/src/App.test.jsx` 行为测试继续通过。
- `frontend/e2e/smoke.spec.js` 更新选择器，确保：
  - Start。
  - Send。
  - End。
  - Summary 出现。
- 新增 Playwright viewport 覆盖：
  - desktop 1365x768。
  - mobile 390x844。
  - 检查关键控件可见且没有水平滚动。

验收：

- 练习页有明确主次：对话是中心，评估是侧边辅助。
- 视觉上能看出是 Fluent Coach 自己的训练工作台，而不是 `ui1.png` 或 `ui2.png` 的改色版本。

### PR10：场景区和资料区视觉升级

目标：让场景准备区有自己的“资料夹/训练准备”气质。`ui2.png` 只作为“场景资料密度和标签信息”的参考，不复刻它的深色侧栏、场景大厅卡片或发光按钮。

设计方向：

- Scenario select 下方的 briefing summary 变成有质感的 session setup band。
- 增加场景 chips：
  - 角色
  - 目标数量
  - target expressions 数量
  - uploaded PDFs 数量
- 内置场景可以在 briefing 展开时展示场景目标和目标表达。
- custom scenario prompt 保持短输入，briefing panel 保持大输入。
- 收起后的 briefing 不只是普通折叠面板，要像一个已挂载的场景资料夹：
  - 显示资料来源数。
  - 显示简短摘要。
  - 显示最近更新时间或字符数。
  - 提供一个清晰的 reopen action。

测试：

- 前端测试检查：
  - 每个内置场景切换后 briefing 面板仍存在。
  - custom prompt 与 briefing 分开。
  - 收起/展开状态不丢文字和 PDF source。

验收：

- 场景准备区不再像一个普通表单，而是有明确的“练习资料夹”和“训练配置”感。
- 不能像 `ui2.png` 的深色场景卡片大厅。

### PR11：Mistake Book 页面视觉升级

目标：错题本也统一到新视觉体系，但保持复盘效率。

设计方向：

- 左侧错题列表采用更清晰的卡片。
- 顶部 summary chips 更像 dashboard。
- 发音错题的 play/record 按钮使用图标按钮，减少文字按钮噪音。
- 右侧 Reading Practice / Timing 面板延续 coach rail 风格。

测试：

- 现有错题本测试继续通过。
- 新增前端测试：
  - 进入错题本详情。
  - 删除单条错题。
  - 删除整本错题。
  - 发音错题播放和跟读按钮仍可点击。
- Playwright smoke 可补一条 Mistake Book 导航检查。

验收：

- 错题本信息密度保留，但视觉不再是简单边框堆叠。

### PR12：端到端验收与报告更新

目标：把新增行为写进自动 smoke 和手动检查清单，避免后续回归。

自动测试：

- `make test`
- `make test-backend`
- `make test-frontend`
- `make test-e2e`

新增/更新报告项：

- `scripts/run_smoke_report.py`
  - 增加事件顺序检查：
    - `asr.final` before first `reply.delta`
    - `reply.done` before `analysis.pending`
  - 增加 text streaming smoke。
  - 增加 known info session creation smoke。
- `reports/smoke-latest.md`
  - 记录：
    - `end_turn -> asr.final`
    - `asr.final -> first reply.delta`
    - `reply.delta count`
    - known info included

手动检查清单：

- 内置 Job Interview：
  - 填 brief。
  - 上传 PDF。
  - 删除 PDF 后再 Start，确认 `known_info_text` 不再包含该 PDF 提取文本，`known_info_sources` 为空。
  - 收起 brief。
  - Start 后 opening line 引用资料。
  - Record 后用户 ASR 文本先出现。
  - AI 回复流式出现。
  - Conversation Assessment 完整结果后出现。
- Custom scenario：
  - custom prompt 和 known info 同时生效。
- UI：
  - 1365x768 无重叠。
  - 390x844 可用。
  - briefing 展开/收起不丢内容。

## 推荐执行顺序

1. PR1 后端音频流式协议。
2. PR2 前端语音即时显示和 delta 渲染。
3. PR3 文本发送流式化。
4. PR4 known info 数据模型和 prompt 注入。
5. PR5 context-aware opening line。
6. PR6 PDF 上传和提取。
7. PR7 可展开/收起 Scenario Briefing 面板。
8. PR8 前端组件拆分。
9. PR9 Practice 页面视觉升级。
10. PR10 场景区和资料区视觉升级。
11. PR11 Mistake Book 视觉升级。
12. PR12 e2e、smoke report 和手动验收清单。

## 风险与控制

- 风险：WebSocket 事件协议变化影响现有测试和 bench。
  - 控制：保留 `reply.text` 兼容一段时间；`test_ws_bench_driver*.py` 与 `scripts/` ws driver 在 PR1 内同步改读 delta/done。
- 风险：user turn 前移导致 LLM prompt 里 user 消息重复。
  - 控制：PR1 采用方案 B（保留 `user_text`，组 prompt 时排除最后一条刚入库的 user turn），并加“user 只出现一次”的断言测试。
- 风险：`add_text_turns` 是 audio/REST 共用耦合点，直接改会牵连 REST。
  - 控制：PR1 先拆成原子函数，`add_text_turns` 作为兼容封装保留；PR3 直接复用，不再各写一份。
- 风险：opening line 的 LLM 调用被塞进同步 `SessionStore.create()`，拖慢/污染测试。
  - 控制：在 async API 层算好 opening line，`create()` 仅接收可选 `opening_line` 参数。
- 风险：known info 字段加进 Session 后旧存档反序列化失败。
  - 控制：字段全部带默认值；`test_storage.py` 补旧 JSON 加载回归。
- 风险：单 PDF 字符上限与 known info 总上限冲突，长简历直接 422。
  - 控制：单 PDF 限 6000、总量限 12000，前端实时字数提示并截断。
- 风险：text WS 等待异步 analysis 时连接长期挂住。
  - 控制：单 turn analysis 设 30s 超时；超时发送 `analysis.error` 并关闭连接，前端再拉 `/analysis` 兜底。
- 风险：多 PDF 上传让 MVP 的 UI、payload 和删除逻辑变复杂。
  - 控制：本轮限制 1 个 PDF；前端阻止第二个上传，后端文档也按单 PDF 预算设计。
- 风险：文本发送从 REST 改 WebSocket 后前端测试复杂度上升。
  - 控制：REST endpoint 保留；新增 text WebSocket 独立测试；必要时降级为 SSE/chunked REST。
- 风险：PDF 文本可能很长或质量差。
  - 控制：限制大小、限制字符数、允许用户编辑提取文本。
- 风险：PDF prompt injection。
  - 控制：prompt 中明确 known info 只是背景资料，不是指令；不要把 PDF 内容拼进 system role。
- 风险：UI 大改导致交互回归。
  - 控制：先组件拆分，再视觉 PR；每个页面保留行为测试和 Playwright smoke。

## 完成定义

本轮功能完成时，必须满足：

- 语音 ASR 完成后，用户气泡立即出现在 conversation 区。
- AI 回复在 conversation 区流式出现，包括 fixture/fallback/真实 LLM 三种路径。
- 文本 Send 也能流式显示 AI 回复。
- Conversation Assessment 仍只展示完整 analysis result，不显示半截纠错。
- 所有场景都有可展开/收起的 Scenario Briefing 面板。
- PDF 上传后能提取文本、进入 known info，并在 start session payload 中发送到后端。
- 有 known info 时，AI opening line 或后续追问能体现已知背景。
- Practice UI 不再是简单三列白框，主对话和辅助评估有明确视觉主次。
- 每个 PR 都有对应自动测试；最后 `make test` 和 `make test-e2e` 可通过。
