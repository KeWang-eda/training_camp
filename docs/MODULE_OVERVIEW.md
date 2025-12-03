# 模块拆分与设计指南

> 本文基于 2025-12-03 的 `training_camp` 代码撰写，重点说明终端态 LangChain 助手的执行流程、核心模块、配置入口与可扩展点，方便后续维护与二次开发。

## 1. 系统总览

```
┌───────────────────────────────────────────────────────────┐
│                        cli.py                             │
│  • 解析参数 (--config/-f/--log-file)                      │
│  • 加载 config.yaml → 构造 TerminalChatbotCore            │
│  • 初始化 CommandHandler 与 PromptSession                 │
└───────────────┬───────────────────────────────────────────┘
                │
        用户输入/脚本命令 (/read、/generate_cases、…)
                │
┌───────────────▼───────────────────────────────────────────┐
│           CommandHandler (src/terminal)                   │
│  • 解析命令 → 调用 TerminalChatbotCore 对应能力            │
│  • 支持自定义命令（来自 config.commands）                 │
│  • 负责终端展示 (Rich Table/Panel)                        │
└───────────────┬───────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────┐
│        TerminalChatbotCore (src/chatbot)                  │
│  • LLM 与 RAG 管理 (ChatbotCore + ConversationalRetrieval)│
│  • 文档摄取 (ContentProcessor + FeishuDocClient + Memory) │
│  • 用例生成 (TestcaseGenerator + layouts/modes)           │
│  • 评审评分 (EvaluationEngine + review_metrics)           │
│  • 输出缓存与落盘 (tests/evaluations/latest cache)        │
└───────────────┬───────────────────────────────────────────┘
                │
      ┌─────────┴──────────┐             ┌─────────────────┴───────────┐
      │ ContentProcessor   │             │ EvaluationEngine/TestcaseGen│
      │ • 文本/图片/文档解析│             │ • Prompt 注入 + JSON Schema │
      │ • ImageAnalyzer 分类│             │ • 风险扣分 + JSON 报告      │
      └────────────────────┘             └─────────────────────────────┘

输出：`output/testcases/*.json|md`、`output/evaluations/*report.json`、`output/logs/`、`output/latest_testcase.json`
```

### 1.1 核心数据流
1. **启动**：`cli.py` 读取 `config.yaml`，计算配置哈希，实例化 `TerminalChatbotCore`、`CommandHandler` 与 `PromptSession`，并在终端展示欢迎 Banner。
2. **命令处理**：用户输入以 `/` 开头的命令由 `CommandHandler.process` 捕获；普通文本走 `handle_chat_message` → `TerminalChatbotCore.ask`。
3. **文档摄取**：`/read`、`/read_link` 触发 `ingest_local_files` / `ingest_feishu_document` → `ContentProcessor` 统一转换为 `ContentSegment` → 建立 FAISS 向量库并刷新 RAG Chain，同步写入 `MemoryManager`。
4. **对话 / RAG**：`ask` 根据是否存在向量库选择基础对话或 RAG（`ConversationalRetrievalChain`），并维护最近 `history_limit` 条对话记录。
5. **用例生成**：`/generate_cases` 读取 `testcase_modes` → 规划模块 → 按 `testcase_layouts` 生成 JSON → 渲染 Markdown/JSON → 落盘并更新 `output/latest_testcase.json`；可选输出 Planner 思考与“测试方案摘要”。
6. **评审得分**：`/evaluate_cases` 自动补全缺失的基线/候选文件 → `_calculate_case_health` 作为兜底基准 → `EvaluationEngine.evaluate` 依次按 `review_metrics` 评分（解析模型输出、推断优先级、风险扣分）→ 生成结构化 JSON 报告并落盘。
7. **脚本批处理**：`cli.py -f script.tcl` 或 `pipeline/run_all_scripts.sh` 逐条执行命令脚本，标准输出与日志文件同步记录。

> 注意：每次文档摄取会用“新批次”构建向量库，历史文件的内容会通过 `MemoryManager` 的摘要保留，但向量检索仅对当前批次生效。

## 2. 模块与职责

| 模块 | 主要文件 | 职责概述 | 关键扩展点 |
| ---- | -------- | -------- | ---------- |
| CLI 层 | `cli.py` | 启动、配置解析、REPL/脚本模式、状态回调 | 支持更多参数、接入 UI 入口、配置哈希透传 |
| 终端交互 | `src/terminal/command_handler.py`, `stream_handler.py` | 命令解析、帮助输出、流式渲染 | 增加内置命令、丰富输出样式、增强脚本日志 |
| LLM/RAG | `src/chatbot/chatbot_core.py` | 初始化 Kimi LLM、FastEmbed、FAISS、对话链路 | 接入其他模型、替换链路为 LangGraph、多检索合并 |
| Orchestrator | `src/chatbot/terminal_chatbot_core.py` | 统一调度：摄取、聊天、生成、评审、落盘、缓存 | 引入异步任务、增量向量库、并发生成/评审 |
| 内容处理 | `src/chatbot/content_processor.py`, `utils/image_analyzer.py`, `utils/feishu_client.py` | 本地文件解析、图片分类描述、飞书 API 拉取 | 新增文件类型、使用更稳定的 OCR/文档解析、接入其他云盘 |
| 测试生成 | `src/chatbot/testcase_generator.py` | 模式管理、Planner+Builder Prompt、Schema 驱动输出 | 支持多模型协同、引入温度控制、完善 fallback 策略 |
| 评审体系 | `src/chatbot/evaluation_engine.py` | 逐项评分、风险扣分、建议结构化、历史记录 | 切换成自研评分器、并行多模型、引入硬指标对齐 |
| 内存与缓存 | `src/chatbot/memory_manager.py` | 聊天历史、文档摘要、评审记录、最近用例缓存 | 提供持久化、按会话隔离缓存、统计面板 |

## 3. 关键模块详解

### 3.1 `cli.py`
- `parse_args()`：支持 `--config`、`-f/--file`（脚本模式）、`--log-file`。脚本模式执行完即退出。
- `load_config()`、`resolve_setting()`：按照 “config → 环境变量 → 默认值” 的优先级解析 API Key、模型、Base URL 等。
- `build_status_callback()`：将内部状态输出到 Rich Console，统一使用 info/warning/success/error 四种颜色。
- `run_script_file()`：按顺序执行 `.tcl/.txt` 命令脚本，写入时间戳和结果到 log 文件，遇到报错或 `/exit` 会立即终止。

### 3.2 `TerminalChatbotCore`
- **模型与链路**：在构造函数中初始化 `ChatbotCore`，获取 LLM 和基于系统 Prompt 的基础链路；摄取成功后再构建 `ConversationalRetrievalChain`。
- **文档摄取**：`ingest_local_files` / `ingest_feishu_document` → `_ingest_segments`
  - 将文件转换为 `ContentSegment`，写入 `loaded_segments` 与 `MemoryManager.document_summaries`。
  - 使用最新一批 `ContentSegment` 重建 FAISS；若需保留历史，可改为合并 `loaded_segments` 或引入增量索引。
- **聊天历史**：`ask()` 依赖 `_select_chain` 判断 RAG；`MemoryManager.add_chat_message` 按 `history_limit` 裁剪。
- **用例生成**：
  - `_resolve_mode_config`：从 `testcase_modes` 读取 planner/builder Prompt、上下文限制、关联模板；若未配置则 fallback 到 `default`。
  - `TestcaseGenerator.generate`：规划模块 → 生成 JSON → 解析失败时将原始输出写入 `fallback_content`，确保可追溯。
  - `_render_testcase_document`：Markdown 头部附带 `generated_at`, `config_hash`；JSON 格式包含完整 `document` 与 metadata。
  - `_write_output`：按照 `outputs.testcases.default_dir` 落盘，文件名为 `yyyyMMdd_HHmmss_<suffix>`，同时更新 `latest_testcase_cache`。
- **评审流程**：
  - `_build_metric_configs` 将 `evaluation_metrics`（可选）转换为 `EvaluationMetric`。
  - `_calculate_case_health` 对候选用例做简单质量预估（字段齐备度 + 行数），作为 LLM 评分的兜底值。
  - `EvaluationEngine.evaluate` 返回 `EvaluationResult` 列表，统一 JSON 序列化并写入 `outputs.evaluations.default_dir`。

### 3.3 `TestcaseGenerator`
- **布局驱动**：初始化时加载 `layout_config`；若没有配置会回退到内置 basic 模板。
- **规划阶段**：`_plan_modules` 将 planner prompt + `{context}` + `{mode}` 注入 LLM，返回模块列表（每行一项），最少保证 1 个默认模块。
- **生成阶段**：`_build_cases` 将 `layout_schema`、模块名、上下文传递给 builder prompt，要求输出固定 JSON；失败时以原文本写入 `fallback_content`。
- **摘要与计划**：`_build_plan_summary` 读取 layout 的 checklist，注入模块名后返回 `TestPlanSection` 列表，供 `/generate_cases plan=true` 展示。

### 3.4 `EvaluationEngine`
- 每个 `ReviewMetricConfig` 都包含 `prompt`、`system_prompt`、可选 `format_hint`；运行时强制模型返回 JSON。
- **风险扣分**：`_run_structured_review`
  - 将模型返回的 `risks` 或 `suggestions` 转换为统一结构，尝试从 `priority/level/deduction` 推断严重度；若缺失则调用 `_infer_level` 复用同一 LLM 判断。
  - 总扣分 = 建议列表中的 `deduction` 求和（默认 10-level），得分 = `100 - total_deduction`，并附带 `penalty_summary`。
- 将所有结果存入 `MemoryManager.evaluations`，便于后续回溯。

### 3.5 `ContentProcessor`
- 支持文本、常规办公文档（依赖 Vision 模型解析）、常见图片格式。
- 图片解析流程：分类 Prompt → `ImageAnalyzer.classify_image` → 选择对应描述 Prompt → `ImageAnalyzer.analyze_image`。
- 若缺少 `image_analyzer`（即未配置图片模型），会输出警告并返回空内容。

### 3.6 `CommandHandler`
- `_parse_generate_args` 统一解析键值/位置参数，兼容 `mode=smoke output=... thoughts=true` 与 `/generate_cases smoke output.json true markdown true`。
- 自定义命令：模板变量包含 `{history}`（最近 10 条消息）、`{args}`（用户输入的剩余文本）。返回的 payload 会在 CLI 层再次走 `handle_chat_message`。
- `evaluate_cases` 执行完会尝试解析最新报告，实时给出 alignment/coverage/bug_prevention 的分数摘要。

### 3.7 `MemoryManager`
- 维护最近 `chat_history_limit` 条对话、最多 200 条文档摘要、100 条评审记录。
- `get_document_overview` 返回摘要拼接结果，供 `TestcaseGenerator` 在上下文开头注入。

### 3.8 `Utils`
- `FeishuDocClient`：支持 link/token 自动识别，拉取飞书 RawContent。需要在 `config.yaml` 里配置 `feishu.app_id/app_secret`。
- `ImageAnalyzer`：封装 OpenAI 的多模态接口，支持图片/文档解析与分类；异常场景会打印警告并返回兜底文本。

## 4. 配置映射 (config.yaml)

| 段落 | 作用 | 重要字段 |
| ---- | ---- | -------- |
| `app` | 基础模型与终端行为 | `api_key`、`default_model`、`system_prompt`、`banner`、`history_limit`、`image_*` |
| `processing` | RAG 参数 | `embedding_model`、`text_splitter.chunk_size`、`text_splitter.chunk_overlap` |
| `image_prompts` | 图片分类 + 描述 Prompt | `classifier`、`default`、`types[*].prompt`、`types[*].metadata.version` |
| `testcase_modes` | 生成模式 | `planner_prompt`、`builder_prompt`、`context_limit`、`layout`、`metadata.version` |
| `testcase_layouts` | 用例模板 Schema | `case_fields`（字段、必填）、`plan_sections`（检查清单） |
| `outputs` | 默认输出 | `testcases.default_dir/default_format`、`evaluations.default_dir` |
| `evaluation.review_metrics` | 结构化评审 | `name`、`prompt`、`system_prompt`、`metadata`、`format_hint` |
| `evaluation_metrics` | 自定义补充指标 | 同上，可选 |
| `paths` | 缓存/日志路径 | `latest_testcase_cache`、`script_log` |
| `commands` | 自定义命令 | `description`、`prompt`、`use_rag` |

## 5. 常用数据结构

| 名称 | 定义 | 说明 |
| ---- | ---- | ---- |
| `ContentSegment` | `type/source/content/metadata` | 文本、文档、图片统一表示；metadata 记录格式/分类/来源 |
| `TestcaseModeConfig` | 模式配置对象 | 从 `testcase_modes` 解析而来，用于驱动 Planner/Builder |
| `TestcaseLayout` | 模板 Schema | 字段顺序、必填、描述；附带计划清单 |
| `TestcaseDocument` | 生成结果 | 包含 `modules`、`planner_notes`、`plan_summary`、`metadata`，支持 Markdown/JSON 序列化 |
| `EvaluationResult` | 评审结果 | `score`（扣分后）、`summary`、`suggestions`（标准化列表）、`penalty_summary` |
| `EvaluationRecord` | 历史记录 | 存储在 `MemoryManager` 中的压缩评审摘要 |

## 6. 扩展指南

1. **新增命令**：在 `config.yaml` 的 `commands` 段新增条目（示例：`polish_prd`），即可在终端直接 `/polish_prd ...` 使用；模板中可引用 `{history}`、`{args}`。
2. **新增生成模式**：在 `testcase_modes` 新增 `smoke_v2`，声明 `planner_prompt` 和 `builder_prompt`，并指向 `testcase_layouts` 中的新模板；终端即可 `/generate_cases mode=smoke_v2`。
3. **新增模板字段**：在 `testcase_layouts.detailed.case_fields` 中增添字段（如 `risk`），LLM 会按照 `layout_schema` 说明填充；同时更新 `plan_sections` 以覆盖新的质量关注点。
4. **替换评审器**：在 `evaluation.review_metrics` 中将 `prompt` 指向自研评分器的接口；若需完全跳过 LLM，可自定义 `EvaluationEngine.evaluate`（保留 `EvaluationResult` 接口稳定即可）。
5. **拓展输入类型**：在 `ContentProcessor` 新增对 `.csv`/`.pptx` 等的解析，返回 `ContentSegment`；配合 `ImageAnalyzer` 或自定义解析器即可扩充摄取范围。
6. **脚本流水线**：在 `scrpits/*.tcl` 编写命令序列（支持注释），或在 `pipeline/run_all_scripts.sh` 中自定义执行顺序，便于 nightly 任务自动生成与评审。

## 7. 调试与排查建议

- **向量检索无结果**：确认在摄取后调用了 `/read` 并看到 `Indexed n document(s)`；当前实现每次覆盖向量库，如需累积请改 `_ingest_segments`。可通过 `/history` 检查 RAG 是否生效。
- **图片/文档分析为空**：检查 `config.app.image_api_key`、`image_model` 是否配置；若为空，`ContentProcessor` 会输出 warning 并返回空内容。
- **生成 JSON 解析失败**：`TestcaseGenerator` 会将原始文本写入 `fallback_content`，终端也会提示；可从 `output/testcases/...json` 中查看原始响应。
- **评审分数异常**：`EvaluationEngine` 解析模型输出失败时会 fallback 到 `score=None`，并保留原始 JSON 在 `rationale` 字段；检查模型是否按指定格式返回。
- **最新用例缓存**：`output/latest_testcase.json` 保存最近一次生成的路径，`/evaluate_cases` 在未指定候选文件时自动引用。

## 8. 后续演进建议

1. **增量向量库**：当前每次 `_ingest_segments` 只索引新批次，后续可改为“追加”，或引入基于文档 ID 的更新策略。
2. **多模态评审**：在评审阶段结合结构化校验（字段完整度、关键字覆盖率）与 LLM 评分，避免完全依赖模型判断。
3. **UI 增强**：与前端对接时可利用 `config.commands` 快速补充“润色 PRD”“质量自查”等命令，实现一线测试同学无感切换。
4. **任务分层**：将 `run_testcase_generation` / `run_evaluation` 抽象为独立服务或模块，便于单元测试与 CI 自动化。
5. **观察指标**：将 `MemoryManager` 中的聊天/评审记录暴露给可视化面板，配合 `output/evaluations/evaluation_scores.tsv` 进行趋势分析。

---

如需进一步了解生成流程，可结合 `docs/DESIGN_PRD_TEST.md`（Prompt 策略）与 `docs/EVALUATION_PLAN.md`（评分项）阅读；脚本运行细节请参考 `docs/RUN_SCRIPT_PLAN.md`。
