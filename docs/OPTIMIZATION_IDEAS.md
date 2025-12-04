# LangChain 终端助手优化建议

> 结合 `python_langchain_cn` 教程中“链、Agent、Memory”最佳实践，针对 2025-12-03 版本的实现盘点后续可演进方向。本文仅提出思路，不直接改动代码。

## 1. 生成/评测链路解耦
- **现状**：`TerminalChatbotCore` 同时负责上下文构造、Prompt 渲染、模型调用、落盘；逻辑集中使得测试与复用成本较高。
- **建议**：参照“LCEL = 可组合 Runnable 链”（`python_langchain_cn/docs/modules/chains/index.mdx`），将“上下文拼接 → Planner → Builder → 渲染”拆分为独立 Runnable，评审链亦同。这样可以：
  - 为 Planner/Builder/Renderer 分别编写单元测试；
  - 支持插入额外环节（如自省、回写修订）而无需修改 Orchestrator；
  - 暴露链配置，方便脚本或服务模式复用。

## 2. 工具化 Agent 的摄取策略
- **现状**：`/read` 与 `/read_link` 通过 if/else 选择不同处理器，未来若新增 URL/数据库/云盘，需要继续堆叠分支。
- **建议**：引入轻量 Tool Agent（`python_langchain_cn/docs/modules/agents/index.mdx`），定义 `ingest_local_files`、`ingest_feishu_document`、`ingest_web_url`（预留）等工具，让 Agent 根据输入自动选择执行。优势：
  - CLI 层保持单一命令 `/ingest`，降低用户心智负担；
  - 后续扩展只需注册新工具，避免改动核心流程；
  - 可记录工具调用日志，为摄取链压测提供数据。

## 3. 记忆体系分层与统一
- **现状**：`MemoryManager` 已托管聊天/文档摘要/评审历史，但 `TerminalChatbotCore` 仍维护一份 `conversation_history`。RAG 历史与对话记忆尚未统一。
- **建议**：对标 Memory 教程（`python_langchain_cn/docs/modules/memory/index.mdx`），实现：
  - 使用 `RunnableWithMessageHistory` 统一管理对话记忆，避免双份缓存；
  - 文档摘要、最新评审结果继续存入 Memory，由链路按需读取；
  - 为 `/generate_cases` 和 `/evaluate_cases` 添加“引用历史上下文”的显式开关，减少 token 压力。

## 4. 多阶段生成/评审闭环
- **现状**：当前流程是“生成一次 → 评审一次”，评审建议不会自动触发修订。
- **建议**：尝试“Plan → Execute → Review → Refine”的分阶段策略：
  1. Planner 产出模块计划；
  2. Builder 按模块生成初稿；
  3. Evaluation Agent 给出结构化建议；
  4. Refinement 链读取建议自动补齐缺失用例，或在终端提示交互；
  这可以借鉴 LangChain ReAct / Plan-and-execute 模式，形成闭环并减少人工手动修订次数。

## 5. Prompt 元数据与版本资产化
- **现状**：`testcase_modes`、`image_prompts` 已附带 `metadata.version`，但缺少作者、最近验证时间等信息，也没有集中对比工具。
- **建议**：
  - 维护 `docs/PROMPT_REGISTRY.md`，记录每个 Prompt 的 `version/owner/last_review/测试记录`
  - 配合脚本将 `config.yaml` 中的 prompt 导出成单独文件，便于 diff 与灰度；
  - 在 `/evaluate_cases` 报告 metadata 中写入 prompt 版本，支持回溯“哪套模板导致评审波动”。

## 6. 观测与性能优化
- **现状**：`EvaluationEngine._infer_level` 对相同文本多次调用 LLM；文件写入缺少原子性；脚本执行日志主要依赖文本。
- **建议**：
  - 为 `_infer_level` 增加最近 N 条 LRU 缓存，或引入局部规则（如关键字映射）减少重复调用；
  - 抽象 `utils/io.py` 实现原子写入（临时文件 + `Path.replace`），同时对写入结果加上 structured log；
  - 扩展脚本日志为 JSON Lines（命令 + 时长 + 成功/失败 + 输出路径），便于数据分析。
