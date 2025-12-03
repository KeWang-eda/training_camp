# LangChain 终端助手优化建议

> 依据 `python_langchain_cn` 教程中的模块化设计理念（参见 `/docs/modules/chains/index.mdx`、`/docs/modules/agents/index.mdx`、`/docs/modules/memory/index.mdx`），结合当前终端项目的实现，梳理后续可演进的方向。本文暂不改动代码，仅作为评估材料。

## 1. 链式（Chain）拆分更清晰
- **问题**：`TerminalChatbotCore.run_testcase_generation` / `_ingest_segments` 中混合了数据收集、prompt 构造、LLM 调用、落盘等逻辑，导致复用困难。
- **建议**：参照教程中“链 = 组件序列”的思路（`python_langchain_cn/docs/modules/chains/index.mdx`），把“上下文拼接 → prompt 渲染 → LLM 调用 → 输出格式化”拆成 LCEL/Runnable 链；这样后续可将链暴露为可测试单元，也可快速插入新的链（如自省、审阅链）。

## 2. 引入工具化 Agent 处理多类型文档
- **问题**：当前 `/read` `/read_link` 完全依赖硬编码流程；若未来需要自动判断“是本地文档/Feishu/URL/数据库”并选择不同处理器，需要手动添加分支。
- **建议**：根据教程中代理“基于工具选择动作”的模式（`python_langchain_cn/docs/modules/agents/index.mdx`），封装一个轻量 Agent：给它的工具包括 `ingest_local_files`、`ingest_feishu_document`、`ingest_web_url`（预留）。CLI 传入指令后由 Agent 判断调用哪个工具，可减少 if/else，同时保留扩展空间（如后续接 SDK、图像 OCR 工具）。

## 3. 记忆与上下文管理
- **问题**：`loaded_segments` 只是简单列表，`ask()` 时未区分“对话记忆（chat_history）”与“文档记忆”，长对话易超 token；而 LangChain 建议将聊天消息与向量上下文分开管理。
- **建议**：参考 Memory 教程（`python_langchain_cn/docs/modules/memory/index.mdx`）使用 `RunnableWithMessageHistory` 或自定义 Memory，将 chat_history / 文档摘要 / 最近 RAG 结果分层保存；同时可在 `case_health`、`run_evaluation` 中调用 Memory 以回溯不同版本的评测结果。

## 4. 多阶段生成与评测
- **问题**：用例生成→评测仍是单轮调用；无法按需求拆分为“生成 → 审阅 → 评测 → 修订”。
- **建议**：借鉴 Chains+Agents 教程，构建一个“计划型”链：
  1. 规划阶段（Planner Agent）列出需要生成的测试模块。
  2. 针对每个模块调用生成链。
  3. 由评测链（Evaluation Agent）给出反馈，再写回报告。
  这种结构便于复用，也符合 LangChain “Plan-and-execute” 的最佳实践。

## 5. 配置与 Prompt 体系
- **问题**：`config.yaml` 中 prompt 目前集中在 `testcase_modes`、`evaluation_metrics`，但图片分类/描述 prompt 只有一个 classifier + 各类型 prompt；缺少默认 fallback、prompt 版本记录。
- **建议**：引入类似 tutorial 中的“Toolkits + PromptTemplate”概念，为每类任务（生成 / 评测 / 图片分类）维护 `version`、`author`、`last_review` 字段，未来可基于版本控制进行离线评测对比。

## 6. 评测指标接口
- **问题**：当前 `case_health` 仍是占位实现；`evaluation_metrics` 全靠 LLM+Prompt，缺少结构化输出（如 JSON）。
- **建议**：定义 `EvaluationResult` 数据结构，支持 `score`, `rationale`, `suggestions` 字段；配合教程中的 “LangChain 评估” 章节思路，可把 LLM 结果解析为结构化数据，再汇总成报告。

---
以上建议优先级可按下述顺序推进：①链式拆分 → ②评测结构化 → ③Agent 化摄取 → ④Memory 分层 → ⑤配置元数据化。这样既能保证代码清晰，也方便引用 LangChain 官方教程中的最佳实践。
