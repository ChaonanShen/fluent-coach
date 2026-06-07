# 文档索引

`docs/` 存放设计说明、实现计划、调研资料和长文档。根目录只保留
`README.md` 与 `README.dev.md`。

## 产品与系统说明

- [user-facing-system-guide.md](user-facing-system-guide.md)：用户视角系统说明，解释场景选择、对话流程、评估面板、错题本和评分标签。
- [competitor-research.md](competitor-research.md)：英语口语陪练竞品调研，用于产品功能取舍、报告表达和后续路线规划。
- [plan.md](plan.md)：历史实现计划和 PR 拆分记录，用作项目背景和决策历史，不作为当前用户使用指南。

## 自动化测试与 Bench

- [bench-framework-guide.md](bench-framework-guide.md)：后端自动化 bench 框架和只读 dashboard 的使用说明。运行 `scripts/run_conversation_bench.py` 或 `scripts/bench_dashboard.py` 前先看这里。
- [test-framework-plan.md](test-framework-plan.md)：自动多轮后端测试框架的高层设计。
- [test-framework-impl-plan.md](test-framework-impl-plan.md)：自动测试框架的详细实现计划。

## Provider 与 Fixture 维护

- [tencent-soe-test-notes.md](tencent-soe-test-notes.md)：腾讯云 SOE 已验证配置、`.env` 关键项和 smoke test 记录。
- [local-agent-prompt.md](local-agent-prompt.md)：在本地 Windows 机器准备 fixture 子集的代理提示词，用于生成并上传 `fixture-subset.zip`。

## 根目录相关文档

- [../README.md](../README.md)：用户向安装、配置、产品功能总览和带截图的使用流程说明。
- [../README.dev.md](../README.dev.md)：开发流程、测试命令、provider 配置和环境隔离约定。
