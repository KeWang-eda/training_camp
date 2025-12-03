# CLI 批量执行与自动评估说明

> 本文记录 2025-12-03 版本中脚本执行与自动评估的落地方式，并给出使用示例与扩展建议。当前实现已支持“最近用例缓存”“脚本批量运行”“日志追踪”等能力。

---

## 1. 自动评估最近一次生成结果

### 工作机制
1. `config.paths.latest_testcase_cache`（默认 `./output/latest_testcase.json`）用于持久化最近一次 `/generate_cases` 产物路径。`TerminalChatbotCore.run_testcase_generation()` 成功写入文件后会更新该缓存。
2. `/evaluate_cases` 参数解析规则：
   - 如果未提供 `candidate`，则自动使用缓存路径；
   - 若未提供 `baseline`，会注入占位说明并在评审报告中提示；
   - 落盘目录/格式默认取自 `config.outputs.evaluations`，除非用户通过第三个参数显式指定。
3. 终端会在评估完成后打印保存路径，并尝试解析报告输出 `alignment/coverage/bug_prevention/total` 摘要。

### 使用示例
```bash
# 生成默认模式用例（输出路径自动按时间戳命名）
/generate_cases mode=default

# 评审：baseline 传人工文档，candidate 自动引用最新生成结果
/evaluate_cases docs/manual_baseline.md

# 完全依赖默认值（baseline=占位文本，candidate=latest）
/evaluate_cases
```

如需指定全部参数：`/evaluate_cases docs/manual.md output/testcases/20251203_default.json output/reports/custom_report.json`。

---

## 2. 脚本批量执行（`-f run.tcl|run.txt`）

### 核心能力
- `python cli.py --config config.yaml -f demo.tcl` 进入脚本模式；完成脚本后自动退出，不开启交互式 Prompt。
- 支持 `.tcl` / `.txt` 后缀；脚本内每一行都会按照 REPL 相同规则处理，支持空行与 `#` 注释。
- 日志：默认写入 `config.paths.script_log`（`./output/logs/shell.log`），可通过 `--log-file` 覆盖；每条命令附带时间戳、原始文本与结果状态。
- 错误处理：当某一行执行失败时停止脚本并记录堆栈，便于复现；成功执行的命令之间共享同一 `TerminalChatbotCore` 实例和内存。

### 示例脚本
```
# run.txt
/read docs/需求.md
/generate_cases mode=default thoughts=true
/evaluate_cases baseline.md
你好，帮我总结一下上述测试重点
/exit
```

运行方式：
```bash
python cli.py --config config.yaml -f run.txt
# 指定日志输出
python cli.py --config config.yaml -f run.txt --log-file ./output/logs/nightly.log
```

CLI 会顺序执行每一行，并在终端复用 Rich 渲染效果；执行完毕后自动退出，同时把执行轨迹写入日志文件（包括脚本路径、命令、成功/失败、异常信息）。

---

## 3. 后续扩展方向
- **变量注入**：允许脚本中定义变量（`SET BASE=...`）并在后续命令中替换，便于多环境切换。
- **产物索引**：脚本结束后输出本次生成/评审文件列表或追加到日志，方便查看。
- **安全控制**：为潜在危险操作（如本地 Shell 命令）引入白名单或 `--allow-shell` 开关，避免误触。
- **结构化日志**：在文本日志基础上附加 JSON Lines，记录执行时长、config_hash 等信息，便于批量分析。

---

通过以上机制，终端助手能够在夜间批量运行生成+评审流程，并在人工介入前提供最新结果与日志留痕。
