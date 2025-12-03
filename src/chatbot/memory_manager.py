"""Memory manager for chat, document, and evaluation history."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class EvaluationRecord:
    name: str
    score: Optional[float]
    rationale: str
    suggestions: str


class MemoryManager:
    """Stores chat history, document summaries, and evaluation records."""

    def __init__(self, chat_history_limit: int = 100):
        self.chat_history: List[Dict[str, str]] = []
        self.document_summaries: List[str] = []
        self.evaluations: List[EvaluationRecord] = []
        self.chat_history_limit = chat_history_limit

    # ------------------------------------------------------------------
    # Chat history helpers
    # ------------------------------------------------------------------

    def add_chat_message(self, role: str, content: str) -> None:
        self.chat_history.append({'role': role, 'content': content})
        if len(self.chat_history) > self.chat_history_limit:
            self.chat_history = self.chat_history[-self.chat_history_limit:]

    def get_recent_messages(self, limit: int = 10) -> List[Dict[str, str]]:
        return self.chat_history[-limit:]

    # ------------------------------------------------------------------
    # Document summaries
    # ------------------------------------------------------------------

    def add_document_summary(self, summary: str) -> None:
        self.document_summaries.append(summary)
        if len(self.document_summaries) > 200:
            self.document_summaries = self.document_summaries[-200:]

    def get_document_overview(self) -> str:
        if not self.document_summaries:
            return ""
        return "\n\n".join(self.document_summaries[-20:])

    # ------------------------------------------------------------------
    # Evaluation records
    # ------------------------------------------------------------------

    def add_evaluation(self, record: EvaluationRecord) -> None:
        self.evaluations.append(record)
        if len(self.evaluations) > 100:
            self.evaluations = self.evaluations[-100:]

    def last_evaluation(self) -> Optional[EvaluationRecord]:
        return self.evaluations[-1] if self.evaluations else None
