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
