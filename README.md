# ByteDance Training Camp

终端形态的 LangChain 助手已经迁移至 `ByteDance/training_camp` 仓库。当前项目在保留原有功能的同时，统一了根目录结构，便于与其他训练营模块协同开发。所有行为依旧由根目录的 `config.yaml` 驱动，可在不改代码的情况下调整模型、Prompt、命令、测试模板与评估指标。

## ✨ 特性
- **终端优先体验**：`prompt_toolkit` + Rich 实现命令历史、流式输出与代码块渲染。
- **统一摄取**：`ContentProcessor` 会把文本、文档、图片和飞书 Wiki 归一为 `ContentSegment`，图片会自动分类（流程图/架构图/UI 等）后套用不同 Prompt。
- **PRD→测试用例闭环**：`TestcaseGenerator` 返回 `TestcaseDocument` 对象，默认序列化为 JSON 并写入 `outputs.testcases.default_dir`；通过 `format=markdown` 可切换 Markdown。
- **离线评测**：`/evaluate_cases` 自动读取 `evaluation.review_metrics` 中的 Prompt，逐项生成 0-100 分的 JSON，并根据“缺失测试点”列表动态扣分（默认每条 -5，封顶 -40），无需人工复核即可得出总体结论。
- **脚本批处理**：`python cli.py --config config.yaml -f run.txt` 可顺序执行 `.tcl/.txt` 中的命令，终端与 `./output/logs/shell.log` 日志同步写入，方便 nightly 任务或多源评测。
- **可选“思考过程 & 测试方案”**：`/generate_cases thoughts=true` 时展示 Planner 模块列表，`plan=true` 可额外展示“测试方案摘要” checklist（功能/兼容/性能/安全）。
- **Config 驱动**：API Key、系统 Prompt、图片分类 Prompt、测试模板、评测指标、自定义命令等都集中在 `config.yaml`。

## 🛠️ 推荐开发环境
- **操作系统**：Linux x86_64（在 `training_camp` Conda 环境验证）。
- **Python**：3.12（`requirements.txt` 已 pin `numpy<2` 以兼容 `faiss-cpu==1.8.0`）。
- **依赖管理**：Conda + pip。
- **必要依赖**：`langchain>=0.3.13`、`langchain-openai`、`fastembed`、`prompt_toolkit`、`rich`、`lark-oapi`、`openai`、`faiss-cpu`。

```bash
conda create -n training_camp python=3.12 -y
conda activate training_camp
pip install -r requirements.txt
```

> 如安装 `lark-oapi` 报版本不匹配，请改用 `pip install lark-oapi==1.4.24`（与当前 SDK 兼容 Python 3.12+）。

## 🚀 快速开始
```bash
# 运行 CLI，默认读取 config.yaml
python cli.py --config config.yaml
```

1. 在 `config.yaml` 的 `app` 段填入文本模型与图片模型的 API Key（或通过环境变量 `KIMI_API_KEY` / `KIMI_IMAGE_API_KEY`）。
2. 若需要读取飞书链接，填写 `feishu.app_id` 与 `feishu.app_secret`。
3. 在终端执行 `/read 文件路径...`、`/read_link <feishu_url>` 把资料载入，再使用 `/generate_cases`、`/evaluate_cases`。

## 📦 目录概览
```
training_camp/
├── cli.py                        # REPL 入口，加载配置并初始化核心
├── config.yaml                   # 所有模型、Prompt、命令、第三方配置
├── docs/                         # DESIGN_PRD_TEST / MODULE_OVERVIEW 等文档
├── output/                       # 默认生成的用例与评测结果
├── pipeline/                     # 训练营课程示例 / 数据管道
├── scrpits/                      # `.tcl` / `.txt` 批处理脚本
├── src/
│   ├── chatbot/                  # chatbot_core、testcase_generator、evaluation_engine
│   ├── terminal/                 # command_handler、stream_handler
│   └── utils/                    # feishu_client、image_analyzer 等
└── langchain-chatbot/            # 老版本代码备份（只读）
```

## 🧮 核心命令
| 命令 | 说明 | 主要参数 |
| --- | --- | --- |
| `/help` | 查看命令列表 | – |
| `/read <path...>` | 读取文件并向量化 | 文件路径列表 |
| `/read_link <feishu_url_or_id>` | 拉取飞书文档并索引 | URL 或 token |
| `/generate_cases [mode] [output] [show_thoughts] [format] [plan]` 或 `/generate_cases mode=smoke output=/tmp/cases.json format=json thoughts=true plan=true` | 生成用例（默认 JSON，目录来自 `outputs.testcases`） | `mode`: 对应 `config.testcase_modes` 键; `output`: 自定义保存路径; `show_thoughts`: 在终端展示 Planner 思考过程; `format`: `markdown`/`json`; `plan`: 是否展示“测试方案摘要” |
| `/evaluate_cases <baseline> <candidate> [output]` | 对比人工与生成用例；基线缺失时用占位摘要，候选缺失时自动取最近一次 `/generate_cases` 产物；评分按 `review_metrics` + 风险扣分 | `baseline`: 基准 Markdown/JSON；`candidate`: 生成用例；`output`: 评估报告保存路径（默认 JSON） |
| `/history` `/save [file]` | 查看/保存对话历史 | – |
| `python cli.py --config config.yaml -f run.txt [--log-file ./output/logs/run.log]` | 以脚本模式批量执行命令（支持 `.tcl` / `.txt`），终端与日志同步输出 | `run.txt` 中每行 1 条命令，支持注释/空行 |

## ⚙️ 配置提示
- `app`：模型与系统 prompt；`banner` 控制 REPL 欢迎语；`history_limit` 决定保留的聊天轮数。
- `image_prompts`：包含 `classifier` Prompt、默认类型、各具体类型（flow_chart/architecture 等）；可随时新增 `types`。
- `processing.embedding_model` / `processing.text_splitter`：控制 embeddings 模型与文本切分参数（默认 `BAAI/bge-small-en-v1.5`、`chunk_size=1000`、`chunk_overlap=200`）。
- `testcase_modes`：定义不同生成模式的 `planner_prompt` / `builder_prompt` / `context_limit`，并通过 `layout` 字段关联到 `testcase_layouts`。
- `testcase_layouts`：声明多套“测试用例模板”，包含字段顺序、必填要求与“测试方案摘要” checklist，LLM 在生成时会读取 Schema（通过 `{layout_schema}` 注入）。
- `outputs.testcases`：设置 `/generate_cases` 的默认格式与输出目录（默认 JSON + `./output/testcases`），CLI 未显式指定路径时按此落盘。
- `outputs.evaluations`：设置 `/evaluate_cases` 的默认输出目录（默认 `./output/evaluations`）。
- `evaluation.review_metrics`：定义 LangChain 评审指标（alignment / coverage / bug_prevention 等），`/evaluate_cases` 输出 JSON，包含 0~100 分、摘要及风险列表；默认每条风险扣 5 分，可在 Prompt 中提示模型按严重度标注；`evaluation_metrics` 可作为补充 prompt。
- `paths.latest_testcase_cache`：缓存最近一次生成的用例路径，便于 `/evaluate_cases` 默认引用。
- `paths.script_log`：脚本模式（`-f run.txt`）的日志输出路径，默认 `./output/logs/shell.log`。
- `commands`：自定义 `/summarize`、`/suggest` 等快捷命令，内部模板支持 `{history}` 与 `{args}`。
- **配置优先级**：CLI 读取顺序为 `config.yaml` → 环境变量（如 `KIMI_API_KEY`）→ 内置默认值，可在 `.env` 中统一管理敏感信息。

## 📚 更多文档
- [docs/MODULE_OVERVIEW.md](docs/MODULE_OVERVIEW.md)：逐文件说明、函数职责、后续扩展点。
- [docs/DESIGN_PRD_TEST.md](docs/DESIGN_PRD_TEST.md)：PRD→测试用例方案、图片多 Prompt 策略、评测流程。
- [docs/OPTIMIZATION_IDEAS.md](docs/OPTIMIZATION_IDEAS.md)：参考 `python_langchain_cn` 教程整理的后续演进建议。

## ✅ 开发者须知
- 代码遵循 Google Python 命名风格，新增函数请保持 snake_case。
- 默认使用 `training_camp` Conda 环境进行测试；如需运行自动化脚本，请在同一环境激活后执行。
- 评测接口 `EvaluationEngine` 遵循“结构化 JSON + 风险扣分”规则：若 LLM 返回 `risks` 列表，则根据条数扣分（默认每条 5 分、封顶 40 分），可在 `evaluation.review_metrics` 中自定义 Prompt 与格式；如需额外统计指标，可在 `evaluation_metrics` 增补。
