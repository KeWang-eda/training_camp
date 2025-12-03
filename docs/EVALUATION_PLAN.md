# 测试用例评估方案（Evaluation Plan）

> 目标：让 `/evaluate_cases` 在没有人工复核的前提下，依据统一指标客观输出 0~100 的分数，并把扣分原因（缺失的测试点/风险）结构化写入 JSON，方便后续追踪。

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
LLM 生成 JSON（score/summary/risks） → 应用扣分规则 → 写入 output/evaluations/<timestamp>_report.json
```

- **输入**：
  - `需求/基线 (baseline)`：可以是 PRD、人工用例或提纲；作用是让 LLM 了解“应该覆盖什么”。
  - `生成用例 (candidate)`：`/generate_cases` 产物，默认已包含 JSON/Markdown 的模块划分、字段、计划摘要。
  - `参考模板 (optional)`：未来如需和某个“金标准”比对，可放在 `baseline`，当前实现已满足“至少需求 + 生成用例”的要求。
- **输出**：单个 JSON 文件，包含 `metadata` 与 `results` 列表；每个指标对象都携带 `name / score / summary / suggestions`。
- **默认目录**：由 `config.outputs.evaluations.default_dir` 控制（当前 `./output/evaluations`）。
- **得分范围**：强制要求返回 0~100 的整数/浮点数；若模型未能解析，结果为 `null` 并在终端告警。

---

## 2. 指标与衡量方式

| 指标 | 关注点 | 测量方法 | 扣分逻辑 |
| --- | --- | --- | --- |
| `alignment` | 测试方案是否体现了需求场景、策略思路与三方（产品/研发/测试）对齐 | LLM 读取需求摘要与候选用例，要求返回 `score / summary / risks[]`。`summary` 概述亮点与缺口；`risks` 列出“遗漏的思路、未定义基线、缺少预案”等。 | 每条 `risk` 默认扣 5 分；可在 Prompt 中要求模型标注“扣 5/10 分”，后续版本根据 `risks[].penalty` 扣分。 |
| `coverage` | 功能、异常、兼容、性能/安全等维度的覆盖度 + 优先级结构 | LLM 需要显式指出“缺少哪一端/场景/边界”。`risks` 里建议带上“iOS/Android 一致性缺失”等关键词，利于映射回用例模块。 | 同上，默认每条 -5；若 `risks` 为空则直接使用模型给出的 `score`。 |
| `bug_prevention` | 异常场景、降级、风控、监控、回滚能力 | Prompt 要求列出“缺少某预案/未覆盖某风险”并说明场景。重点关注发布阶段、资金/内容安全、基础设施故障。 | 同上，默认每条 -5；最多扣 40 分，避免出现负分。 |

> **说明**：若未来需要“自适应扣分”，可在 `risks` 中返回对象数组（`{"detail":"...","penalty":10}`），`EvaluationEngine._apply_risk_penalty()` 会读取 `penalty` 字段，否则回退至 5 分。

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
      "score": 53.0,
      "summary": "亮点...\n扣分点：共 5 项（每项 -5 分）",
      "suggestions": "- 未定义需求基线 (扣5分)\n- ...",
      "metadata": {
        "prompt": "evaluation.review_metrics[0]"
      }
    }
  ]
}
```

- `metadata.generated_at`：UTC ISO8601 时间。
- `metadata.config_hash`：`config.yaml` 内容的 MD5，方便追溯配置版本。
- `results[].summary`：保留模型原文，并在内部追加“扣分点统计行”，便于人工扫描。
- `results[].suggestions`：逐条呈现扣分条目（`- 描述 (扣5分)`），方便直接转成待办。

---

## 4. 扣分与客观性保障

1. **JSON 严格模式**：`review_metrics` Prompt 都以“仅输出 JSON”收尾，`EvaluationEngine` 首先尝试 `json.loads()`，失败时才退化为纯文本。
2. **风险驱动扣分**：
   - `_apply_risk_penalty(raw_score, len(risks))` 默认 `扣分 = min(risk_count × 5, 40)`，结果被 `round(..., 2)` 并限制在 `[0, 100]`。
   - 若模型返回的 `score` 本身很低（如 20），则不会因为无风险描述而抬高。
3. **可配置模板**：`config.yaml.evaluation.review_metrics` 支持自定义 `prompt/system_prompt/format_hint`，可以针对优惠券、支付等场景扩展指标。
4. **输入可追溯**：`baseline_path` / `candidate_path` 写入终端日志；若第二个参数无效，会自动 fallback 到最新一次 `/generate_cases` 输出，仍会生成报告。

---

## 5. 与生成流程的衔接

- `/generate_cases` 默认输出 JSON，目录可在 `outputs.testcases.default_dir` 改为任意路径。生成成功后会将路径写入 `paths.latest_testcase_cache`（默认 `./output/latest_testcase.json`）。
- `/evaluate_cases` 可只输入一个参数甚至不输入：
  - `python cli.py --config config.yaml` → `/evaluate_cases`：baseline=占位文本，candidate=latest 生成的 JSON。
  - `/evaluate_cases baseline.md`：baseline=baseline.md，candidate=latest。
  - `/evaluate_cases baseline.md candidate.json output=/tmp/report.json`：完全自定义。
- 评估完成后，终端会显示：
  - `Evaluation report saved to output/evaluations/<timestamp>_report.json`
  - 报告中 `results` 顺序与 `review_metrics` 一致，方便和配置一一对照。

---

## 6. 后续扩展

1. **严重度映射**：允许 `risks` 返回 `{"detail":"...","severity":"high"}`，由引擎映射 `high=10`、`medium=5`、`low=2`。
2. **统计指标**：结合 `_calculate_case_health()` 或 JSON Schema 校验，补充“字段缺失率、步骤平均长度”等硬指标，与 LLM 打分并行展示。
3. **多份候选比对**：未来 `/evaluate_cases baseline c1.json c2.json` 可输出多份 `results`，便于 A/B prompt 对比。
4. **可视化报告**：在 `output/evaluations` 同步生成 Markdown/HTML，将 `risks` 列表直观呈现给 QA/PM。

以上方案确保：输入至少包含“需求 + 生成用例”、输出为结构化 JSON 且分数处于 0~100 区间，并通过风险条目透明说明扣分原因，实现“无需人工复核也能快速客观评分”的目标。
