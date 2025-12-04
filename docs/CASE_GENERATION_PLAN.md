# 测试用例生成方案（Case Generation Plan）

> 目标：`/generate_cases` 产出结构化 JSON，既能直接被人工评审阅读，也能供 `/evaluate_cases`、CI 校验和后续分析复用。本文档在《测试用例评估方案（Evaluation Plan）》的框架上补充“如何生成”的视角，帮助你连接需求输入、规划提示词、模块拆分与输出格式。

---

## 1. 生成流程概览

```
/generate_cases [scenario_brief] [options]
        │
        └─ 若未显式传入，默认读取 config.prompts.case_generation.baseline 中的默认提示词

TerminalChatbotCore.run_case_generation()
        ↓
CasePlanner.plan()          （规划阶段：拆目标、列模块、补充注意事项）
        ↓
CaseAuthor.compose_cases()  （撰写阶段：逐模块生成结构化用例）
        ↓
输出 JSON → 写入 output/testcases/<timestamp>_default.json → paths.latest_testcase_cache
```

- **输入**：
  - `scenario_brief`：需求/PRD 摘要或终端临时描述；缺省时会提示“缺少需求上下文”。
  - `options.mode`：区分生成策略（当前支持 `default`，用于评估基线）。
  - `config.prompts.case_generation.*`：在 `config.yaml` 内定义规划提示、写作提示、输出 schema。
- **输出**：
  - 主体 JSON 文件，包含 `metadata`、`document` 两大块；`document.modules[].cases[]` 为核心内容。
  - 备份 Markdown（可选，取决于 `config.outputs.testcases.emit_markdown`）。
- **默认目录**：`config.outputs.testcases.default_dir`，当前为 `./output/testcases`。

---

## 2. JSON 结构梳理

以 `output/demo/demo_testcase.json` 为例，整体分为三层：

1. **文件级 `metadata`**：记录生成时间、配置指纹与模式。
   - `generated_at`：UTC ISO8601 时间戳，例如 `2025-12-03T15:28:07.627299`。
   - `config_hash`：`config.yaml` 的 MD5；与评估报告中的哈希对齐即可确认同一配置。
   - `mode`：当前执行的策略（如 `default`、`stress`）。
2. **`document` 块**：携带规划信息与模块、用例具体内容。
   - `metadata.version`：规划模板版本，便于兼容增量变更。
   - `planner_notes`：规划阶段的摘录，用来提醒评审“为什么要覆盖这些模块”。
   - `plan_summary`：由 CasePlanner 生成的综述条目，结构为 `[ { title, checklist[] } ]`，可直接作为评审 checklist。
3. **模块与用例**：`document.modules` 数组，每个模块含：
   - `name` / `goal`：模块识别与质量目标；建议遵循“编号 + 简述”命名，便于排序。
   - `layout`：下游渲染布局提示，目前统一为 `detailed`。
   - `fallback_content`：保留字段，尚未启用。
   - `cases`：结构化用例列表；每条包含 `title` 与 `field_values`（详见下表）。

| 字段 | 说明 | 建议写法 |
| --- | --- | --- |
| `preconditions` | 执行前置条件，可为字符串或字符串数组 | 表述环境、账号、数据准备，避免隐式假设 |
| `steps` | 步骤说明 | 建议拆分为数组，以动词开头，保持可执行性 |
| `expected` | 期望结果 | 明确可观测输出、响应时间、状态变化 |
| `risk` | 风险提示 | 描述若回归会触发的业务风险或客户影响 |
| `priority` | 用例优先级 | 使用 `P0`（最高）到 `P3`（最低），与评估指标一致 |
| `raw_text` | LLM 原始输出 | 仅在结构化失败时保留；正常流程下应为 `null` |

> **Tip**：保持字段名称与大小写一致，`/evaluate_cases` 会按同样的 keys 做规则校验（如检查 `priority`、`expected` 是否缺失）。

---

## 3. 提示词配置与角色分工

`config.yaml` 中 `prompts.case_generation` 分为三部分：

1. `planner_prompt`：负责把需求拆解成模块、注意事项。建议包含：
   - 需求背景与约束（例如“高德静态地图、百度 OCR、商城天气联动”）；
   - 要求生成的模块数量（一般 3–5 个核心模块 + 异常策略）；
   - 输出格式示例（说明需要 JSON 或 Markdown）；
   - 评审关注点（覆盖主流程、异常、性能、韧性、安全等）。
2. `case_author_prompt`：针对每个模块生成结构化用例。提示词应强调：
   - 每个用例必须包含 `preconditions/steps/expected/risk/priority`；
   - 保持语言一致（目前整体中文）；
   - 根据 `planner_notes` 的目标设定至少 3~5 条用例，关注高优先级场景。
3. `output_schema`：示例 JSON，指导模型填充正确结构。必要时可加入校验注意（如“steps 使用数组”）。

---

## 4. 质量控制与自检

生成完成后可以用以下清单快速验收：

- **字段完整性**：随手检查 `cases` 是否存在缺失字段；若 LLM 丢字段，会在评估时被扣分。
- **优先级合理性**：核心流程标记为 `P0/P1`，辅助验证用 `P2/P3`；为 `/evaluate_cases` 的风险推断提供依据。
- **规划一致性**：`planner_notes` 中提出的目标是否都在 `modules` 中得到对应；若缺失，可重新触发规划或手动补写。
- **可执行性**：步骤与期望是否可操作、可验证；必要时补充“如何判断成功/失败”的具体指标。
- **风险覆盖**：`risk` 字段应说明回归后影响（例如“会触发白屏”），结合评估建议能更快定位问题。

---

## 5. 与评估流程对齐

- `config_hash`、`mode` 与评估报告保持一致，便于追踪。
- `priority`、`risk` 等字段会被 `/evaluate_cases` 判定是否存在；缺失会导致 `coverage`/`bug_prevention` 得分下降。
- 建议在提交评审前，先运行一次 `/evaluate_cases` 并检查 `suggestions`，根据扣分条目回补用例或者完善规划。
- `paths.latest_testcase_cache` 始终指向最近一次生成结果，若要锁定版本，可将 JSON 拷贝到 `output/demo/` 或仓库内的 `docs/samples/`。

---

## 6. 后续增强建议

1. **模板版本化**：在 `document.metadata.version` 中记录模板变更历史（例如 `v2-202512`），便于识别老旧输出。
2. **模块标签**：为 `modules` 增加 `tags` 字段（如 `core`, `performance`, `resilience`），与评估维度做自动映射。
3. **自动补充示例数据**：对涉及外部接口的用例，可额外生成 `mock_payload`，方便集成测试直接调用。
4. **Markdown 渲染**：如需面向非技术 reviewer，可将 JSON 同步渲染成表格，或输出 `.md` 文件并在 README 中链接。

本方案结合评估指标，确保生成的用例集既结构化又可执行，为后续自动评估与人工复核打下稳定基础。
