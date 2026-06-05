# AI 英语口语陪练竞品调研

## 调研目标

本调研关注市面上英语口语陪练、发音纠正、语法/表达纠错类产品的功能设计，重点不是罗列产品，而是提炼对本项目有用的能力：

- 场景对话如何组织。
- 发音、语法、表达反馈如何呈现。
- 课后总结和学习闭环如何设计。
- 哪些功能适合三天黑客松实现。
- 哪些功能适合放入最终报告，体现实用性和可量化能力。

## 竞品功能观察

| 产品 | 主要方向 | 做得好的功能 | 对本项目的启发 |
|---|---|---|---|
| 流利说 | AI 英语学习、口语练习、课程化训练 | 自适应诊断、AI 老师评估、场景素材、配音课、口语实时打分、雅思模考报告 | 需要形成“测评 -> 学习计划 -> 练习 -> 报告”的闭环 |
| ELSA Speak | 发音和口语反馈 | 多维评分：pronunciation、intonation、fluency、grammar、vocabulary；角色扮演；面试/职场场景 | 发音反馈要分层：总分、单词、音素/重音；总结报告要有明确维度 |
| Speak | AI 语言导师 | 鼓励用户大声说、即时反馈、AI Tutor、个性化课程、解释表达为什么不自然 | 语法纠错不能只改句子，还要解释为什么 awkward 或不适合当前场景 |
| Loora | AI 英语对话陪练 | 真实场景对话、面试/会议/商务、实时反馈、grammar/rephrasing/accent、lesson summary | “对话区 + 教练反馈 + 课后总结”是合理产品结构 |
| Busuu Conversations | 场景化对话训练 | 按 CEFR 难度组织场景对话，场景中有明确任务 | 每个场景应该有任务完成度，而不只是自由聊天 |
| Babbel Speak | AI 对话伙伴 | 轮流对话，结束后反馈任务完成情况和词汇 | 课后总结可以展示“完成了哪些任务、用了哪些新表达” |
| BoldVoice | 口音与发音训练 | 真人教练视频、sound-by-sound 分析、嘴型提示、母语者对比、每日 5-10 分钟任务 | 发音训练可以设计成小目标：每天练少量高频错误音/词 |
| FluencyPal / Speakerly | 口语流利度与反馈 | 自由对话、纠错对话、角色扮演、语法规则练习、进度追踪、filler words / rhythm / pacing 分析 | 可以区分“自由对话”和“纠错练习”，并统计流利度指标 |

## 可借鉴的产品设计

### 1. 场景任务进度

场景不应该只是“换一个主题”，而应该是一组可完成任务。

以面试场景为例：

```text
自我介绍      已完成
项目经历      已完成
求职动机      未完成
优势说明      未完成
反问面试官    未完成
```

这样有三个好处：

- AI 对话更容易推进，不会漫无目的聊天。
- 用户知道自己还需要练什么。
- 最终报告可以量化：`task_completion_rate = completed_tasks / total_tasks`。

建议在场景配置里加入：

```yaml
tasks:
  - id: self_introduction
    label: Self introduction
    required: true
  - id: motivation
    label: Motivation for this role
    required: true
```

### 2. 纠错分层

竞品的共同点是：反馈不会一次性把所有信息压给用户。

建议本项目分成三层：

```text
快速反馈：这一轮最值得改的一处错误
详细反馈：语法、表达、发音、流利度
练习反馈：推荐跟读句、错题本、下次练习
```

例如：

```text
用户：I am very interest this position.

快速反馈：
I am very interested in this position.

详细反馈：
interest -> interested
这里需要形容词 interested，表示“我感兴趣”。

练习反馈：
跟读句：I am very interested in this position.
重点词：interested, position
```

### 3. 解释“为什么不自然”

很多英语学习产品不只改语法，也会解释表达是否适合当前场景。

例如面试场景：

```text
原句：
I want this job because salary is good.

更好表达：
I’m interested in this role because it matches my skills and career goals.

原因：
面试场景下直接强调工资会显得动机不够专业。
```

这类能力比单纯语法纠错更有价值，也更符合“场景口语陪练”。

### 4. 课后总结和下一步练习

课后总结应该是产品闭环的核心，而不是普通聊天记录总结。

建议输出：

```text
语法：72
发音：68
流利度：76
表达自然度：70
场景任务完成度：60%

本次主要问题：
1. be interested in
2. final consonants
3. 面试动机表达

下次 5 分钟练习：
1. 跟读 3 句
2. 复习 2 个常错表达
3. 重新回答 1 个面试问题
```

### 5. 错题本/复习系统

错题本是本项目可以做出差异化的地方。它比单次纠错更能体现学习效果。

建议错题分三类：

| 类型 | 示例 |
|---|---|
| 语法错误 | `I am interest` -> `I am interested in` |
| 更好表达 | `I want this job` -> `I’m excited about this role because...` |
| 发音问题 | `interested` 结尾 `/ɪd/` 弱，`position` 重音不准 |

错题本条目建议包含：

```json
{
  "type": "grammar",
  "wrong": "I am interest this position.",
  "correct": "I am interested in this position.",
  "explanation_zh": "interest 是名词/动词，这里需要 interested。",
  "practice_sentence": "I am very interested in this position.",
  "review_count": 0,
  "mastery": 0.41
}
```

### 6. 每日短练习

BoldVoice 等产品使用短任务降低学习门槛。这个设计适合黑客松 demo，因为它能把错题本和课后总结连接起来。

建议课后自动生成：

```text
今日 5 分钟复习：
- 跟读 3 个句子
- 复习 2 个常错表达
- 重新回答 1 个场景问题
```

这可以作为 `daily_drills` 功能，数据来自错题本和本次总结。

## 对当前实现计划的调整建议

不需要推翻现有 `plan.md`，建议增强以下点：

1. **场景配置系统**
   - 增加 `tasks` 字段，用于对话目标追踪和任务完成率统计。
   - 增加 `cefr_level` 字段，用于控制问题难度和反馈复杂度。

2. **语法/表达纠错服务**
   - 输出中加入 `naturalness_reason_zh`，解释为什么某种表达不自然或不适合当前场景。
   - 区分 `grammar_error`、`unnatural_expression`、`scenario_inappropriate`。

3. **课后总结**
   - 明确输出 `task_completion_rate`。
   - 明确输出 `top_grammar_patterns`、`top_pronunciation_issues`。
   - 增加 `next_5_min_practice`。

4. **错题本**
   - 增加 `daily_drills`，从错题自动生成短练习。
   - 支持按错误类型筛选：语法、表达、发音。

5. **发音评测**
   - 反馈展示分为 `simple` 和 `detailed` 两档。
   - `simple` 用于对话侧边栏，`detailed` 用于课后总结或跟读详情页。

## 黑客松优先级

建议三天内优先实现这些竞品启发功能：

1. 场景任务进度。
2. 语法/表达纠错，并解释为什么不自然。
3. 跟读句发音评测接口，第一版使用 Mock provider。
4. 课后总结，包含多维评分和下一步练习。
5. 错题本，至少支持语法和表达类错题。

可后置功能：

- 真人教练视频。
- 嘴型动画。
- 母语者音频对比。
- 完整 CEFR 分级课程体系。
- 完整每日学习计划。

## 参考链接

- 流利说：https://www.liulishuo.com/
- 流利说 App Store：https://apps.apple.com/cn/app/id597364850
- ELSA Speak：https://elsaspeak.com/
- ELSA Speech Analyzer：https://elsaspeak.com/en/speech-analyzer
- Speak：https://www.speak.com/?lang=en
- Loora：https://www.loora.com/
- Busuu Conversations：https://help.busuu.com/hc/en-gb/articles/21862192336402-What-are-Busuu-Conversations-and-how-can-they-help-me-learn-a-language
- Babbel Speak：https://support.babbel.com/hc/en-us/articles/25875402999826-Babbel-Speak
- BoldVoice：https://apps.apple.com/us/app/boldvoice-accent-training/id1567841142

## 结论

竞品共同证明了一个方向：用户不只是要“AI 陪我聊”，而是要“聊完知道哪里错、为什么错、接下来练什么”。

本项目应该把重点放在学习闭环上：

```text
场景对话
  -> 即时纠错
  -> 跟读评测
  -> 课后总结
  -> 错题本
  -> 下一次短练习
```

这条链路既实用，也方便测试和量化，适合黑客松展示。
