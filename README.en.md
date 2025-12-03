# ByteDance Training Camp · Terminal QA Copilot

The LangChain-based terminal assistant has been migrated to the `ByteDance/training_camp` repository. The tool focuses on **reading PRDs / design assets**, **generating structured test suites**, and **reviewing them automatically** without adding any GUI dependency.

## Key Features
- **Terminal-first UX** – `prompt_toolkit` + Rich provide history, completion, streaming responses, and syntax-highlighted code blocks.
- **Unified ingestion** – `/read` and `/read_link` normalize local docs, Feishu wikis, and screenshots into `ContentSegment` objects; images are auto-classified (flow chart, architecture, UI, etc.) before prompting.
- **Config-driven testcase generation** – `testcase_modes` and `testcase_layouts` describe prompts, field schemas, and test-plan checklists. `/generate_cases` outputs JSON (default) or Markdown under `./output/testcases`, with optional planner thoughts and plan summaries.
- **Automated evaluation** – `/evaluate_cases` consumes `evaluation.review_metrics`, requests structured JSON (score/summary/risks) from the LLM, and deducts 5 points per missing scenario (capped at 40). Baseline/candidate paths fall back to placeholders or the latest generated file, so the command is single-argument friendly.
- **Batch scripts** – `python cli.py --config config.yaml -f run.txt` executes `.tcl/.txt` scripts line by line, mirroring output to the console and to `./output/logs/shell.log` (overridable via `--log-file`). Errors stop execution but preserve the log trail.

## Quick Start
```bash
conda create -n training_camp python=3.12 -y
conda activate training_camp
pip install -r requirements.txt

# launch the REPL
python cli.py --config config.yaml
```
1. Set text/vision API keys under `app` (or via env vars such as `KIMI_API_KEY`).
2. Configure `feishu.app_id` / `app_secret` if you need `/read_link`.
3. Load assets with `/read` or `/read_link`, then run `/generate_cases` and `/evaluate_cases`.

## Core Commands
| Command | Description |
| --- | --- |
| `/read <paths...>` | Ingest one or more local files and index them for RAG. |
| `/read_link <feishu_url_or_id>` | Fetch and index a Feishu document. |
| `/generate_cases [mode] [output] [format] [thoughts] [plan]` | Produce structured cases using layouts defined in `config.yaml`. Supports positional or `key=value` syntax. |
| `/evaluate_cases <baseline> <candidate> [output]` | Compare baseline vs. generated cases; missing paths fall back to placeholders/latest output; scores follow the risk-deduction model. |
| `python cli.py --config config.yaml -f run.txt [--log-file ...]` | Run commands from a `.tcl/.txt` script file and capture execution logs. |

## Configuration Tips
- `app`: global models, base URLs, banner, and history length.
- `image_prompts`: classifier prompt plus per-type prompts for flow charts, architectures, wireframes, etc.
- `testcase_modes`: different generation presets (default, smoke...) referencing layouts.
- `testcase_layouts`: field schemas + optional test-plan sections injected into prompts via `{layout_schema}`.
- `outputs.testcases` / `outputs.evaluations`: default format and directories (both rooted at `./output`).
- `evaluation.review_metrics`: structured review prompts; each should return `{"score":...,"summary":"...","risks":[...]}` so the engine can apply deductions. Additional prompts can live under `evaluation_metrics`.
- `paths.latest_testcase_cache` & `paths.script_log`: where we cache the last testcase file and script runner logs.

## Repository Layout
```
training_camp/
├── cli.py
├── config.yaml
├── docs/
├── output/
├── pipeline/
├── scrpits/
├── src/
└── langchain-chatbot/  # legacy snapshot (read-only)
```

For detailed architecture notes see [docs/MODULE_OVERVIEW.md](docs/MODULE_OVERVIEW.md),
test-generation design choices in [docs/DESIGN_PRD_TEST.md](docs/DESIGN_PRD_TEST.md),
and evaluation details in [docs/EVALUATION_PLAN.md](docs/EVALUATION_PLAN.md) once updated.
