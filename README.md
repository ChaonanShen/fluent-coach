# XEngineer 第三批(6.5-6.7)

## 题目：AI 英语口语陪练

请开发一款英语口语练习工具，帮助用户在指定场景下进行真实对话训练。要求：支持场景选择（面试 / 点餐 / 会议等）、实时语音对话、发音评测、语法/表达纠错与课后总结等。需综合考虑对话交互的自然度，语音端到端流畅性和延迟性，纠错的精准度与时机，口语能力提升的可量化反馈等。

## PR 规范（必须严格遵守）

- 请基于 PR 添加新功能。每个 PR 只做一件事，只实现或修改单一功能。
- 鼓励尽可能小、粒度尽可能细的 PR；大功能应拆分为多个独立 PR 分步提交。
- 代码变更类 PR 的标题与描述需清晰完整，内容包含：
  - 标题：一句话说明本 PR 新增或修改了什么。
  - 功能描述：说明该功能的作用与使用方式。
  - 实现思路：简要说明技术选型或核心实现逻辑。
  - 测试方式：说明如何验证该功能正常运行。
- 文档、资料整理等非代码变更 PR，只需提供标题和简要修改说明。
- PR 合并后，主分支代码需保持可运行状态，评委在任意时间查看应能复现演示效果。

## 测试数据集脚本（scripts/）

测试用的语音/文本数据来自 4 个公开数据集（LibriSpeech、SpeechOcean762、L2-ARCTIC、JFLEG）。
原始数据包有几个 GB，**不入库**；我们只把抽取后的小样本打包成 `fixture-subset.zip`（约 20MB）提交到 git，任何人 clone 后无需下载原始数据即可跑测试。

### `scripts/extract_fixtures.py` —— 常用：从仓库里的 zip 还原 fixtures

clone 项目后，把 `fixture-subset.zip` 解开到 `fixtures/` 即可：

```powershell
py scripts/extract_fixtures.py
```

它会还原（这两个目录被 .gitignore 忽略，由 zip 派生）：

- `fixtures/generated/`  —— 各数据集的 JSON manifest
- `fixtures/audio/public/`  —— 抽样出来的音频

可选参数：`--bundle-zip <路径>`（默认 `fixture-subset.zip`）、`--dest <目录>`（默认项目根）。

### `scripts/prepare_fixtures.py` —— 仅维护者：从原始数据集重新生成 zip

只有需要更新样本时才用。先把原始数据包放到 `dataset/`（该目录被忽略）：

```text
dataset/
  dev-clean.tar.gz          # LibriSpeech（可选再加 test-clean.tar.gz）
  speechocean762.tar.gz     # SpeechOcean762（OpenSLR 101）
  l2arctic_release_v5.0.zip # L2-ARCTIC
  jfleg-master.zip          # JFLEG
```

然后运行（首次会解压原始包，L2-ARCTIC 较慢）：

```powershell
py scripts/prepare_fixtures.py --bundle-zip fixture-subset.zip
```

生成 `fixtures/generated/`、`fixtures/audio/public/` 和 `fixture-subset.zip`，并打印各数据集抽取数量。

常用参数：

- `--skip-extract` 已解压过、只想重新扫描时用，跳过解压。
- `--convert-wav` 若装了 ffmpeg，把音频统一转成 16kHz 单声道 WAV（否则按原格式拷贝）。

> 注意：L2-ARCTIC 外层 zip 内含各说话人的子 zip（`ABA.zip` 等），SpeechOcean762 的 `scores.json` 在 `resource/` 下需与 `WAVE/` 同级——若是全新原始包，解压后可能需要按这两点调整目录再加 `--skip-extract` 重扫。生成 zip 后改用 `extract_fixtures.py` 即可，无需再碰原始数据。

更新样本的流程：放好原始数据 → `prepare_fixtures.py` 生成新 `fixture-subset.zip` → 提交该 zip。

## 本地开发命令

首次运行先安装依赖：

```bash
make install-backend
make install-frontend
```

常用命令：

```bash
make test
make test-backend
make test-frontend
make dev-backend
make dev-frontend
```

`make test` 会先检查 `fixtures/generated/` 与 `fixtures/audio/public/` 是否存在。
若缺失且项目根目录有 `fixture-subset.zip`，会自动调用
`scripts/extract_fixtures.py` 还原测试数据。

后端开发服务默认监听 `http://127.0.0.1:8000`，健康检查接口：

```text
GET /api/health
```

前端开发服务由 Vite 启动，`/api` 和 `/ws` 会代理到本地 FastAPI 后端。

### 从本地电脑访问服务器上的开发服务

如果服务跑在远程服务器上，`10.x.x.x` 这类地址通常是服务器内网地址，
本地电脑不能直接访问。推荐用 SSH 端口转发：

```bash
ssh -L 5173:127.0.0.1:5173 -L 8000:127.0.0.1:8000 <user>@<server-public-ip>
```

然后在本地浏览器打开：

```text
http://localhost:5173/
```

前端的 `/api` 和 `/ws` 会由 Vite 代理到服务器上的后端。若不用 SSH
转发而是直接用公网 IP 访问，需要在云服务器安全组/防火墙开放 `5173`
端口；通常不需要把 `8000` 暴露给公网。

## 发音评测 Provider

默认发音评测使用 `PRON_PROVIDER=mock`，从 SpeechOcean762 fixture 回放确定性分数，
因此 `make test` 不访问外部服务。

本地后端启动时会自动读取项目根目录 `.env`。若 `.env` 中配置了真实腾讯云 SOE，可直接启动：

```bash
make dev-backend
```

真实 provider 会使用：

- `TENCENT_APP_ID`
- `TENCENT_SECRET_ID`
- `TENCENT_SECRET_KEY`
- `TENCENT_SOE_WS_URL`
- `TENCENT_SOE_SERVER_ENGINE_TYPE`
- `TENCENT_SOE_EVAL_MODE`
- `TENCENT_SOE_SCORE_COEFF`

默认测试仍应保持 mock；真实腾讯链路可用
`python3 scripts/test_tencent_soe.py` 做手动 smoke test。

## ASR / TTS Provider

默认 ASR 使用 `ASR_PROVIDER=fake`，用于稳定测试 WebSocket 协议与对话链路。
真实本地 ASR 使用额外依赖：

- `faster-whisper`：本地 Whisper ASR 推理库，用来把语音转文字。
- `ffmpeg`：音频解码/转码工具，用来把浏览器录音的 `webm/opus` 等格式转为
  ASR 和腾讯 SOE 更稳定的 `16kHz mono wav`。

安装方式：

```bash
make install-backend
python3 -m pip install -e ".[asr]"
conda install -y ffmpeg
```

可先用 fixture 音频做本地 smoke test：

```bash
ASR_PROVIDER=faster_whisper ASR_MODEL_SIZE=tiny python3 scripts/test_asr_provider.py
```

`faster-whisper` 首次使用模型名（如 `tiny`、`small`）时会尝试下载模型。
如果服务器不能访问外网，推荐手动下载 faster-whisper 兼容模型目录，然后把
`ASR_MODEL_SIZE` 设置为本地模型目录路径，例如：

```bash
ASR_PROVIDER=faster_whisper ASR_MODEL_SIZE=/path/to/faster-whisper-small make dev-backend
ASR_PROVIDER=faster_whisper ASR_MODEL_SIZE=/path/to/faster-whisper-small python3 scripts/test_asr_provider.py
```

真实 ASR 集成测试默认不会运行；需要显式执行 integration marker。

TTS 默认使用 `TTS_PROVIDER=browser`，前端通过浏览器 `speechSynthesis`
播放 AI 回复。后端 `/api/tts/synthesize` 当前返回 browser fallback 元数据，
方便后续替换成真实云 TTS provider。

## LLM Provider

语法/表达纠错和场景对话回复都支持接 OpenAI-compatible 大模型接口。
默认 `LLM_PROVIDER=fake`，不会访问网络；fixture 命中时仍优先使用确定性样例，
便于测试复现。

启用真实大模型时，把 OpenAI-compatible 配置写入 `.env` 后启动后端：

```bash
make dev-backend
```

要求接口兼容 `/chat/completions`。真实 LLM 只在 fixture 未命中的自由输入上调用；
JSON 解析失败会降级为当前 fallback，不中断对话。
