# 模块拆分与设计指南

> 本文解释终端版 LangChain 助手的模块结构、数据流和代码扩展点，便于在 Coursework 场景下继续演进。

## 1. 总览

```
training_camp/
├── cli.py                       # CLI 入口，加载 config 并注入 TerminalChatbotCore
├── config.yaml                  # 模型、prompt、Feishu、图片类型、评测指标、测试模板等配置
├── src/                         # chatbot / terminal / utils 模块
├── docs/                        # 设计文档（DESIGN_PRD_TEST.md、MODULE_OVERVIEW.md 等）
├── output/                      # 生成的用例与评测报告
├── pipeline/、scrpits/          # 课程示例与批处理脚本
└── langchain-chatbot/           # 老版本代码备份
```

### 数据流
1. `cli.py` 读取 `config.yaml`，构造 `TerminalChatbotCore` 与 `CommandHandler`。
2. `/read` `/read_link` 等指令触发 `TerminalChatbotCore.ingest_*`，由 `ContentProcessor`/`FeishuDocClient` 产生 `ContentSegment`，并写入向量库 + `loaded_segments`。
3. `/generate_cases`：`run_testcase_generation(thoughts=…, plan=…, output_format=…)` 把 `loaded_segments` 合并成上下文，套 `testcase_modes` prompt，基于 `testcase_layouts` 生成结构化 JSON，再渲染为 Markdown/JSON；默认格式与路径来自 `outputs.testcases`；`thoughts=true` 展示 Planner 模块列表，`plan=true` 展示“测试方案摘要” checklist。
4. `/evaluate_cases`：`run_evaluation()` 读取人工/生成用例，自动 fallback 缺失文件，然后按 `review_metrics` 调用 LLM（依据建议条目动态扣分）并生成 JSON 报告。

## 2. 目录与文件详解

### 2.1 cli.py
- **职责**：解析 CLI 参数、读取配置、构建核心对象、管理 REPL。
- **主要函数**
  - `parse_args()`：仅接收 `--config`，避免命令行/配置冲突。
  - `load_config()` / `resolve_setting()`：支持 config → env → fallback 顺序。
  - `handle_chat_message()`：统一调用 `TerminalChatbotCore.ask()` 并使用 `TerminalStreamHandler` 输出。
- **扩展建议**：如需多 Agent，可在 config 中定义 `agents` 并在 CLI 环节切换不同的 system prompt。

### 2.2 src/chatbot/chatbot_core.py
- **职责**：封装 LangChain 的 LLM / 向量化逻辑。
- **关键函数**
  - `initialize_models()`：实例化 `ChatOpenAI` 与 FastEmbed；懒加载 `get_llm()`。
  - `create_conversation_chain(vector_store, system_prompt)`：无向量时返回 `_BasicConversationChain`（内置系统 Prompt + 历史记忆），否则返回 `ConversationalRetrievalChain`。
  - `_BasicConversationChain`：轻量替代原 `ConversationChain`，在 `messages` 中注入 `SystemMessage`。
- **扩展点**：若后续接入 LangGraph，可在此处替换基础链构造。

### 2.3 src/chatbot/content_processor.py
- **数据结构**：`ContentSegment(type, source, content, metadata)`；便于记录来源/格式/图片类型。
- **函数**
  - `process_local_files()` / `process_files()`：统一转为 `ContentSegment` 列表。
  - `_build_segment()`：依据扩展名分发到 `_extract_text_content` / `_extract_document_content` / `_extract_image_content`。
  - `_extract_image_content()`：读取 `config.image_prompts`，先调用 `ImageAnalyzer.classify_image()` 判断类型，再用对应 prompt 生成结构化描述，同时返回 metadata（`image_type`, `image_label`）。
- **命名约定**：后续新增格式（视频、音频等）时，同样返回 `ContentSegment`，在 metadata 中存储额外信息。

### 2.4 src/chatbot/terminal_chatbot_core.py
- **定位**：应用层 Orchestrator，负责 RAG 状态、文档摄取、用例生成与评测。
- **重要属性**
  - `loaded_segments`: List[ContentSegment]，用于生成上下文。
  - `testcase_modes` / `evaluation_metrics`: 来自 config.yaml。
- **核心方法**
  - `ingest_local_files()`：调用 `ContentProcessor`，再 `_ingest_segments()` 写入向量库并缓存。
  - `ingest_feishu_document()`：通过 `FeishuDocClient` 拉取 RawContent，封装为 `ContentSegment`。
  - `run_testcase_generation(mode, output, output_format, show_thoughts, show_plan_summary)`：构建上下文 → 套 prompt → 根据 `testcase_layouts` 渲染 Markdown/JSON，并附带 `generated_at`/`config_hash` 元信息；按需返回“思考过程”和“测试方案摘要”。
  - `_render_testcase_document()`：根据 `TestcaseDocument` + layout schema 渲染 Markdown/JSON；JSON 额外包含 `metadata`（时间戳与配置哈希）。
  - `run_evaluation(baseline, candidate, output)`：自动加载基线与候选文件（缺失时使用占位/最近生成的用例），按 `review_metrics` 调用 LLM，依据“建议数量 × 扣分”规则生成 JSON 报告（含 `metadata` 字段）。
  - `_write_output(subdir, desired_path, content, suffix)`：标准化结果落盘路径，默认遵循 `outputs.*` 配置（`./output/testcases`、`./output/evaluations` 等）。
- **后续计划**：可以将 `run_testcase_generation`、`run_evaluation` 拆分到独立类（如 `TestcaseGenerator`、`EvaluationEngine`），当前设计保留接口，方便重构。

### 2.5 src/chatbot/testcase_generator.py
- **Schema 驱动**：根据 `testcase_layouts` 载入 `TestcaseLayout`（字段顺序、必填项、plan checklist），生成时把 schema 描述 (`{layout_schema}`) 注入 builder prompt，要求 LLM 以 JSON 返回。
- **主要数据结构**：
  - `TestcaseCase`：以 `field_values` 字典保存所有 schema 字段，可额外附带 `raw_text`。
  - `TestcaseModule`：记录 `layout`、`module_goal`，若 JSON 解析失败则落入 `fallback_content`。
  - `TestcaseDocument`：集合模块、`planner_notes` 与 `plan_summary`（直接来自模板 checklist），并提供 `to_markdown(layouts)` / `to_json()` / `to_dict()`。
- **流程**：`generate()` → `_plan_modules()`（列模块）→ `_build_cases()`（注入 schema）→ `_parse_module_output()`（JSON→对象或 fallback）→ `_build_plan_summary()`（模板 checklist + 模块名注入）。

### 2.6 src/terminal/command_handler.py
- **职责**：解析终端命令并调用核心。
- **内置命令**：`/read`、`/read_link`、`/generate_cases`、`/evaluate_cases`、`/history`、`/save` 等，呈现在 `/help` 表格中。`/generate_cases` 默认使用 `config.outputs.testcases` 中的格式/目录，但仍支持顺序或 `mode=... output=... format=... thoughts=... plan=...` 键值写法覆盖。
- **新增选项**：`format`（`markdown`/`json`）、`thoughts`（Planner 输出）、`plan`（“测试方案摘要” Panel）统一通过 `_parse_generate_args()` 解析并传给核心。
- **扩展命令**：`config.commands` 里定义（如 `/summarize`），在 `execute_custom_command()` 中构造 prompt。
- **UI 细节**：新增日志文案 `Analyzing {label} «filename» with AI...`，展示图片类型。

### 2.7 src/terminal/stream_handler.py
- **功能**：在终端流式输出 tokens，自动识别代码块，高亮展示。
- **方法**：`on_llm_new_token`、`_toggle_code_block`；可根据需要扩展 Markdown 渲染。

### 2.8 src/utils/image_analyzer.py
- **接口**
  - `analyze_image(image_file, type, prompt=None)`：OpenAI Chat Completions，多模态描述。
  - `classify_image(image_file, type, prompt, candidate_keys)`：用于类型判定，返回 `candidate_keys` 中最匹配的 key。
- **注意**：需要写入 config 中的 `image_prompts.classifier/default/types` 以自定义分类与描述。

### 2.9 src/utils/feishu_client.py
- **功能**：拉取飞书 Docx/Wiki RawContent。
- **方法**
  - `extract_document_id(link_or_id)`：从 URL 截取 token。
  - `fetch_raw_content(doc_id)`：调 `docx.v1.document.raw_content`；失败时抛异常供上层捕获。
- **Warning 处理**：内部使用 `warnings.filterwarnings` 忽略 `pkg_resources` 弃用提示。

## 3. 配置要点
- `app.system_prompt`：全局 Agent 行为描述。
- `image_prompts`：分类 Prompt + 类型列表（可无限扩展）。
- `testcase_modes`：定义不同生成模式（`default`/`smoke`/自定义），并通过 `layout` 字段引用 `testcase_layouts` 的模板。
- `testcase_layouts`：声明不同模板需要的用例字段、必选项、描述与“测试方案摘要” checklist；生成时会注入模板文本并输出结构化 JSON。
- `outputs.testcases`：默认输出格式与目录（JSON + `./output/testcases`），CLI 未指定路径时按此设置落盘。
- `evaluation.review_metrics`：配置 alignment / coverage / bug_prevention 等 LangChain 指标（输出 JSON）；`evaluation_metrics` 仍可用于追加个性化 prompt。

## 4. TODO / 扩展建议
1. **生成与评测责任拆分**：可将 `run_testcase_generation` / `run_evaluation` 提取为独立类，便于单元测试。
2. **统计式评测**：结合 `_calculate_case_health` 或独立校验器，引入硬指标（字段缺失率、步骤粒度、前置条件完备度等）并与 LLM 分数并行展示。
3. **多 Agent 支持**：在 config 中预定义多个 `agents` 并提供 `/switch_agent` 指令，实现不同场景（开发/测试/产品）提示词切换。

---
如需在文档中引用本文，可在 README 的 “📚 相关文档” 部分添加链接，以方便团队成员快速了解架构设计。
