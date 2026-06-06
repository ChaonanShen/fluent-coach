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
- **评测数据拉取**:`GET /api/sessions/{id}/analysis` → `SessionAnalysisResponse{session_id, grammar_results[], pronunciation_results[], errors[]}`(见 `backend/app/api.py`)。该接口当前读进程内 `analysis_store`,适合同一进程 bench driver 兜底校准;跨进程历史回放以 RunRecord 为准。grammar/pronunciation 也实时通过 `analysis.result` 事件回传(含 `turn_id`)。
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
在进入 delta 循环前初始化计数,循环内记录首/末 delta 时间,循环后算 ITL:
```python
reply_text_parts: list[str] = []
first_delta = True
delta_count = 0                       # NEW
stream_started = time.perf_counter()  # NEW
first_delta_at = None                 # NEW
last_delta_at = None                  # NEW
try:
    for chunk in stream_reply.chunks:
        if not chunk:
            continue
        now = time.perf_counter()     # NEW
        if first_delta:
            timings["reply_first_delta_ms"] = _elapsed_ms(dialogue_started)
            first_delta = False
            first_delta_at = now      # NEW
        last_delta_at = now           # NEW
        delta_count += 1              # NEW
        reply_text_parts.append(chunk)
        await websocket.send_json({...})  # 不变
except Exception:
    ...
# 循环后、在 timings["dialogue_reply_ms"] 附近：
timings["reply_delta_count"] = delta_count                                   # NEW
timings["reply_total_stream_ms"] = _elapsed_ms(stream_started)               # NEW
if delta_count > 1 and first_delta_at is not None and last_delta_at is not None: # NEW
    timings["reply_itl_ms"] = round(
        ((last_delta_at - first_delta_at) * 1000.0) / (delta_count - 1), 3
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
3. 离线模式:函数入口注入 `main.asr_provider = FakeASR()` 和 `main.dialogue_service.llm_client = FakeLLMClient([...])`(用多词响应),保证流式;结束后用 `try/finally` 还原。
4. 兜底:也可 `GET /api/sessions/{id}/analysis` 二次校准 grammar/pronunciation(防事件竞态)。
5. `audio_path` 从 session 的最新 user turn 取(`session_store.get(sid).turns[-2].audio_path`),或从 `analysis`/turn 列表关联。
6. 返回 `list[TurnRecord]`(`generated_at`/`run_id` 由 CLI 脚本 stamp)。

> 说明:RunRecord 不写产品 DB,但 WS 创建的 session/turn 仍会按当前 `APP_DB_PATH` 写 SQLite。
> 测试需在 import app 前或通过 monkeypatch 隔离 `APP_AUDIO_DIR`/`APP_DB_PATH`;脚本可接受写入默认本地 `.local`。

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
DEFAULT_RUNS_DIR = Path("reports/runs")
def runs_dir() -> Path: return Path(os.environ.get("BENCH_RUNS_DIR", str(DEFAULT_RUNS_DIR)))
def save_run(run: RunRecord) -> Path           # reports/runs/<run_id>.json
def load_run(run_id: str) -> RunRecord
def list_runs() -> list[dict]                  # [{run_id, scenario_id, mode, generated_at, turn_count}]
```
- `BENCH_RUNS_DIR` 必须运行时读取,不能 import 时固定,否则 dashboard/run_store 测试 monkeypatch 不稳定。

### 3.6 `scripts/run_conversation_bench.py` — CLI
- 参数:`--scenario {interview,restaurant_ordering,meeting}`、`--turns N`、`--transcript-source scripted`、`--real`、`--output-dir reports`。
- 默认(无 `--real`):在 import app 前设置 `ASR_PROVIDER=fake`、`LLM_PROVIDER=fake`、`PRON_PROVIDER=mock`;driver 再注入 FakeASR/FakeLLM;`mode="offline_fake"`。
- `--real`:必须先 `load_dotenv()` 再 import `backend.app.main`,不注入 FakeLLM(用 env 配置的真实 client),`mode="real"`;`run_id` 含时间戳(脚本侧 `datetime.now`)。
- `--real` 不能使用假 bytes;第一阶段可先要求 `--audio-dir/--audio-file` fixture wav 输入,无真实音频则直接报错并提示后续 TTS 真实档。
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
    # 读 RunRecord.turns[i].audio_path；校验路径在允许根（.local/audio、APP_AUDIO_DIR 或 reports）内防穿越；FileResponse
```
- 路径白名单校验:`resolve()` 后必须位于 `Path('.local/audio').resolve()`、`APP_AUDIO_DIR` 或 `runs_dir()` 之下,否则 404。

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
- driver 注入 FakeASR/FakeLLM;发音段离线默认关闭(不进 RunRecord,面板容忍缺失)。
- 脚本侧才用 `datetime.now()`(库 `testkit` 内不调时间随机,保持可测)。

### 验证清单
1. `make test` 全绿。
2. `python3 scripts/run_conversation_bench.py --scenario interview --turns 10` → `reports/runs/<id>.json` + `reports/bench-latest.md`;各段(transcode/asr/TTFT/ITL/dialogue/grammar)p50/p90 有值。
3. `python3 scripts/bench_dashboard.py` → 浏览器 `http://127.0.0.1:8100/`:run 列表、每轮表格(音频回放 + asr + reply + grammar)、延迟分位图。
4. `... --turns 10 --real --audio-dir fixtures/audio/public/...`(需 `.env` + 本地模型 + 真实音频;`PRON_ASSESS_AUDIO_TURNS=1` 看发音)→ TTFT/ITL/asr_ms/pronunciation_ms 为真实数值。

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

## 6. 第二阶段 — `grammar_tts` 全自动语法错误 bench

目标:让 bench 不再依赖固定用户台词或人工准备音频,而是自动生成"带语法/表达错误的用户回复",
用本地 Kokoro TTS 合成音频,再喂回真实 WS 链路。**本阶段只测语法/表达错误**,发音错误检测仍走
L2-ARCTIC / SpeechOcean / 真人录音的 pronunciation eval。

### 6.0 已核实前提

- 本地 TTS 模型已放在 `models/tts/Kokoro-82M/`,包含:
  - `kokoro-v1_0.pth`
  - `voices/af_heart.pt`
  - `config.json` / `configuration.json`
- Kokoro README 示例使用:
  ```python
  from kokoro import KPipeline
  pipeline = KPipeline(lang_code="a")
  generator = pipeline(text, voice="af_heart")
  for gs, ps, audio in generator:
      ...
  ```
- 当前 `backend/app/services/tts.py` 只有 `browser`、`openai_compatible`、`cloud_disabled`;
  还没有服务端本地 TTS provider。
- `run_conversation_bench.py --real` 当前要求 `--audio-file/--audio-dir`;还没有"自动生成用户文本 → TTS 音频"模式。

### 6.1 提交切分

| 提交 | 内容 | 生产改动 |
|---|---|---|
| **C4** | 接入 Kokoro 本地 TTS provider + 独立 smoke 脚本 | `tts.py` 新 provider,默认不启用 |
| **C5** | 新增语法错误注入器 + 虚拟用户数据契约 + 单测 | 纯 `testkit` 新增 |
| **C6** | `grammar_tts` driver/CLI/RunRecord/报告聚合 | 纯 `testkit` 和 script 改动 |
| **C7** | dashboard 展示 clean/injected/grammar metrics/TTS 延迟 | 独立 dashboard |
| **C8** | README/guide 更新 + 真实本地 smoke 验证记录 | 文档 |

---

## 7. C4 — Kokoro 本地 TTS provider

### 7.1 `pyproject.toml`

新增可选依赖组,默认 `make test` 不安装、不依赖:

```toml
[project.optional-dependencies]
tts = [
    "kokoro>=0.9.2,<1",
    "soundfile>=0.12,<1",
]
```

系统依赖:`espeak-ng`。README 写明安装:

```bash
python3 -m pip install -e ".[tts]"
sudo apt-get install -y espeak-ng
```

> 若服务器没有 sudo,记录 conda/系统包替代方案;代码层面只做清晰错误提示。

### 7.2 `backend/app/services/tts.py`

新增 `KokoroTTSProvider`,懒加载依赖,避免默认测试 import 失败:

```python
class KokoroTTSProvider:
    provider_name = "kokoro"

    def __init__(self) -> None:
        self.model_dir = Path(os.environ.get("KOKORO_MODEL_DIR", "models/tts/Kokoro-82M"))
        self.voice = os.environ.get("KOKORO_VOICE", "af_heart")
        self.lang_code = os.environ.get("KOKORO_LANG_CODE", "a")
        self.sample_rate = int(os.environ.get("KOKORO_SAMPLE_RATE", "24000"))
        self._pipeline = None

    def synthesize(self, text: str) -> TTSResult:
        # lazy import kokoro + soundfile
        # pipeline(text, voice=self.voice) -> audio chunks
        # concatenate chunks -> wav bytes -> base64
        # return mime_type="audio/wav"
```

实现要求:

- 空文本直接返回 fallback 或抛可读 `RuntimeError`。
- 第一次调用初始化 pipeline,后续复用,避免每轮重新加载模型。
- 优先验证 `KOKORO_MODEL_DIR` 存在;如果 Kokoro 包暂不支持显式本地目录,先用包默认加载机制,
  但 smoke 脚本必须证明在当前服务器上不会重新下载。
- `create_tts_provider()` 支持:
  ```python
  if provider == "kokoro":
      return KokoroTTSProvider()
  ```
- `provider_status()` 当前只读 env,无需改结构;dashboard/providers 会显示 `tts=kokoro`。

### 7.3 `scripts/test_kokoro_tts.py`

新增手动 smoke 脚本,不进默认 `make test`:

```bash
TTS_PROVIDER=kokoro \
KOKORO_MODEL_DIR=/home/scn/xe2/models/tts/Kokoro-82M \
python3 scripts/test_kokoro_tts.py \
  --text "I has three year experience." \
  --output /tmp/kokoro-smoke.wav
```

脚本检查:

- 输出文件存在且大于 1KB。
- mime 是 wav,采样率 24000 或配置值。
- 打印耗时 `tts_ms`。

### 7.4 测试

- `tests/backend/test_asr_tts_providers.py` 增加 `create_tts_provider` 对 `TTS_PROVIDER=kokoro`
  的 provider name 测试,用 monkeypatch 替代实际合成,不加载模型。
- `tests/backend/test_tts_kokoro_provider.py` 用 fake `kokoro`/`soundfile` module monkeypatch,
  验证 `synthesize()` 返回 base64 wav 和 `mime_type="audio/wav"`。
- 真实模型 smoke 标记为 `manual` 或单独脚本,不进默认测试。

---

## 8. C5 — 虚拟用户与确定性语法错误注入

### 8.1 `backend/app/testkit/grammar_cases.py`

新增可控错误案例库。每条包含:

```python
class GrammarErrorCase(BaseModel):
    scenario_id: str
    clean_text: str
    injected_text: str
    expected_corrected_text: str
    expected_error_types: list[str]
    error_spans: list[str] = []
```

示例:

```text
clean:    I have three years of experience in backend development.
injected: I has three year experience in backend development.
types:    ["subject_verb_agreement", "plural_noun"]

clean:    Yesterday I went to a meeting and explained the risk.
injected: Yesterday I go to meeting and explain the risk.
types:    ["verb_tense", "article"]
```

第一版优先用模板案例,不要靠 LLM 随机造错。原因:只有模板案例才能稳定计算 grammar recall。

### 8.2 `backend/app/testkit/grammar_injection.py`

提供:

```python
def next_error_case(scenario_id: str, index: int) -> GrammarErrorCase
def score_grammar_result(case: GrammarErrorCase, grammar: dict | None, asr_text: str) -> dict[str, object]
```

`score_grammar_result` 第一版指标:

- `expected_error_recall`:grammar issues 中命中的 expected_error_types 比例。
- `corrected_text_match`:normalized corrected_text 是否等于 expected_corrected_text。
- `asr_preserved_injected_error`:ASR 文本是否仍包含关键错误 span,用于判断 TTS→ASR 是否把错误吞掉。

命中规则要宽松:

- normalized 文本比较,忽略大小写和多余空格。
- error_type 可做 alias 映射,例如 `agreement` / `subject_verb_agreement`。
- corrected_text_match 不作为唯一通过条件,因为 grammar_service 可能给等价改写。

### 8.3 `backend/app/testkit/virtual_user.py`

本阶段虚拟用户分两层:

```python
class VirtualUser(Protocol):
    def next_clean_turn(self, *, scenario_id: str, history: list[dict[str, str]], index: int) -> str: ...
```

实现:

- `TemplateVirtualUser`:默认用于 `make test`,直接从 `grammar_cases` 取 clean_text,确定性。
- `LLMVirtualUser`:真实 bench 可选,根据 scenario + AI 上一句生成 clean_text;随后仍交给
  `grammar_injection` 注入错误。若 LLM 生成文本不适合注入,回退到模板案例。

CLI 第一版默认用模板 clean_text,保证可评测。后续再打开:

```bash
--virtual-user llm
```

---

## 9. C6 — `grammar_tts` driver / CLI / RunRecord

### 9.1 `backend/app/testkit/models.py`

扩展 `TurnRecord`,全部是可选字段,兼容旧 run:

```python
clean_text: str | None = None
injected_text: str | None = None
expected_corrected_text: str | None = None
expected_error_types: list[str] = []
grammar_metrics: dict[str, object] = {}
tts: dict[str, object] = {}
```

### 9.2 `backend/app/testkit/tts_audio.py`

新增工具:

```python
def synthesize_turn_audio(text: str, provider: TTSProvider) -> tuple[bytes, str, dict[str, object], dict[str, float]]
```

职责:

- 调 `provider.synthesize(text)`。
- 解码 `audio_base64`。
- 返回 `(audio_bytes, mime_type, tts_meta, {"tts_ms": ...})`。
- 如果 provider fallback 或没有音频,抛出清晰错误,不要悄悄用假音频。

### 9.3 `backend/app/testkit/ws_driver.py`

新增模式:

```python
mode="grammar_tts"
```

每轮流程:

1. 从 `VirtualUser` 取 clean_text。
2. 从 `grammar_injection` 取 injected_text + expected ground truth。
3. 用 `tts_audio.synthesize_turn_audio(injected_text, tts_provider)` 生成音频。
4. WS 发送:
   ```python
   start_turn({"mime_type": mime_type, "expected_text": injected_text})
   send_bytes(audio_bytes)
   end_turn
   ```
   对真实 ASR 来说 `expected_text` 只用于 partial/ground truth,`FasterWhisperASR` 不会用它作弊。
5. 收集 `asr.final`、reply、grammar、timings。
6. 计算:
   - `wer = word_error_rate(injected_text, asr_text)`
   - `grammar_metrics = score_grammar_result(case, grammar, asr_text)`
7. `TurnRecord` 写 clean/injected/expected/tts/timings。

约束:

- `grammar_tts` 默认拒绝 `ASR_PROVIDER=fake` 和 `TTS_PROVIDER=browser/cloud_disabled`。
- 可加 `--allow-fake-providers` 只给开发调试使用,默认关闭。
- 如果 `PRON_ASSESS_AUDIO_TURNS` 未设置,保持发音评测默认逻辑;本阶段不要求 pronunciation 有值。

### 9.4 `scripts/run_conversation_bench.py`

参数调整:

```bash
--mode offline_fake | real_audio | grammar_tts
--real  # 保留兼容,等价于 --mode real_audio
--virtual-user template | llm
--allow-fake-providers
```

导入顺序:

- 先处理 `--mode` 和 `.env`。
- `grammar_tts` 必须 `load_dotenv(force=True)` 后再 import app/provider 单例。
- 创建 TTS provider 时也要在 env 加载后进行。

真实命令:

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
  --turns 10
```

### 9.5 `backend/app/testkit/report.py`

Markdown 增加:

- grammar hit summary:
  - average `expected_error_recall`
  - corrected_text_match rate
  - ASR WER against injected_text
- latency summary 继续只聚合 `*_ms`,包括新 `tts_ms`。

### 9.6 测试

- `tests/backend/test_grammar_injection.py`
  - case 轮转、expected_error_types 非空。
  - score 对 mock grammar result 能算 recall。
- `tests/backend/test_tts_audio.py`
  - fake TTS provider 返回 base64 wav bytes → `tts_ms` 和 meta 正常。
  - fallback/no audio 抛 RuntimeError。
- `tests/backend/test_ws_bench_driver_grammar_tts.py`
  - 注入 fake TTS provider + FakeASR + FakeLLM,跑 2 轮。
  - 每轮有 `clean_text`、`injected_text`、`expected_error_types`、`grammar_metrics`、`tts_ms`。
  - 默认测试不加载 Kokoro 模型、不联网。
- CLI smoke 可用 `/tmp` output 验证。

---

## 10. C7 — Dashboard 展示 grammar_tts 字段

### 10.1 API

`dashboard.py` 不需要改 API;仍然返回完整 RunRecord JSON。

### 10.2 `dashboard/index.html`

Turns 表新增/调整:

- Expected / ASR 改成:
  - Clean
  - Injected
  - ASR
  - WER
- Grammar 列显示:
  - expected_error_types
  - grammar issues
  - expected_error_recall
  - corrected_text_match
- Timing 增加 `TTS` pill。

Summary 增加:

- Avg grammar recall
- Corrected match rate
- Median TTS

Latency 图把 `tts_ms` 纳入关键指标。

### 10.3 测试

`tests/backend/test_bench_dashboard.py` fixture RunRecord 增加 grammar_tts 字段,确保详情 API 仍返回,
音频回放仍正常。静态页不做浏览器 E2E,只保证 HTML 可访问。

---

## 11. C8 — 文档与真实 smoke

### 11.1 README / bench guide

更新:

- 本地 Kokoro 安装:
  ```bash
  python3 -m pip install -e ".[tts]"
  sudo apt-get install -y espeak-ng
  ```
- `.env` 示例:
  ```bash
  TTS_PROVIDER=kokoro
  KOKORO_MODEL_DIR=/home/scn/xe2/models/tts/Kokoro-82M
  KOKORO_VOICE=af_heart
  ```
- `grammar_tts` 命令和 dashboard 查看方式。
- 明确发音错误不在 grammar_tts 中测。

### 11.2 验证清单

默认验证:

```bash
make test
python3 scripts/run_conversation_bench.py --scenario interview --turns 2 --output-dir /tmp/bench-test
```

Kokoro smoke:

```bash
TTS_PROVIDER=kokoro \
KOKORO_MODEL_DIR=/home/scn/xe2/models/tts/Kokoro-82M \
python3 scripts/test_kokoro_tts.py --output /tmp/kokoro-smoke.wav
```

真实 grammar_tts smoke:

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
  --turns 3 \
  --output-dir /tmp/grammar-tts-report
```

查看:

```bash
BENCH_RUNS_DIR=/tmp/grammar-tts-report/runs \
APP_AUDIO_DIR=/tmp/grammar-tts-audio \
python3 scripts/bench_dashboard.py
```

成功标准:

- 每轮都有 `clean_text` / `injected_text` / `asr_text` / `reply_text` / `grammar`。
- `tts_ms`、`asr_ms`、`reply_first_delta_ms`、`grammar_ms` 有值。
- `grammar_metrics.expected_error_recall` 有值。
- dashboard 能回放 TTS 生成音频。
