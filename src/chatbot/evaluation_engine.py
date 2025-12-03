"""Structured evaluation pipeline for generated test cases."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain.schema import HumanMessage, SystemMessage

from chatbot.memory_manager import EvaluationRecord, MemoryManager


@dataclass
class EvaluationMetric:
    name: str
    prompt: str
    system_prompt: Optional[str]
    metadata: Dict[str, str]


@dataclass
class ReviewMetricConfig:
    name: str
    prompt: str
    system_prompt: Optional[str] = None
    format_hint: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    name: str
    score: Optional[float]
    rationale: str
    suggestions: List[Dict[str, Any]]
    penalty_summary: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class EvaluationEngine:
    """Runs configured evaluation metrics and returns structured results."""

    def __init__(self, llm, memory: MemoryManager, review_metrics: Optional[List[Dict[str, Any]]] = None):
        self.llm = llm
        self.memory = memory
        self.review_metrics = self._build_review_configs(review_metrics or [])

    def evaluate(
        self,
        baseline_text: str,
        candidate_text: str,
        metrics: List[EvaluationMetric],
        placeholder_score: float,
    ) -> List[EvaluationResult]:
        results: List[EvaluationResult] = []

        if self.review_metrics:
            results.extend(self._run_structured_review(baseline_text, candidate_text))

        for metric in metrics or []:
            user_prompt = self._fill_template(
                metric.prompt,
                baseline=baseline_text,
                candidate=candidate_text,
            )
            messages = [
                SystemMessage(content=metric.system_prompt or "你是评测专家，请返回 JSON。"),
                HumanMessage(content=user_prompt),
            ]
            response = self.llm.invoke(messages).content.strip()
            score = self._extract_score(response)
            results.append(
                EvaluationResult(
                    name=metric.name,
                    score=score,
                    rationale=response,
                    suggestions=[],
                    penalty_summary={},
                    metadata=metric.metadata,
                )
            )

        for record in results:
            self.memory.add_evaluation(
                EvaluationRecord(
                    name=record.name,
                    score=record.score,
                    rationale=record.rationale,
                    suggestions=json.dumps(record.suggestions, ensure_ascii=False),
                )
            )

        return results

    def _run_structured_review(self, baseline_text: str, candidate_text: str) -> List[EvaluationResult]:
        review_results: List[EvaluationResult] = []
        for metric in self.review_metrics:
            prompt_body = self._fill_template(
                metric.prompt,
                baseline=baseline_text,
                candidate=candidate_text,
            )
            if metric.format_hint:
                prompt_body = f"{prompt_body}\n{metric.format_hint}"
            messages = [
                SystemMessage(content=metric.system_prompt or "你是 QA 评审专家，请根据指引返回 JSON。"),
                HumanMessage(content=prompt_body),
            ]
            response = self.llm.invoke(messages).content.strip()
            parsed = self._parse_json_response(response)
            # Summary stays descriptive only
            summary = parsed.get('summary') or response

            # Normalize suggestions structure (array of dicts)
            raw_suggestions = parsed.get('suggestions') or []
            if not isinstance(raw_suggestions, list):
                raw_suggestions = []
            # Fallback: if model returns 'risks' list, convert to suggestions with default level
            if not raw_suggestions:
                risks_data = parsed.get('risks') or []
                if isinstance(risks_data, list):
                    raw_suggestions = risks_data

            normalized: List[Dict[str, Any]] = []
            total_deduction = 0

            for idx, item in enumerate(raw_suggestions, start=1):
                if not isinstance(item, dict):
                    # convert plain string to suggestion with default priority
                    text = str(item).strip()
                    if not text:
                        continue
                    # infer level via LLM; if cannot infer, skip (no default)
                    inferred_level = self._infer_level(text)
                    if inferred_level is None:
                        continue
                    deduction = 10 - inferred_level
                    normalized.append({
                        "id": f"S{idx}",
                        "text": text,
                        "priority": f"P{inferred_level}",
                        "level": inferred_level,
                        "deduction": deduction,
                        "category": "general",
                        "hint": "Level inferred by model",
                    })
                    total_deduction += deduction
                    continue

                # extract fields
                text = str(item.get('text') or item.get('内容') or '').strip()
                sid = str(item.get('id') or item.get('编号') or f"S{idx}")
                priority = str(item.get('priority') or '').strip().upper()
                level_val = item.get('level')
                deduction_val = item.get('deduction')
                category = item.get('category') or 'general'
                hint = item.get('hint') or ''

                # determine level from priority if missing
                if level_val is None and priority.startswith('P') and priority[1:].isdigit():
                    level_val = int(priority[1:])

                # If still missing, infer via LLM; if fail, skip this suggestion
                if not isinstance(level_val, int):
                    level_val = self._infer_level(text)
                    if level_val is None:
                        continue
                level_val = max(0, min(9, level_val))

                # ensure priority matches level
                priority = priority or f"P{level_val}"

                # compute deduction if missing; clamp 0..10
                if not isinstance(deduction_val, (int, float)):
                    deduction_val = 10 - level_val
                deduction_val = max(0, min(10, int(deduction_val)))

                normalized.append({
                    "id": sid,
                    "text": text or f"Suggestion {sid}",
                    "priority": priority,
                    "level": level_val,
                    "deduction": deduction_val,
                    "category": category,
                    "hint": hint,
                })
                total_deduction += deduction_val

            # score per metric: 100 - total_deduction (lower bounded at 0)
            score_metric = max(0.0, float(100 - total_deduction))

            review_results.append(
                EvaluationResult(
                    name=metric.name,
                    score=score_metric,
                    rationale=summary,
                    suggestions=normalized,
                    penalty_summary={
                        "count": len(normalized),
                        "total_deduction": total_deduction,
                    },
                    metadata=metric.metadata,
                )
            )
        return review_results

    @staticmethod
    def _build_review_configs(configs: List[Dict[str, Any]]) -> List[ReviewMetricConfig]:
        parsed: List[ReviewMetricConfig] = []
        for entry in configs:
            prompt = entry.get('prompt')
            if not prompt:
                continue
            parsed.append(
                ReviewMetricConfig(
                    name=entry.get('name', 'review'),
                    prompt=prompt,
                    system_prompt=entry.get('system_prompt'),
                    format_hint=entry.get('format_hint'),
                    metadata=entry.get('metadata', {}),
                )
            )
        return parsed

    @staticmethod
    def _parse_json_response(response: str) -> Dict[str, Any]:
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {}

    def _apply_risk_penalty(self, raw_score: Any, risk_count: int) -> Optional[float]:
        """Deprecated in new model; retained for backwards compatibility."""
        base_score = None
        if isinstance(raw_score, (int, float)):
            base_score = float(raw_score)
        else:
            extracted = self._extract_score(str(raw_score)) if raw_score is not None else None
            base_score = float(extracted) if extracted is not None else None
        if base_score is None:
            return None
        deduction = risk_count * 5
        return max(0.0, round(base_score - deduction, 2))

    def _infer_level(self, text: str) -> Optional[int]:
        """Use LLM to infer priority level (0..9) from suggestion text.

        Returns None when inference fails to avoid defaulting.
        """
        try:
            hint = (
                "你是评审助手。根据建议的重要性输出严格JSON，不要额外文本。\n"
                "级别说明：P0最严重(10分扣)，P9最轻(1分扣)。仅返回 {\"level\": 整数0..9}。\n"
                "建议: " + text
            )
            messages = [
                SystemMessage(content="你是评审专家，只返回JSON"),
                HumanMessage(content=hint),
            ]
            resp = self.llm.invoke(messages).content.strip()
            data = self._parse_json_response(resp)
            lvl = data.get('level')
            if isinstance(lvl, int) and 0 <= lvl <= 9:
                return lvl
            # attempt parse from priority string
            pr = data.get('priority')
            if isinstance(pr, str) and pr.upper().startswith('P') and pr[1:].isdigit():
                val = int(pr[1:])
                if 0 <= val <= 9:
                    return val
            return None
        except Exception:
            return None

    @staticmethod
    def _fill_template(template: str, **kwargs) -> str:
        result = template
        for key, value in kwargs.items():
            result = result.replace(f'{{{key}}}', str(value))
        return result

    @staticmethod
    def _extract_score(response: str) -> Optional[float]:
        try:
            for token in response.replace('%', ' ').split():
                cleaned = token.strip().strip(',')
                if cleaned.replace('.', '', 1).isdigit():
                    value = float(cleaned)
                    if 0 <= value <= 100:
                        return value
            return None
        except ValueError:
            return None
