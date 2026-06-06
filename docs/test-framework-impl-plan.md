# 全自动测试框架 · 详细实现计划(可执行)

> 配套设计见 [test-framework-plan.md](./test-framework-plan.md)。本文件是**逐文件、逐函数、可照着写**的实现计划。
> 范围:第一阶段「时延档 + RunRecord 落盘 + 独立只读面板」。`plan.md` 不动。
> 默认 `make test` 必须保持离线、确定性(marker 配置:`addopts = -m 'not integration and not manual'`,见 `pyproject.toml`)。

## 0. 已核实的代码事实(实现前提)

- **WS 协议** [`backend/app/main.py:264+`](../backend/app/main.py)
  - Client→Server:`{"type":"start_turn","expected_text":..,"mime_type":..,"force_analysis_error":..}` → 二进制音频块(`send_bytes`) → `{"type":"end_turn"}`。
  - Server→Client 事件:`asr.partial`、`asr.final`、`reply.text`(非流式)/`reply.delta`+`reply.done`(流式)、`debug.timing`(stage ∈ {asr,reply,grammar,pronunciation})、`analysis.pending`、`analysis.result`(含 `stage`/`turn_id`/`result`)、`analysis.error`、`error`。
  - **流式触发条件**(三者全真才流式,见 `dialogue_service.generate_reply_stream` [`dialogue.py:95`](../backend/app/services/dialogue.py#L95)):台词**不命中** `dialogue_samples` fixture **且** `llm_client is not None` **且** client 有 `stream_complete`。否则走非流式 `reply.text`,**无 TTFT/ITL**。
- **TestClient WS 用法**(镜像 [`tests/backend/test_audio_websocket.py`](../tests/backend/test_audio_websocket.py)):`TestClient(app).websocket_connect(f"/ws/sessions/{sid}/audio")`,`send_json`/`send_bytes`/`receive_json`。建 session:`POST /api/sessions {"scenario_id":...}`。
- **评测数据拉取**:`GET /api/sessions/{id}/analysis` → `SessionAnalysisResponse{session_id, grammar_results[], pronunciation_results[], errors[]}`(见 `backend/app/api.py`)。grammar/pronunciation 也实时通过 `analysis.result` 事件回传(含 `turn_id`)。
- **音频落盘**:`save_turn_audio` 写 `.local/audio/<session>/<uuid>.<ext>`,`stored_audio.preferred_path`;`Turn.audio_path` 记录该路径。
- **音频回合发音评测默认关闭**:`_should_assess_audio_turn_pronunciation()` [`main.py:1053`](../backend/app/main.py#L1053) 在 mock provider 下返回 False。→ **离线默认不跑发音段**;发音延迟仅在 `--real`(腾讯 SOE)或显式 `PRON_ASSESS_AUDIO_TURNS=1` 下采集。
- **ITL 缺失点**:流式 `else` 分支 [`main.py:569-627`](../backend/app/main.py#L569) 只记了 `reply_first_delta_ms`,没数 delta 个数 / 总流时长。

## 1. 提交切分(小步直提 master)

| 提交 | 内容 | 生产改动 |
|---|---|---|
| **C1** | WS 流式补 ITL + 单测 | 仅 `main.py` 流式循环几行 |
| **C2** | `testkit` 数据层:models + run_store + report + ws_driver + CLI + 单测 | 无(纯新增) |
| **C3** | 独立只读面板:dashboard app + 静态页 + 启动脚本 + 单测 | 无(独立 app) |

---

## 2. C1 — WS 流式补 ITL

### 2.1 改 `backend/app/main.py` 流式 `else` 分支(约 576-627 行)
在进入 delta 循环前初始化计数,循环内累加,循环后算 ITL:
```python
reply_text_parts: list[str] = []
first_delta = True
delta_count = 0                       # NEW
stream_started = time.perf_counter()  # NEW（首 delta/总时长基准已有 dialogue_started，可复用，但单独基准更准）
try:
    for chunk in stream_reply.chunks:
        if not chunk:
            continue
        if first_delta:
            timings["reply_first_delta_ms"] = _elapsed_ms(dialogue_started)
            first_delta = False
        delta_count += 1              # NEW
        reply_text_parts.append(chunk)
        await websocket.send_json({...})  # 不变
except Exception:
    ...
# 循环后、在 timings["dialogue_reply_ms"] 附近：
timings["reply_delta_count"] = delta_count                                   # NEW
timings["reply_total_stream_ms"] = _elapsed_ms(stream_started)               # NEW
if delta_count > 1 and "reply_first_delta_ms" in timings:                    # NEW
    timings["reply_itl_ms"] = round(
        (timings["reply_total_stream_ms"] - timings["reply_first_delta_ms"]) / (delta_count - 1), 3
    )
```
- 非流式分支(`reply.text`)不加这些键(本就无 token 流)。
- 其余逻辑、事件、顺序完全不动。

### 2.2 测试 `tests/backend/test_ws_itl.py`
- 注入流式:`monkeypatch.setattr(main.dialogue_service, "llm_client", FakeLLMClient(["Sure, here is a longer reply with several words"]))`(FakeLLMClient.stream_complete 按词 yield → 多 delta)。
- 用**非 fixture 台词**(如 `"My weekend was relaxing and quiet overall"`)→ 触发流式。
- 读到 `debug.timing` stage=reply,断言 `timings` 含 `reply_delta_count >= 2`、`reply_itl_ms`(>=0)、`reply_first_delta_ms`。
- 默认 marker、离线。

---

## 3. C2 — testkit 数据层(driver / run_store / report / CLI)

新目录 `backend/app/testkit/`(加 `__init__.py`)。

### 3.1 `backend/app/testkit/models.py` — RunRecord 契约(pydantic)
```python
class TurnRecord(BaseModel):
    index: int
    user_text: str                    # = expected_text(离线)/ asr_text(真实)
    asr_text: str
    expected_text: str | None
    audio_path: str | None
    reply_text: str
    grammar: dict | None              # GrammarCorrection.model_dump()
    pronunciation: dict | None        # PronunciationAssessment.model_dump()
    errors: list[dict] = []           # AnalysisError.model_dump()
    timings_ms: dict[str, float] = {} # 合并各 debug.timing 的 timings
    wer: float | None = None

class LatencyStat(BaseModel):
    p50: float; p90: float; p95: float; max: float; mean: float; count: int

class RunRecord(BaseModel):
    run_id: str
    scenario_id: str
    mode: str                          # "offline_fake" | "real"
    generated_at: str                  # 调用方传入(脚本侧 stamp，避免库内 Date)
    providers: dict[str, str | None]   # 取自 provider_status()
    turns: list[TurnRecord]
    latency_summary: dict[str, LatencyStat] = {}
```
- 复用现有模型仅做 `model_dump`,避免与产品模型强耦合。

### 3.2 `backend/app/testkit/scripts_data.py` — 离线 scripted 台词
- 按 scenario 提供**不命中 `dialogue_samples`** 的自然台词各 8~10 条(确保走流式),超出轮数则循环。
- 例:interview → `["My weekend was relaxing and quiet overall", "I enjoy building backend services and tools", ...]`。
- 真实档可改用 `dialogue_samples` 真句或 persona(后续阶段)。

### 3.3 `backend/app/testkit/ws_driver.py` — 驱动 WS + 组装 RunRecord
核心函数:
```python
def run_ws_conversation(
    *, scenario_id: str, turns: int, app=app, transcript_source="scripted",
    mode: str = "offline_fake",
) -> list[TurnRecord]:
```
算法(每轮):
1. `client = TestClient(app)`;首轮 `POST /api/sessions` 取 `session_id`。
2. `with client.websocket_connect(...) as ws:` 对每轮:
   - `ws.send_json({"type":"start_turn","expected_text": line})` → 读一条(asr.partial)。
   - `ws.send_bytes(b"\x00" * 32)`(非空假音频)→ `ws.send_json({"type":"end_turn"})`。
   - **按类型收集**(不靠固定顺序):循环 `ws.receive_json()`,塞进 per-turn buckets:
     - `asr.final` → asr_text
     - `reply.delta`(累加文本)/`reply.text`/`reply.done` → reply_text
     - `debug.timing` → `timings_ms.update(msg["timings"])`(reply/grammar/pronunciation 各段都并进来)
     - `analysis.result`(stage grammar/pronunciation) → grammar/pronunciation dict
     - `analysis.error` → errors.append
     - `error` → 记录并中止该轮
   - **停止条件**:已收到 reply 终态(`reply.done`/`reply.text`)**且**收到一条 grammar 的 `analysis.result`/`analysis.error`(grammar 必有);若发音段开启,再等 pronunciation 终态。设最大读取次数兜底防卡。
3. 离线模式:函数入口注入 `dialogue_service.llm_client = FakeLLMClient([...])`(用多词响应),保证流式;`ASR_PROVIDER` 由调用方设 `fake`。
4. 兜底:也可 `GET /api/sessions/{id}/analysis` 二次校准 grammar/pronunciation(防事件竞态)。
5. `audio_path` 从 session 的最新 user turn 取(`session_store.get(sid).turns[-2].audio_path`),或从 `analysis`/turn 列表关联。
6. 返回 `list[TurnRecord]`(`generated_at`/`run_id` 由 CLI 脚本 stamp)。

> 说明:driver 不污染产品 DB;它只读 `/api/sessions/{id}/analysis` 与 WS 事件。注入的 FakeLLM 在函数结束后应还原(try/finally)。

### 3.4 `backend/app/testkit/report.py` — 聚合
```python
def percentile(values: list[float], p: float) -> float        # 纯 stdlib 线性插值
def aggregate_latency(turns: list[TurnRecord]) -> dict[str, LatencyStat]
def build_run_record(*, run_id, scenario_id, mode, generated_at, providers, turns) -> RunRecord
def render_markdown(run: RunRecord) -> str                     # 汇总表 + 各段 p50/p90
```
- 对所有 turn 的 `timings_ms` 按键聚合;键缺失的轮跳过(发音离线缺失不报错)。

### 3.5 `backend/app/testkit/run_store.py` — RunRecord 读写
```python
RUNS_DIR = Path(os.environ.get("BENCH_RUNS_DIR", "reports/runs"))
def save_run(run: RunRecord) -> Path           # reports/runs/<run_id>.json
def load_run(run_id: str) -> RunRecord
def list_runs() -> list[dict]                  # [{run_id, scenario_id, mode, generated_at, turn_count}]
```

### 3.6 `scripts/run_conversation_bench.py` — CLI
- 参数:`--scenario {interview,restaurant_ordering,meeting}`、`--turns N`、`--transcript-source scripted`、`--real`、`--output-dir reports`。
- 默认(无 `--real`):`os.environ["ASR_PROVIDER"]="fake"`,driver 注入 FakeLLM;`mode="offline_fake"`。
- `--real`:`load_dotenv()`,不注入 FakeLLM(用 env 配置的真实 client),`mode="real"`;`run_id` 含时间戳(脚本侧 `datetime.now`)。
- 流程:`run_ws_conversation` → `build_run_record`(stamp generated_at/run_id/providers=`provider_status()`)→ `save_run` → 同时写 `reports/bench-latest.{json,md}`(`render_markdown`)。
- 打印 run 路径与各段 p50/p90 摘要。

### 3.7 测试
- `tests/backend/test_ws_bench_driver.py`(默认离线):
  - 跑 3 轮 → `len(turns)==3`;每轮含 `reply_first_delta_ms`/`reply_itl_ms`/`dialogue_reply_ms`/`grammar_ms` 键;`reply_text` 非空;`grammar` 字段存在。
  - `aggregate_latency` 对 `reply_first_delta_ms` 出 `p50/p90/count==3`。
  - `build_run_record` + `save_run`/`load_run` round-trip;RunRecord schema 校验通过。
- `tests/backend/test_bench_report.py`:`percentile` 边界(单值/多值)、缺键不报错。

---

## 4. C3 — 独立只读面板(零耦合产品)

### 4.1 `backend/app/testkit/dashboard.py` — 独立 FastAPI app
```python
dashboard_app = FastAPI(title="XEngineer Bench Dashboard")
# 不 import 产品业务逻辑（main/services），仅 import run_store + models
@dashboard_app.get("/")                         -> FileResponse(dashboard/index.html)
@dashboard_app.get("/api/runs")                 -> run_store.list_runs()
@dashboard_app.get("/api/runs/{run_id}")        -> run_store.load_run(run_id).model_dump()
@dashboard_app.get("/api/runs/{run_id}/turns/{i}/audio")
    # 读 RunRecord.turns[i].audio_path；校验路径在允许根（.local/audio 或 reports）内防穿越；FileResponse
```
- 路径白名单校验:`resolve()` 后必须位于 `Path('.local/audio').resolve()` 或 `RUNS_DIR.resolve()` 之下,否则 404。

### 4.2 `backend/app/testkit/dashboard/index.html` — 单文件静态页(无构建)
- 原生 JS `fetch('/api/runs')` 列表 → 选中 `fetch('/api/runs/{id}')`。
- 渲染:
  - 顶部:run 元信息 + `latency_summary` 各段 p50/p90/p95 表;**内联 SVG 柱状/分位图**(纯 JS 画,无第三方库)。
  - 每轮表格:index | 音频(`<audio src=".../turns/{i}/audio">`) | expected/asr | reply | grammar(corrected+issues) | pronunciation(overall+低分词) | errors | 关键延迟(TTFT/ITL/asr_ms)。
- 所有资源内联,零外部依赖。

### 4.3 `scripts/bench_dashboard.py` — 启动
```python
import uvicorn
from backend.app.testkit.dashboard import dashboard_app
uvicorn.run(dashboard_app, host="127.0.0.1", port=int(os.environ.get("BENCH_DASHBOARD_PORT","8100")))
```
- 与 `make dev-backend`(8000)端口隔离,互不影响。

### 4.4 测试 `tests/backend/test_bench_dashboard.py`(默认离线)
- 用 `TestClient(dashboard_app)`,先 `save_run` 一份 fixture RunRecord(指向一个临时音频文件,`monkeypatch` `BENCH_RUNS_DIR`/允许根)。
- 断言:`GET /` 200、`GET /api/runs` 含该 run、`GET /api/runs/{id}` schema 正确、音频端点返回文件字节;越权路径(`../etc/passwd` 式)404。

---

## 5. 全局约束与验证

### 离线/确定性保证
- 新测试均默认 marker;不联网、不依赖 mic、不读真实 key。
- driver 注入 FakeLLM + `ASR_PROVIDER=fake`;发音段离线默认关闭(不进 RunRecord,面板容忍缺失)。
- 脚本侧才用 `datetime.now()`(库 `testkit` 内不调时间随机,保持可测)。

### 验证清单
1. `make test` 全绿。
2. `python3 scripts/run_conversation_bench.py --scenario interview --turns 10` → `reports/runs/<id>.json` + `reports/bench-latest.md`;各段(transcode/asr/TTFT/ITL/dialogue/grammar)p50/p90 有值。
3. `python3 scripts/bench_dashboard.py` → 浏览器 `http://127.0.0.1:8100/`:run 列表、每轮表格(音频回放 + asr + reply + grammar)、延迟分位图。
4. `... --turns 10 --real`(需 `.env` + 本地模型 + `PRON_ASSESS_AUDIO_TURNS=1` 看发音)→ TTFT/ITL/asr_ms/pronunciation_ms 为真实数值。

### 文件清单(新增/改)
```
改  backend/app/main.py                      # 仅 ITL 几行
新  backend/app/testkit/__init__.py
新  backend/app/testkit/models.py
新  backend/app/testkit/scripts_data.py
新  backend/app/testkit/ws_driver.py
新  backend/app/testkit/report.py
新  backend/app/testkit/run_store.py
新  backend/app/testkit/dashboard.py
新  backend/app/testkit/dashboard/index.html
新  scripts/run_conversation_bench.py
新  scripts/bench_dashboard.py
新  tests/backend/test_ws_itl.py
新  tests/backend/test_ws_bench_driver.py
新  tests/backend/test_bench_report.py
新  tests/backend/test_bench_dashboard.py
```

## 6. 后续阶段(不在本计划)
TTS→WS 真实语音 WER、虚拟用户 persona + 已知错误注入(precision/recall)、裁判 + rubric + fixture 标定、面板多 run 趋势对比与回归红线、并发吞吐压测。
