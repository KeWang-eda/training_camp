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
    suggestions: str
    metadata: Dict[str, Any]


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
                    suggestions="",
                    metadata=metric.metadata,
                )
            )

        for record in results:
            self.memory.add_evaluation(
                EvaluationRecord(
                    name=record.name,
                    score=record.score,
                    rationale=record.rationale,
                    suggestions=record.suggestions,
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
            score = parsed.get('score')
            summary = parsed.get('summary') or response
            risks_data = parsed.get('risks') or []
            if not isinstance(risks_data, list):
                risks_data = [str(risks_data)]
            risks_clean = [item.strip() for item in risks_data if str(item).strip()]
            adjusted_score = self._apply_risk_penalty(score, len(risks_clean))
            detail_suffix = ""
            if risks_clean:
                detail_suffix = f"\n扣分点：共 {len(risks_clean)} 项（每项 -5 分）。"
            summary_with_penalty = summary + detail_suffix
            suggestions = "\n".join(f"- {item} (扣5分)" for item in risks_clean)
            review_results.append(
                EvaluationResult(
                    name=metric.name,
                    score=adjusted_score,
                    rationale=summary_with_penalty,
                    suggestions=suggestions,
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
        base_score = None
        if isinstance(raw_score, (int, float)):
            base_score = float(raw_score)
        else:
            extracted = self._extract_score(str(raw_score)) if raw_score is not None else None
            base_score = float(extracted) if extracted is not None else None
        if base_score is None:
            return None
        deduction = min(risk_count * 5, 40)
        return max(0.0, round(base_score - deduction, 2))

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
