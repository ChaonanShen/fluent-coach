# 用户视角系统说明

本文从用户使用产品的角度说明 AI 英语口语陪练的主要部件，以及系统如何给语法、表达和发音问题分层打标签。

## 1. 场景选择

用户进入练习页后，先选择一个对话场景：

- `Job Interview`：面试练习。AI 扮演招聘经理，用户练习自我介绍、项目经历、行为问题和反问团队。
- `Restaurant Ordering`：餐厅点餐。AI 扮演服务员，用户练习询问菜单、点餐、特殊要求和处理服务问题。
- `Work Meeting`：工作会议。AI 扮演项目负责人，用户练习进度汇报、风险说明、优先级澄清和下一步确认。
- `Custom`：自定义场景。用户输入想练习的英文对话场景，系统生成对应角色、开场白、目标表达和评分关注点。

每个场景都有自己的对话目标、推荐表达和纠错重点。总结分数中的任务完成度、词汇表现等，会参考这些场景配置。

## 2. 对话区

对话区是主要练习入口。

- `Start` 开始一轮场景对话，AI 会先给出开场白。
- 用户可以用文字发送，也可以点击 `Record` 进行语音对话。
- 语音模式下，ASR 完成后会先把用户说的话显示在聊天框；LLM 回复到达后，再显示 AI 回复并播放语音。
- AI 回复只推进角色扮演，不在聊天回复里直接讲语法课；纠错内容放在评估面板和错题本里。

## 3. Conversation Assessment

`Conversation Assessment` 展示当前对话中的核心反馈，分成两个主要部分。

### Grammar / Expression Correction

这里展示语法和表达修正。

- `Original`：用户原话。
- `Corrected`：系统修正后的版本。
- 下方中文解释说明主要问题。
- 多轮对话会保留历史，但区域固定高度，默认滚动到最新一条。

语法和表达在数据层是分开的：语法问题来自具体错误点，表达问题通常是“这句话可以更自然、更职业、更贴合场景”。

### Pronunciation

这里展示发音评测。

- 先展示 `Low-score words`，也就是低分单词序列。
- 再展示 `Overall`、`Accuracy`、`Fluency` 三个分数。
- 多轮语音对话的发音结果同样保留历史，并在固定区域内滚动。

## 4. Reading Practice

`Reading Practice` 是独立练习区，不依赖当前对话轮次。

- `Record Reading` 可以随时使用。
- 上方文本框不是用户输入框，而是显示用户刚刚读出来的转写内容。
- 用户可以随便读一句英文，系统会返回发音评测。
- 评测结果同样先显示低分单词，再显示 `Overall`、`Accuracy`、`Fluency`。

这个区下面还放了三个辅助模块：

- `Mistake Book` 入口。
- `Timing`：显示 ASR、LLM 回复、语法分析、发音评测、TTS 等耗时。
- `Summary`：显示本轮练习的总体指标。

## 5. Mistake Book

`Mistake Book` 按对话保存错题。

- 列表页按会话展示错题本，并显示总数、语法数、表达数、发音数。
- 详情页可以按 `Grammar`、`Expression`、`Pronunciation` 过滤。
- 每条错题右上角有删除按钮。
- 语法/表达错题展示原错误片段、修正版和中文解释。
- 发音错题展示目标单词和练习句，不重复展示同一个单词的 wrong/correct。
- 发音错题里的目标单词和练习句前面有两个图标按钮：播放标准读音、录音跟读评测。

发音错题中的练习句不是用户原句，而是系统围绕目标词生成的新句子，避免把用户原句里的语法错误带进跟读练习。

## 6. Summary

`Summary` 是当前会话的整体表现概览，当前展示这些指标：

- `Overall`：综合分。
- `Grammar`：语法表现。
- `Pronunciation`：发音表现。
- `Fluency`：流畅度。
- `Vocabulary`：是否使用了场景目标表达和相关词汇。

系统内部还会统计 `top_issues`，用于记录高频问题；当前界面主要展示分数，不展示旧版的 drill 文案。

## 7. 错误分层与标签

系统对错误大致分成四层：面板区域、错题大类、细分标签、严重程度/时机。

### 第一层：反馈区域

- `Grammar / Expression Correction`：语法和表达修正。
- `Pronunciation`：发音评测。
- `Timing`：性能耗时，不是语言错误。
- `Summary`：整体表现指标，不是单条错误。

### 第二层：错题大类

保存到错题本时，每条错题都有一个大类：

- `grammar`：语法错误，例如时态、冠词、介词、句型等。
- `expression`：表达优化，例如更自然、更礼貌、更职业的说法。
- `pronunciation`：发音问题，主要是低分单词。

用户在错题本里看到的 `Grammar / Expression / Pronunciation` 计数来自这一层。

### 第三层：细分标签

细分标签保存在错题的 `subtype` 或内部 word issue 中，用来说明具体问题类型。

#### Grammar 标签

这些标签来自语法纠错的 `error_type`：

- `tense`：时态错误，例如该用过去式或现在完成时。
- `preposition`：介词错误，例如 `interested in` 不是 `interested about`。
- `article`：冠词错误，也就是 `a / an / the` 漏用、多用或用错。
- `word_choice`：用词不自然或不准确。
- `comparative_form`：比较级形式错误，例如 `more faster`。
- `missing_verb`：缺少动词或 be 动词。
- `gerund_after_preposition`：介词后动词形式错误，例如 `for communicate` 应为 `for communicating`。
- `professional_tone`：职业场景语气不够合适。
- `politeness`：礼貌程度不够，常见于点餐、会议请求等。
- `countability`：可数/不可数名词错误，例如 `a waters`。
- `sentence_structure`：句子结构错误。
- `missing_auxiliary`：疑问句等缺少助动词，例如缺少 `do/does`。
- `intensifier`：程度副词使用错误，例如 `too much salty`。
- `subject_verb_agreement`：主谓一致错误，例如复数主语配了单数动词。
- `time_marker`：时间标记和时态搭配不当，例如 `yesterday` 搭配现在完成时。
- `infinitive`：不定式结构错误，例如 `need discuss` 应为 `need to discuss`。
- `redundant_preposition`：多余介词，例如 `discuss about`。
- `verb_pattern`：动词搭配结构错误，例如 `explain me` 应为 `explain ... to me`。
- `time_clause`：时间状语从句时态错误，例如 `when I will finish it`。
- `modal_verb`：情态动词后动词形式错误，例如 `can pushing`。

#### Expression 标签

- `natural_expression`：表达可以更自然、更职业或更贴合当前场景。它不是严格语法错误，但会进入错题本，方便用户复习更好的说法。

#### Pronunciation 标签

发音有两个相关标记：

- `low_accuracy`：单词分数低于阈值时，单词分数里会标为低准确度，用于界面高亮低分单词。
- `word_accuracy`：保存到错题本的发音错题 subtype，表示某个单词的发音准确度偏低，需要单独跟读。

### 第四层：严重程度和纠错时机

每个语法/表达 issue 还会带严重程度：

- `major`：主要错误，明显影响准确性、自然度或场景表达。
- `minor`：较小错误，不一定影响理解，但值得优化。

语法纠错还有时机标记：

- `immediate_light`：适合较快指出的轻量纠错。
- `after_turn`：本轮结束后展示。
- `delayed_summary`：更适合放到总结阶段的表达或语气问题。

这些字段主要帮助系统决定如何展示和统计，用户通常只会看到修正内容、中文解释、错题分类和总结分数。

