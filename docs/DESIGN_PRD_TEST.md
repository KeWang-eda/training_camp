# LangChain 终端助手 → PRD 测试工作台设计说明

> 文档聚焦 2025-12-03 的实现版本，阐述终端助手如何闭环“需求摄取 → 测试用例生成 → 离线评审”，并给出配置映射、模块职责与迭代方向。

---

## 1. 目标与约束
- **形态**：保持纯终端交互，依赖 `prompt_toolkit` + `rich` 完成 REPL、脚本执行与流式输出。
- **能力闭环**：从 PRD / 图片 / 飞书文档摄取上下文，生成结构化测试用例，并根据统一指标输出评审报告。
- **配置驱动**：全部 Prompt、模板、模型配置集中在 `config.yaml`，支持 CLI 参数与环境变量覆盖。
- **可追溯**：所有产物附带生成时间、配置哈希，最近用例路径缓存到磁盘，支持后续评审引用。

---

## 2. 目录骨架

```
training_camp/
├── cli.py                    # 终端入口 & 脚本执行
├── config.yaml               # 模型、Prompt、评测、输出路径配置
├── src/
│   ├── chatbot/              # 业务核心（RAG、生成、评审、内存）
│   ├── terminal/             # 命令解析、流式渲染
│   └── utils/                # Feishu、多模态工具
├── docs/                     # 架构/评审/优化文档
├── output/                   # 用例与评审结果（运行时生成）
├── pipeline/                 # 课程示例脚本
├── scrpits/                  # `.tcl`/`.txt` 批量命令脚本
└── langchain-chatbot/        # 历史代码备份
```

---

## 3. 核心流程

### 3.1 启动与配置
1. `cli.py` 解析 `--config/-f/--log-file` 参数，加载 YAML 配置并生成 12 位 `config_hash`。
2. 通过 `resolve_setting` 依次读取配置值、环境变量（如 `KIMI_API_KEY`）、兜底默认值，确保密钥可外置。
3. 构造 `TerminalChatbotCore` 与 `CommandHandler`，准备 PromptSession 或脚本执行环境。

### 3.2 文档摄取 / RAG 准备
1. `/read` → `ContentProcessor.process_local_files`：按后缀识别文本、文档、图片，统一产出 `ContentSegment`。
2. 若配置了多模态模型，图片/文档会调用 `ImageAnalyzer` 分类 + 描述，metadata 中记录类型与标签。
3. `_ingest_segments` 使用 FastEmbed + FAISS 重建向量库，刷新 `ConversationalRetrievalChain` 并写入 Memory 摘要。

### 3.3 对话
- 普通消息走 `_BasicConversationChain`，若存在向量库则切换到 RAG 链路；历史记录同时写入 `conversation_history` 与 `MemoryManager`（计划合并为后者）。

### 3.4 测试用例生成
1. `/generate_cases` 支持位置参数或 `mode=... output=... format=... thoughts=true plan=true` 键值写法。
2. `TerminalChatbotCore.run_testcase_generation`：
   - 读取 `testcase_modes[mode]` 获取 Planner/Builder Prompt、上下文长度与布局 key。
   - `TestcaseGenerator.generate`
     - `_build_context` 拼接文档片段与 Memory 摘要。
     - `_plan_modules` 调用 Planner Prompt 产出模块列表。
     - `_build_cases` 注入 `{layout_schema}` 执行 Builder Prompt → 解析 JSON → 生成 `TestcaseDocument`。
   - 按 `output_format` 渲染 Markdown/JSON，头部写入 `generated_at` 与 `config_hash`，文件名为 `YYYYMMDD_HHMMSS_<mode>.{md|json}`。
   - 更新 `output/latest_testcase.json` 缓存路径。可选展示 Planner 思考与“测试方案摘要”。

### 3.5 自动评审
1. `/evaluate_cases [baseline] [candidate] [output]`：参数缺省时，baseline 使用占位提示，candidate 自动引用最近生成的用例。
2. 结合 `evaluation.review_metrics` 构造评审任务：
   - `EvaluationEngine._run_structured_review` 强制模型返回 JSON，兼容 `suggestions`/`risks`，并通过 `_infer_level` 推断优先级（默认 P0-P9 → 扣分 10~1）。
   - 同时执行 `evaluation_metrics` 补充扩展指标（若配置）。
3. 汇总结果写入 `output/evaluations/YYYYMMDD_HHMMSS_report.json`，终端即时输出 alignment/coverage/bug_prevention 评分摘要。
4. 评审记录保存到 `MemoryManager`，便于会话中的后续追问。

### 3.6 脚本执行
- `python cli.py --config config.yaml -f scrpits/nightly.tcl`：逐行执行命令，支持注释、自动终止；执行轨迹追加到 `config.paths.script_log`。

---

## 4. 配置映射

| 区块 | 说明 | 关键字段 |
| --- | --- | --- |
| `app` | 模型与终端行为 | `api_key`、`default_model`、`image_*`、`history_limit`、`banner` |
| `processing` | RAG 参数 | `embedding_model`（默认 `BAAI/bge-small-zh-v1.5`）、`text_splitter.chunk_size/overlap` |
| `image_prompts` | 图片分类与描述 | `classifier`、`default`、`types[*]`（key/label/prompt/metadata） |
| `feishu` | 飞书凭据 | `app_id`、`app_secret`、`base_url` |
| `testcase_modes` | 用例生成模式 | `planner_prompt`、`builder_prompt`、`context_limit`、`layout`、版本元数据 |
| `testcase_layouts` | 模板 Schema | `case_fields`（字段顺序、必填）、`plan_sections`（计划检查项） |
| `evaluation.review_metrics` | 结构化评审 | 每项包含 `name`、`prompt`、`system_prompt`，默认三指标 |
| `evaluation_metrics` | 扩展打分 | 可选项，接口同 `review_metrics`，当前为空列表 |
| `commands` | 自定义聊天命令 | 模板可引用 `{history}`、`{args}` |
| `outputs` | 默认落盘策略 | `testcases.default_dir/default_format`、`evaluations.default_dir` |
| `paths` | 缓存/日志 | `latest_testcase_cache`（最近用例）、`script_log` |

---

## 5. 主要模块职责（简版）

| 模块 | 责任 | 备注 |
| --- | --- | --- |
| `cli.py` | 解析参数、加载配置、驱动 PromptSession/脚本模式、构造核心对象 | `config_hash` 在此计算并透传 |
| `chatbot.chatbot_core` | 管理 LLM、Embedding、FAISS，生成基础 or RAG 会话链 | `_BasicConversationChain` 为轻量兜底 |
| `chatbot.content_processor` | 解析文本/文档/图片 → `ContentSegment` | 依赖 `ImageAnalyzer` 完成分类与描述 |
| `chatbot.terminal_chatbot_core` | Orchestrator：摄取、对话、生成、评审、输出落盘、缓存维护 | `_write_output` 统一命名与目录策略 |
| `chatbot.testcase_generator` | Planner + Builder 双阶段生成，结构化/Markdown 序列化 | 解析失败时保留 `fallback_content` |
| `chatbot.evaluation_engine` | 结构化评审、风险扣分、结果归档 | `_infer_level` 需要多次 LLM 调用（可缓存） |
| `chatbot.memory_manager` | 存储聊天、文档摘要、评审历史 | `get_document_overview` 为上下文前缀 |
| `terminal.command_handler` | 内置命令解析、自定义命令执行、计划面板渲染 | `/generate_cases` 兼容位置/键值混合参数 |
| `terminal.stream_handler` | LLM 流式输出，手动处理代码块高亮 | 后续可替换为 `rich.syntax` |
| `utils.feishu_client` | 飞书 RawContent 拉取，输出 JSON 字符串 | 需补充重试/可读错误提示 |
| `utils.image_analyzer` | OpenAI 多模态封装，支持分类与描述 | 目前未做图像压缩 |

---

## 6. 命令速览

| 命令 | 说明 | 典型用法 |
| --- | --- | --- |
| `/read` | 读取本地文件并建立向量库 | `/read docs/prd.md screenshot.png` |
| `/read_link` | 通过链接/ID 拉取飞书文档 | `/read_link https://feishu.cn/docx/...` |
| `/generate_cases` | 生成测试用例，支持模式/格式/展示选项 | `/generate_cases mode=smoke thoughts=true plan=true` |
| `/evaluate_cases` | 按配置指标评审用例 | `/evaluate_cases manual.md latest.json`；`/evaluate_cases`（全默认） |
| `/history` | 查看最近对话 | `/history` |
| `/save` | 导出对话历史 | `/save conversation.txt` |
| 自定义命令 | 基于 `config.commands` | `/summarize`、`/suggest xxx` |
| 脚本模式 | 批量执行命令文件 | `python cli.py --config config.yaml -f scrpits/demo.tcl` |

---

## 7. 迭代方向
1. **安全与配置**：移除配置文件中的明文凭据，提供 `.env.example` 与自动校验脚本。
2. **输出可靠性**：引入原子写入与异常日志归档，避免半写文件。
3. **RAG 累积与观测性**：支持追加索引、提供 `/docs status` 等观测命令，并整合历史管理。
4. **多模态与外部集成稳健性**：为 Feishu 请求和图片分析添加重试/超时/降级策略，压缩大图减少 token 成本。
5. **体验优化**：终端渲染替换为 Rich 原生 Markdown/语法高亮；Planner/Builder 提供温度、模型切换配置。

---

当前实现已完成 Coursework 所需的“需求摄取 → 用例生成 → 评审”全流程；后续迭代可围绕安全性、稳定性与可观测性持续增强。
