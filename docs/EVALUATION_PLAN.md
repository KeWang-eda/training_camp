# 测试用例评估方案（Evaluation Plan）

> 目标：`/evaluate_cases` 在缺少人工复核时仍能基于统一指标输出 0~100 的评分，并把扣分原因（缺失场景、风险项）结构化写入 JSON，便于追踪与回归。

---

## 1. 评估流程概览

```
/evaluate_cases [baseline] [candidate]
        │                     │
        │                     └─ 若未显式传入，自动读取 latest_testcase_cache 指向的最新 /generate_cases 结果
        │
        └─ 可选：人工基线 / PRD 摘要；缺失时使用占位提示文本

TerminalChatbotCore.run_evaluation()
        ↓
EvaluationEngine.evaluate()
        ↓（按 metrics 顺序执行）
LLM 返回结构化 JSON → EvaluationEngine 归一化风险 & 扣分 → 写入 output/evaluations/<timestamp>_report.json → 终端展示摘要
```

- **输入**：
  - `需求/基线 (baseline)`：可以是 PRD、人工用例或提纲；作用是让 LLM 了解“应该覆盖什么”。
  - `生成用例 (candidate)`：`/generate_cases` 产物，默认已包含 JSON/Markdown 的模块划分、字段、计划摘要。
  - `参考模板 (optional)`：未来如需和某个“金标准”比对，可放在 `baseline`，当前实现已满足“至少需求 + 生成用例”的要求。
- **输出**：单个 JSON 文件，包含 `metadata` 与 `results` 列表；每个指标对象含 `name / score / summary / suggestions / penalty_summary / metadata`。
- **默认目录**：由 `config.outputs.evaluations.default_dir` 控制（当前 `./output/evaluations`）。
- **得分范围**：强制要求返回 0~100 的整数/浮点数；若模型未能解析，结果为 `null` 并在终端告警。

---

## 2. 指标与衡量方式

| 指标 | 关注点 | 期望返回字段 | 分数计算 |
| --- | --- | --- | --- |
| `alignment` | 测试方案是否体现需求背景、策略思路与跨角色对齐 | `score`、`summary`、`suggestions[]` 或 `risks[]` | 对 `suggestions` 中每个条目尝试读取 `deduction`；若缺失则根据 `level`（或推断的 P0-P9）计算 `10 - level`；全部扣分求和后 `score = max(0, 100 - total_deduction)` |
| `coverage` | 主流程/异常/兼容/性能/安全覆盖是否充分 | 同上 | 与 `alignment` 相同，重点关注覆盖盲区描述，建议在 `suggestions` 加入 `category` 标记维度 |
| `bug_prevention` | 异常处理、预案、监控、回滚能力 | 同上 | 仍按扣分模型计算；若模型未返回结构化条目将自动推断优先级 |

> LLM 若仅返回 `risks` 数组，`EvaluationEngine` 会将其转换为 `suggestions` 并调用 `_infer_level` 逐条推断优先级。

---

## 3. JSON 结构定义

```json
{
  "metadata": {
    "generated_at": "2025-12-03T05:49:57Z",
    "config_hash": "abc123"
  },
  "results": [
    {
      "name": "alignment",
      "score": 72.0,
      "summary": "测试重点覆盖主流程，但缺少异常预案说明。",
      "suggestions": [
        {
          "id": "S1",
          "text": "缺少优惠券过期场景的回归测试。",
          "priority": "P3",
          "level": 3,
          "deduction": 7,
          "category": "coverage",
          "hint": "模型返回或自动推断"
        }
      ],
      "penalty_summary": {
        "count": 1,
        "total_deduction": 28
      },
      "metadata": {
        "prompt": "evaluation.review_metrics[0]"
      }
    }
  ]
}
```

- `metadata.generated_at`：UTC ISO8601 时间。
- `metadata.config_hash`：`config.yaml` 内容的 MD5，方便追溯配置版本。
- `results[].summary`：保留模型原文，未做额外加工；若模型未返回内容则回退到原始响应。
- `results[].suggestions`：列表元素为字典，至少包含 `text`；`deduction`/`level`/`priority` 可缺省，由引擎自动补全。
- `results[].penalty_summary`：记录扣分条目数量与总扣分，用于快速统计。

---

## 4. 扣分与客观性保障

1. **JSON 严格模式**：`review_metrics` Prompt 都以“仅输出 JSON”收尾，`EvaluationEngine` 首先尝试 `json.loads()`，失败时才退化为纯文本。
2. **风险归一化**：
  - 优先读取 `suggestions[*].deduction`，缺失时根据 `level` 或 `priority`（如 `P3`）计算，若仍不可用则通过 `_infer_level` 调用同一 LLM 推断（结果缓存计划中）。
  - 总扣分 = 所有条目 `deduction` 之和，最终得分 `max(0, 100 - total_deduction)`；若模型完全未返回条目，则直接保留模型提供的 `score`。
3. **元数据记录**：`penalty_summary.count/total_deduction` 与 `metadata.prompt`（索引配置）会写入报告，方便定位模板。
4. **输入可追溯**：`baseline_path`/`candidate_path` 与处理结果通过 `status_callback` 输出到终端；脚本模式下同样写入日志。
5. **兼容旧逻辑**：`_apply_risk_penalty` 仍保留以兼容旧 prompt，但在当前实现中已被结构化扣分逻辑取代。

---

## 5. 与生成流程的衔接

- `/generate_cases` 默认输出 JSON，目录可在 `outputs.testcases.default_dir` 改为任意路径。生成成功后会将路径写入 `paths.latest_testcase_cache`（默认 `./output/latest_testcase.json`）。
- `/evaluate_cases` 可只输入一个参数甚至不输入：
  - `python cli.py --config config.yaml` → `/evaluate_cases`：baseline=占位文本，candidate=latest 生成的 JSON。
  - `/evaluate_cases baseline.md`：baseline=baseline.md，candidate=latest。
  - `/evaluate_cases baseline.md candidate.json output=/tmp/report.json`：完全自定义。
- 评估完成后，终端会输出：
  - `Evaluation report saved to ...` 成功提示；
  - 若解析成功，追加 `alignment: xx  coverage: xx  bug_prevention: xx  total: yy` 摘要，方便快速查看分数。
- 报告中的 `results` 顺序与 `review_metrics` 定义一致，便于配置比对。

---

## 6. 后续扩展

1. **建议缓存**：为 `_infer_level` 增加最近请求缓存，避免重复调用同一文本。
2. **硬指标并行**：继续完善 `_calculate_case_health()`（字段缺失率、步骤平均长度）并在报告中附加，形成“规则 + LLM”双重评分。
3. **多候选对比**：扩展 `/evaluate_cases` 支持多个候选文件，输出对比表格便于 prompt 调优。
4. **可视化报告**：在 `output/evaluations` 追加 Markdown/HTML 渲染，结合 `suggestions` 生成待办清单。

当前实现已满足 Coursework 需求：输入需求与用例即可得到可追溯的 0~100 分数与结构化改进建议。后续优化将聚焦稳定性、效率与可观测性。
