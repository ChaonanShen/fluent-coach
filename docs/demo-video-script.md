# 演示视频讲稿

本文是一份录制演示视频时可参考的讲稿。建议录制顺序是：开场介绍、Job Interview、Custom 医生问诊、Reading Practice、Mistake Book、收尾总结。整体控制在 8 到 12 分钟即可。

录制前建议准备：

- 后端和前端已启动，浏览器打开 `http://localhost:5173/`。
- `.env` 已配置真实 LLM、ASR 和腾讯云 SOE，`PRON_ASSESS_AUDIO_TURNS=1`。
- 浏览器麦克风权限已允许，TTS 使用 Edge 或 Chrome 效果更稳定。
- 如果想稳定演示语法纠错，Job Interview 场景可优先使用本文给出的固定错误句。

## 1. 开场

画面停在首页，对准标题和三个区域。

讲述：

> 大家好，这个系统是一个 AI 英语口语陪练工具。它支持面试、点餐、工作会议和自定义场景练习。用户可以用文字或语音和 AI 对话，系统会在对话过程中给出语法、表达和发音反馈，并在结束后生成总结。练习中出现的问题也会沉淀到错题本里，方便后续复习和跟读纠错。

继续讲述：

> 这次演示我会展示两个场景：第一个是 Job Interview，第二个是自定义的医生问诊场景。最后我会演示自由朗读练习区和错题本，尤其是发音错题里标准朗读和跟读评估这两个按钮。

## 2. Job Interview 场景

### 2.1 开始会话

操作：

1. 场景选择 `Job Interview`。
2. 点击 `Start`。
3. 等 AI 开场白出现。

讲述：

> 这里选择 Job Interview。点击 Start 后，系统会创建一次练习会话，AI 先扮演面试官发起开场问题。左边是对话区域，中间是 Conversation Assessment，用来展示每一轮的纠错和发音反馈，右边是 Reading Practice、错题本入口、Timing 和结束后的 Summary。

### 2.2 第一轮：自我介绍，制造时态和介词错误

建议用文字输入，保证纠错稳定。

输入：

```text
I am working in this field since three years.
```

讲述：

> 我这里故意输入一个常见错误：I am working in this field since three years。它的问题是，从过去持续到现在的经历应该用现在完成进行时，而且持续时长通常用 for，不用 since。

等 AI 回复和评估结果出现后讲述：

> 可以看到系统没有打断对话，AI 继续像面试官一样追问；同时中间的评估区域会显示 Original、Corrected 和中文解释。这里会把句子修正成 I have been working in this field for three years，并解释时态和介词问题。

### 2.3 第二轮：项目经历，制造表达和比较级错误

输入：

```text
My last project make the team more faster.
```

讲述：

> 第二轮我继续故意说得不太自然。这里 make 应该用过去式 made，more faster 也是重复比较级。系统除了语法修正，还会给出更自然的表达，比如 helped the team work more efficiently。

等反馈后补充：

> 这类反馈比较适合口语学习，因为它不是只告诉你对错，还会给一个更适合面试场景的表达方式。

### 2.4 第三轮：语音输入，制造发音问题

建议用语音录入。录音时尽量让 ASR 仍能识别文本，但刻意把 `with` 或 `three` 读得不清楚。

朗读：

```text
I was responsible for communicating with customers.
```

录制技巧：

- 把 `with` 的 `th` 发得含糊一些，接近 `wiz`。
- 或者把 `three` 发得接近 `tree`。

讲述：

> 接下来我用 Record 发送语音。语音会先经过 ASR 转写，然后进入同样的对话链路。因为我会故意把某个单词发得不清楚，所以如果发音评测识别到问题，中间的 Original 里会直接高亮低分单词，并显示 Overall、Accuracy 和 Fluency。

等 Timing 出现后讲述：

> 右侧 Timing 会记录这轮链路的耗时，包括 ASR、AI 回复、语法分析、发音评测和 TTS。这个区域主要用来观察端到端响应速度。

### 2.5 第四轮：问面试官问题，制造职业表达问题

输入：

```text
I want to know how much salary you can give me.
```

讲述：

> 最后一轮我演示一个表达问题。这个句子语法上能理解，但在面试里不够职业。系统会建议更礼貌、更自然的表达，比如 Could you share the expected salary range for this role?

### 2.6 结束会话并看 Summary

操作：

1. 点击 `End`。
2. 等右侧 `Summary` 出现。

讲述：

> 点击 End 后，本轮练习结束。系统会生成 Summary，从 Overall、Grammar、Pronunciation、Fluency、Vocabulary 这些维度总结这次练习。这个总结适合用户快速判断本轮主要问题在哪里。

## 3. Custom 医生问诊场景

### 3.1 创建自定义场景

操作：

1. 切换场景到 `Custom`。
2. 输入自定义场景描述。
3. 点击 `Start`。

自定义场景描述：

```text
I want to practice a doctor consultation. The AI is a doctor in a clinic, and I am a patient describing symptoms and asking what to do next.
```

讲述：

> 除了内置场景，这个系统也支持自定义场景。我这里输入医生问诊，系统会生成一个 Doctor Consultation 场景，让 AI 扮演医生，用户扮演病人。自定义场景同样会有开场白、目标表达和纠错重点。

### 3.2 第一轮：描述症状，制造持续时间表达错误

建议用文字输入。

输入：

```text
I have headache since two days.
```

讲述：

> 我先描述症状，并故意说 I have headache since two days。这里更自然的说法是 I have had a headache for two days，既要注意冠词，也要注意持续时间表达。

等反馈后讲述：

> 自定义场景下，系统仍然会根据当前角色和上下文做纠错。医生会继续追问症状，评估区会给出这一轮的修正和解释。

### 3.3 第二轮：回答医生追问，制造句型错误

输入：

```text
My throat is pain and I feel tired very much.
```

讲述：

> 第二轮我继续回答医生问题。这个句子里 My throat is pain 不自然，应该说 My throat hurts，或者 I have a sore throat。I feel tired very much 也可以改成 I feel very tired。

### 3.4 第三轮：语音输入，制造发音问题

建议用语音录入。重点放在 `throat`、`symptoms`、`three` 这类容易出问题的词。

朗读：

```text
The pain gets worse when I swallow, and I have had these symptoms for three days.
```

录制技巧：

- 把 `throat` 或 `three` 的 `th` 发得不清楚。
- 不要太夸张，避免 ASR 完全识别错整句。

讲述：

> 这里我再用语音输入一次。医生问诊场景很适合练习症状描述，比如 pain gets worse when I swallow，以及 I have had these symptoms for three days。系统会同时评估表达和发音。

### 3.5 第四轮：询问下一步，制造表达问题

输入：

```text
What medicine I should eat?
```

讲述：

> 最后一轮我问医生下一步该怎么做。What medicine I should eat 是中式表达，系统应该会建议 What medicine should I take? 或 What should I do next? 这类更自然的问法。

结束该会话后讲述：

> 结束后，自定义场景也会生成 Summary，并且本轮出现的问题同样会进入错题本。

## 4. Reading Practice 自由朗读练习

操作：

1. 回到练习页右侧 `Reading Practice`。
2. 点击 `Record Reading`。
3. 朗读一句英文。
4. 点击停止，等待评估结果。

朗读句子：

```text
I went to the store with my friend, and we talked about three symptoms.
```

录制技巧：

- 把 `with`、`three` 或 `symptoms` 读得稍微不清楚。

讲述：

> Reading Practice 是自由练习区，不依赖当前对话轮次。用户可以随便读一句英文，系统会先显示转写文本，再返回发音评测。这里适合单独练一句话，尤其是练习某些容易发错的单词。

补充：

> 和对话区不同，这里不需要 AI 角色继续回复，它更像一个独立的发音检测工具。

## 5. Mistake Book 错题本演示

### 5.1 进入错题本

操作：

1. 点击右侧 `Mistake Book`。
2. 选择刚才生成的会话错题本。

讲述：

> 现在进入错题本。错题本是按会话保存的，每一次练习会生成一本错题本。顶部可以看到本次会话的综合分、语法分、发音分、流利度和词汇分，也能看到 Grammar、Expression、Pronunciation 各类错题数量。

### 5.2 讲解语法和表达错题

操作：

1. 展示 `Grammar` 或 `Expression` 条目。
2. 指向原句、修正句和中文解释。

讲述：

> 这里的语法和表达错题会保留用户原来的错误片段、系统推荐的修正，以及中文解释。比如面试里 I am working in this field since three years，会被整理成时态和介词问题；I want to know how much salary you can give me，则会被整理成更职业、更礼貌的表达问题。

### 5.3 讲解发音错题和跟读按钮

操作：

1. 找到 `Pronunciation` 条目。
2. 点击目标单词前的播放按钮。
3. 点击麦克风按钮进行跟读。
4. 等跟读评估结果出现。

讲述：

> 发音错题会把低分单词单独整理出来。每个发音错题有两个很重要的按钮：播放按钮可以听标准读音，麦克风按钮可以跟读并重新评估。这样用户不是只看到自己哪里错了，还能马上针对这个词或练习句做纠正。

继续讲述：

> 例如这里如果 `with`、`three` 或 `symptoms` 被评为低分，用户可以先听标准发音，再录一次自己的发音。系统会返回新的分数，帮助用户形成一个从发现问题到纠正问题的闭环。

### 5.4 删除和返回练习

操作：

1. 简单指一下单条 `Delete`。
2. 点击 `Back to Practice` 返回。

讲述：

> 错题本也支持删除单条错题或者删除整本错题本。复习完之后可以点击 Back to Practice 回到练习页继续新的会话。

## 6. 收尾

讲述：

> 这就是系统的完整演示流程：用户可以选择内置场景或自定义场景进行多轮英语对话；系统在对话过程中给出语法、表达和发音反馈；结束后生成总结；所有问题沉淀到错题本里，并支持发音标准朗读和跟读评估。整体目标是把一次口语练习从“开口说”延伸到“知道哪里错、怎么改、如何复习”。

## 7. 录制时的备用台词

如果现场某个错误没有被识别，可以替换为这些更稳定的句子：

Job Interview：

```text
I responsible for communicate with customers.
I think I am suitable to this position.
In my previous company, I learn how to lead a small team.
I am very interested about your company culture.
```

医生问诊：

```text
I have fever since yesterday night.
My stomach is pain after I eat dinner.
I feel dizzy when I standing up.
What should I do next if the pain become worse?
```

发音练习：

```text
I have three symptoms and a sore throat.
The team reviewed the systems before launch.
I went to the store with my friend.
```
