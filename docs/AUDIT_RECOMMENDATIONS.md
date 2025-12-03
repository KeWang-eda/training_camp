# 项目审阅建议汇总

> 基于 2025-12-03 的代码快照，对 `training_camp` 逐模块的实现状态与改进优先级进行复盘。当前版本已完成核心改造（配置化模型、脚本执行、测试生成/评测闭环、元信息写入等），以下建议聚焦进一步的工程化与可维护性提升。

---

## 已交付亮点（复核通过）
- **配置抽离完整**：`config.yaml` 已包含 `processing.embedding_model`、`text_splitter`、图片分类、多模式用例模板与评审指标，CLI 入口也支持 `--config` 与环境变量覆盖。
- **生成/评测留痕**：`TerminalChatbotCore` 在写入用例与评测报告时统一追加 `generated_at` 与 `config_hash`，并维护 `output/latest_testcase.json` 便于后续引用。
- **命令行体验**：`CommandHandler` 支持脚本模式、Planner 思考/计划面板开关，`cli.py` 的 `-f/--log-file` 结合 Rich 输出满足批量执行场景。
- **结构化评审**：`EvaluationEngine` 结合 `review_metrics` 做 JSON 解析、风险归一化与扣分统计，评审记录写入 `MemoryManager` 便于追溯。

---

## 关键改进事项

| 优先级 | 模块 | 现状评估 | 建议 |
| --- | --- | --- | --- |
| P0 | 配置安全 | `config.yaml` 仍保留 Feishu 明文凭据 | 改为环境变量或本地 `.env`，并在 README/USAGE 提示优先级顺序；添加示例脚本验证配置缺失时的提示文案 |
| P0 | 输出写入 | `_write_output` 直接写文件，异常会产生半写文件 | 引入临时文件 + `Path.replace` 的原子写，统一封装到 `utils/io.py` 复用生成/评测/日志写入 |
| P1 | 终端渲染 | `TerminalStreamHandler` 手动维护代码块状态 | 改用 `rich.syntax.Syntax` / `rich.markdown.Markdown`，减少状态机逻辑，修复多段代码块合并问题 |
| P1 | RAG 记忆 | `conversation_history` 与 `MemoryManager.chat_history` 重复存储 | 统一依赖 `MemoryManager`，`_build_rag_history` 改用 `get_recent_messages()`，并考虑暴露历史摘要给外部命令 |
| P1 | 文档摄取 | 每次 `_ingest_segments` 重建向量库，仅保留最新批次 | 追加模式：保留历史 segments 并更新向量库，或提供 `/reset_docs` 命令显式清理，避免意外覆盖 |
| P2 | Feishu 集成 | `FeishuDocClient` 无重试/超时控制，错误提示偏底层 | 引入 `httpx + tenacity`，补充用户可读错误信息；URL 解析改用 `urllib.parse` 兼容多种链接 |
| P2 | 图片处理 | `ImageAnalyzer` 未做大图压缩 | 接入 Pillow 做尺寸压缩，并区分失败时的错误码/提示，降低多模态调用成本 |

---

## 模块级细化建议

### src/chatbot
- `chatbot_core.py`：若后续接入多模型，可抽象成 `LLMProvider` 接口；当前默认 `FastEmbedEmbeddings` 已切换中文模型，可保留。
- `terminal_chatbot_core.py`：评审参数与生成模式解析可迁移至 `dataclasses`，并补充日志上下文（mode、输出路径、提示词版本）。
- `testcase_generator.py`：JSON 解析失败时仅回落到 `fallback_content`，建议使用 `logger.warning` 附带模块名与截断内容，便于排查模型输出问题。
- `evaluation_engine.py`：`_infer_level` 多次调用模型，后续可缓存重复文本的推断结果，或允许配置静态映射以减少额外请求。

### src/terminal
- `command_handler.py`：当前 `/read` 逐文件处理，后续可支持 `glob` 与递归；参数解析可引入 `shlex.split` 避免路径含空格的解析问题。
- `stream_handler.py`：建议抽象成“Markdown 渲染 + 语法高亮”组合，提升可维护性并支持复制代码块。

### src/utils
- `feishu_client.py`：补充响应日志（`log_id` 等）到 status callback，便于排查；考虑使用新的 SDK 异常类型替代泛型 `RuntimeError`。
- `image_analyzer.py`：引入最大图片尺寸配置与压缩策略（压缩后保留原尺寸信息写入 metadata）。

### 文档与输出
- `docs`：`MODULE_OVERVIEW.md`、`DESIGN_PRD_TEST.md` 已更新为现状，后续若新增 Prompt 模板，建议拆分出 `docs/PROMPT_REFERENCE.md` 并在 README 只保留链接。
- `output`：在 `output/evaluations` 追加 `evaluation_scores.tsv`（按时间列出 key 指标）可帮助课程复盘；JSON Schema 校验可选用 `jsonschema` 轻量实现。

---

## 后续行动清单
1. **安全与配置**：整理凭据读取流程，补充文档说明与示例脚本。
2. **输出可靠性**：抽象统一 IO 工具，加入原子写与错误日志。
3. **RAG 与交互体验**：优化历史管理与终端渲染，确保长会话稳定；提供 `/docs status` 之类的可观测命令（可选）。
4. **外部依赖稳健性**：为 Feishu/多模态调用引入重试与降级策略，完善用户提示。

---

项目当前交付质量良好，建议按照上表优先级推进，以“安全配置 → 可观测性 → 交互体验 → 外部依赖稳健”顺序迭代。
