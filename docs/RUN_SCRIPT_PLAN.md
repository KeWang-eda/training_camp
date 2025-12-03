# CLI 批量执行与自动评估方案

> 目的：减少手动输入 `/generate_cases`、`/evaluate_cases` 等命令的成本；当没有 baseline 但想快速看评估结果时，自动选取最近一次生成的用例作为评测目标。

---

## 1. 自动评估最近一次生成结果

### 现状
`/evaluate_cases <baseline> <candidate>` 需要同时指定两个文件。实际使用时，如果只是想评估刚刚产出的 `/generate_cases` 结果，就必须手动复制路径两遍，比较繁琐。

### 改进思路
1. **缓存最新文件路径（配置化）**  
   - 新增 `config.paths.latest_testcase_cache`（默认 `./output/latest_testcase.json`）。`TerminalChatbotCore.run_testcase_generation()` 在成功写入文件后更新内存变量，并把路径写入该文件，CLI 重启后读取即可继续引用。
2. **命令默认值**  
   - `/evaluate_cases` 若只提供一个参数（或 `candidate` 缺失），默认使用最近的生成文件。  
   - `baseline` 缺失时使用需求摘要／占位文本，并在输出中注明“使用占位 baseline”。
3. **自动决定输出路径**  
   - `config.outputs.testcases` 与 `config.outputs.evaluations` 以 `./output` 为根目录（如 `./output/testcases`、`./output/evaluations`）。命令未指定 `output` 时，就按这些配置生成文件，而非硬编码 `data/outputs/...`。

### 用户体验
```bash
/generate_cases mode=default
/evaluate_cases baseline.md          # candidate 自动指向 latest testcase
/evaluate_cases                      # baseline & candidate 均默认（baseline=占位文本）
```
如需明确指定文件，仍可跟以前一样传两个路径。

---

## 2. 脚本批量执行（`-f run.tcl|run.txt`）

### 需求理解
- 用户希望通过 `python cli.py --config config.yaml -f run.tcl` 直接批量执行命令，每行一个命令（如 `/read ...`、普通聊天或 `/generate_cases`）。
- 文件后缀可为 `.tcl` 或 `.txt`，满足其一即可。

### 方案设计
1. **CLI 参数**  
   - `cli.py` 新增 `--file/-f` 选项，若传入则按脚本模式运行，无需交互式 REPL。
   - 新增 `--log-file` 或在 `config.paths.script_log` 中定义默认日志（默认 `./output/logs/shell.log`），脚本模式输出除终端外，还会流入日志。
2. **脚本解析规则**  
   - 每行一个命令，支持空行 / `#` 开头注释。  
   - 行内容与 REPL 完全一致（例如 `/generate_cases default`, `你好`）。  
   - 遇到 `/exit` 或文件末尾自动退出。
3. **执行顺序**  
   - 可复用现有 `CommandHandler` 和 `handle_chat_message()`，保持一致的输出格式。  
   - 如需等待命令完成（例如 `/generate_cases`），仍旧按当前逻辑同步执行即可。
4. **错误处理与日志**  
   - 某一行失败后立即停止脚本（退出码非 0），但在日志中完整记录报错信息，便于排查；不再继续执行后续命令。
   - 每行命令的执行结果会带时间戳写入日志文件（默认 `config.paths.script_log`；若传 `--log-file` 则覆盖），包含命令文本、Rich 输出摘要与错误栈。

### 文件格式建议
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

CLI 会顺序执行每一行，并在终端输出相同的 Rich 渲染效果；执行完毕后自动退出，并将执行轨迹写入日志文件（默认 `config.paths.script_log`）。

---

## 3. 后续扩展
- **变量注入**：未来可支持在脚本中设置变量（例如 `SET BASE=...`），以便换用不同的 baseline。
- **脚本产出**：可在脚本模式结束时打印“生成文件列表”，方便用户快速定位输出。
- **安全控制**：若需要在脚本中调用危险命令，可增加 `--allow-shell` 或配置白名单。

---

如认可以上方案，下一步即可在 CLI/TerminalChatbotCore 中实现“自动评估最近结果 + 脚本执行模式”的具体代码。*** End Patch
