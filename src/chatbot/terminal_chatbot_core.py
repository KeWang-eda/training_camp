"""Terminal-focused chatbot core orchestrating LLM, RAG, and external docs."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from langchain.chains import ConversationChain, ConversationalRetrievalChain
from langchain.schema import HumanMessage, SystemMessage

from chatbot.chatbot_core import ChatbotCore
from chatbot.content_processor import ContentProcessor, ContentSegment
from chatbot.memory_manager import MemoryManager
from chatbot.testcase_generator import (
    TestcaseDocument,
    TestcaseGenerator,
    TestcaseModeConfig,
)
from chatbot.evaluation_engine import EvaluationEngine, EvaluationMetric, EvaluationResult
from utils.image_analyzer import ImageAnalyzer
from utils.feishu_client import FeishuDocClient

StatusCallback = Callable[[str, str], None]


class TerminalChatbotCore:
    """Coordinates document loading and conversations for the CLI."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str = "kimi-k2-turbo-preview",
        status_callback: Optional[StatusCallback] = None,
        history_limit: int = 50,
        image_api_key: Optional[str] = None,
        image_base_url: Optional[str] = None,
        image_model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        image_prompt_config: Optional[Dict[str, Any]] = None,
        testcase_modes: Optional[Dict[str, Dict[str, Any]]] = None,
        evaluation_metrics: Optional[List[Dict[str, Any]]] = None,
        review_metrics: Optional[List[Dict[str, Any]]] = None,
        testcase_layouts: Optional[Dict[str, Any]] = None,
        default_testcase_format: Optional[str] = None,
        default_testcase_dir: Optional[str] = None,
        evaluation_output_dir: Optional[str] = None,
        latest_testcase_cache: Optional[str] = None,
        embedding_model_name: Optional[str] = None,
        text_splitter_config: Optional[Dict[str, int]] = None,
        config_hash: Optional[str] = None,
        feishu_app_id: Optional[str] = None,
        feishu_app_secret: Optional[str] = None,
        feishu_base_url: str = "https://open.feishu.cn",
    ):
        self.logger = logging.getLogger(__name__)
        self._status_callback = status_callback
        self.history_limit = history_limit
        self.system_prompt = system_prompt

        self.core = ChatbotCore(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            embedding_model_name=embedding_model_name,
            text_splitter_config=text_splitter_config,
        )
        self.core.initialize_models()
        self.llm = self.core.get_llm()

        self.base_chain: ConversationChain = self.core.create_conversation_chain(system_prompt=self.system_prompt)
        self.vector_store = None
        self.rag_chain: Optional[ConversationalRetrievalChain] = None

        analyzer = None
        if image_api_key and image_model_name:
            analyzer = ImageAnalyzer(
                api_key=image_api_key,
                base_url=image_base_url or base_url,
                model_name=image_model_name,
            )

        self.memory = MemoryManager(chat_history_limit=history_limit)

        self.content_processor = ContentProcessor(
            image_analyzer=analyzer,
            status_callback=self._notify,
            image_prompt_config=image_prompt_config,
        )

        self.testcase_layouts = testcase_layouts or {}
        self.default_testcase_format = (default_testcase_format or 'json').lower()
        self.testcase_output_dir = Path(default_testcase_dir or './output/testcases').expanduser()
        self.evaluation_output_dir = Path(evaluation_output_dir or './output/evaluations').expanduser()
        self.latest_testcase_cache_path = Path(latest_testcase_cache or './output/latest_testcase.json').expanduser()
        self.latest_testcase_path: Optional[str] = self._load_latest_testcase_cache()

        self.testcase_generator = TestcaseGenerator(
            self.llm,
            self.memory,
            layout_config=self.testcase_layouts,
        )
        self.evaluation_engine = EvaluationEngine(
            self.llm,
            self.memory,
            review_metrics=review_metrics or [],
        )

        self.feishu_client: Optional[FeishuDocClient] = None
        if feishu_app_id and feishu_app_secret:
            self.feishu_client = FeishuDocClient(
                app_id=feishu_app_id,
                app_secret=feishu_app_secret,
                base_url=feishu_base_url,
            )

        self.conversation_history: List[Dict[str, str]] = []
        self.loaded_segments: List[ContentSegment] = []
        self.testcase_modes = testcase_modes or {}
        self.evaluation_metrics = evaluation_metrics or []
        self.config_hash = config_hash or "unknown"

    def ingest_local_files(self, file_paths: Sequence[str]) -> int:
        """Ingest local files and rebuild the retriever."""

        segments = self.content_processor.process_local_files(file_paths)
        return self._ingest_segments(segments)

    def ingest_single_file(self, file_path: str) -> bool:
        """Compatibility helper to ingest a single file."""

        return self.ingest_local_files([file_path]) > 0

    def ingest_feishu_document(self, link_or_id: str) -> int:
        """Fetch a Feishu doc by link/id and ingest it."""

        if not self.feishu_client:
            self._notify('warning', "Feishu client not configured.")
            return 0

        doc_id = self.feishu_client.extract_document_id(link_or_id)
        if not doc_id:
            self._notify('warning', "Invalid Feishu link or document id.")
            return 0

        try:
            content = self.feishu_client.fetch_raw_content(doc_id)
        except Exception as exc:
            self._notify('error', f"Failed to fetch Feishu document: {exc}")
            return 0

        segments = [
            ContentSegment(
                type='link',
                source=f'feishu:{doc_id}',
                content=content,
                metadata={'source': 'feishu'},
            )
        ]
        count = self._ingest_segments(segments)
        if count:
            self._notify('success', f"Indexed Feishu document {doc_id}.")
        return count

    def ask(self, prompt: str, stream_handler=None, use_rag: Optional[bool] = None) -> str:
        """Generate a response, optionally using the RAG chain."""

        self._append_history('user', prompt)
        chain, payload = self._select_chain(prompt, use_rag)
        config = {'callbacks': [stream_handler]} if stream_handler else None

        try:
            if config:
                result = chain.invoke(payload, config)
            else:
                result = chain.invoke(payload)
        except Exception as exc:  # pragma: no cover
            self._notify('error', f"Failed to generate response: {exc}")
            raise

        response = self._extract_response(chain, result)
        self._append_history('assistant', response)
        return response

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Return recent messages for display/saving."""

        return list(self.conversation_history)

    def reset_vector_store(self) -> None:
        """Clear loaded documents and retriever."""

        self.vector_store = None
        self.rag_chain = None

    def get_vector_store_status(self) -> bool:
        """Return True if documents have been indexed."""

        return self.vector_store is not None

    def _select_chain(self, prompt: str, use_rag: Optional[bool]) -> Tuple[ConversationChain, Dict[str, str]]:
        """Decide which chain to use and prepare the payload."""

        if use_rag is None:
            use_rag = self.vector_store is not None

        if use_rag and self.rag_chain:
            return self.rag_chain, {
                "question": prompt,
                "chat_history": self._build_rag_history(),
            }

        return self.base_chain, {"input": prompt}

    @staticmethod
    def _extract_response(chain: ConversationChain, result: Dict[str, str]) -> str:
        """Normalize chain outputs to a plain string."""

        if isinstance(chain, ConversationalRetrievalChain):
            return result.get('answer') or result.get('result', '')
        return result.get('response', '') or ''

    def _append_history(self, role: str, content: str) -> None:
        """Append a message to the local history buffer."""

        self.conversation_history.append({'role': role, 'content': content})
        self.memory.add_chat_message(role, content)
        if len(self.conversation_history) > self.history_limit:
            self.conversation_history = self.conversation_history[-self.history_limit:]

    def _build_rag_history(self) -> List[tuple]:
        """Create chat history tuples for ConversationalRetrievalChain."""

        history: List[tuple] = []
        last_user: Optional[str] = None

        for message in self.conversation_history:
            if message['role'] == 'user':
                last_user = message['content']
            elif message['role'] == 'assistant' and last_user is not None:
                history.append((last_user, message['content']))
                last_user = None

        return history[-self.history_limit:]

    def _ingest_segments(self, documents: List[ContentSegment]) -> int:
        if not documents:
            self._notify('warning', "No documents were processed.")
            return 0

        vector_store_documents = [
            {
                'content': segment.content,
                'name': segment.source,
                'metadata': segment.metadata,
            }
            for segment in documents
        ]

        vector_store = self.core.create_vector_store(vector_store_documents)
        if not vector_store:
            self._notify('warning', "Unable to build vector store from documents.")
            return 0

        self.vector_store = vector_store
        self.loaded_segments.extend(documents)
        for segment in documents:
            snippet = segment.content[:500]
            self.memory.add_document_summary(f"{segment.source}: {snippet}")
        self.rag_chain = self.core.create_conversation_chain(vector_store, system_prompt=self.system_prompt)
        self._notify('success', f"Indexed {len(documents)} document(s).")
        return len(documents)

    # ------------------------------------------------------------------
    # Testcase generation & evaluation
    # ------------------------------------------------------------------

    def run_testcase_generation(
        self,
        mode: str = "default",
        output_path: Optional[str] = None,
        output_format: Optional[str] = None,
        show_thoughts: bool = False,
        show_plan_summary: bool = False,
    ) -> Tuple[str, Optional[List[str]], Optional[List[Dict[str, Any]]]]:
        if not self.testcase_modes:
            raise ValueError("No testcase_modes configured in config.yaml")

        mode_conf = self._resolve_mode_config(mode)
        document = self.testcase_generator.generate(self.loaded_segments, mode_conf)
        final_format = (output_format or self.default_testcase_format).lower()
        serialized, suffix = self._render_testcase_document(document, mode, final_format)
        output = self._write_output('testcases', output_path, serialized, suffix=suffix)
        self._notify('success', f"Generated test cases saved to {output}")
        self._update_latest_testcase_cache(output)
        plan_notes = document.planner_notes if show_thoughts else None
        plan_summary = (
            [section.as_dict() for section in document.plan_summary]
            if show_plan_summary and document.plan_summary
            else None
        )
        return output, plan_notes, plan_summary

    def run_evaluation(
        self,
        baseline_path: Optional[str] = None,
        candidate_path: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> str:

        baseline_text = self._load_input_text(
            baseline_path,
            role='baseline',
            fallback_text="[baseline placeholder] 未提供基线内容，将直接依据候选用例进行评审。",
        )
        candidate_source = candidate_path or self.latest_testcase_path
        candidate_text = self._load_input_text(
            candidate_source,
            role='candidate',
            fallback_text=baseline_text,
        )

        metrics = self._build_metric_configs()
        placeholder = self._calculate_case_health(candidate_text)
        results = self.evaluation_engine.evaluate(baseline_text, candidate_text, metrics, placeholder)
        report_text = self._format_evaluation_report_json(results)
        output = self._write_output('evaluations', output_path, report_text, suffix='report.json')
        self._notify('success', f"Evaluation report saved to {output}")
        return output

    def _resolve_mode_config(self, mode: str) -> TestcaseModeConfig:
        raw = self.testcase_modes.get(mode) or self.testcase_modes.get('default')
        if not raw:
            raise ValueError(f"Unknown testcase generation mode: {mode}")
        metadata = raw.get('metadata', {})
        planner_prompt = raw.get('planner_prompt') or raw.get('prompt')
        builder_prompt = raw.get('builder_prompt') or raw.get('prompt')
        if not builder_prompt:
            raise ValueError('testcase mode missing builder prompt')
        layout_key = raw.get('layout') or 'detailed'
        if layout_key not in self.testcase_layouts:
            layout_key = next(iter(self.testcase_layouts), 'basic')
        return TestcaseModeConfig(
            name=mode,
            planner_prompt=planner_prompt or '请列出需要覆盖的模块。',
            builder_prompt=builder_prompt,
            system_prompt=raw.get('system_prompt'),
            context_limit=int(raw.get('context_limit', 20000)),
            metadata=metadata,
            layout=layout_key or 'detailed',
        )

    def _build_metric_configs(self) -> List[EvaluationMetric]:
        metrics: List[EvaluationMetric] = []
        for raw in self.evaluation_metrics:
            prompt = raw.get('prompt')
            if not prompt:
                continue
            metrics.append(
                EvaluationMetric(
                    name=raw.get('name', 'metric'),
                    prompt=prompt,
                    system_prompt=raw.get('system_prompt'),
                    metadata=raw.get('metadata', {}),
                )
            )
        return metrics

    def _format_evaluation_report_json(self, results: List[EvaluationResult]) -> str:
        payload = {
            "metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "config_hash": self.config_hash,
            },
            "results": [],
        }
        for record in results:
            payload["results"].append(
                {
                    "name": record.name,
                    "score": record.score,
                    "summary": record.rationale,
                    "suggestions": record.suggestions,
                    "metadata": record.metadata,
                }
            )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _write_output(self, subdir: str, desired_path: Optional[str], content: str, suffix: str) -> str:
        if subdir == 'testcases':
            base_dir = self.testcase_output_dir
        elif subdir == 'evaluations':
            base_dir = self.evaluation_output_dir
        else:
            base_dir = Path('./output') / subdir
        base_dir.mkdir(parents=True, exist_ok=True)

        if desired_path:
            path = Path(desired_path)
            if path.suffix == '':
                path = path.with_suffix(f'.{suffix.split(".")[-1]}')
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            path = base_dir / f'{timestamp}_{suffix}'

        path.write_text(content, encoding='utf-8')
        return str(path)

    def _load_latest_testcase_cache(self) -> Optional[str]:
        path = getattr(self, 'latest_testcase_cache_path', None)
        if not path:
            return None
        try:
            if path.exists():
                cached = path.read_text(encoding='utf-8').strip()
                return cached or None
        except OSError as exc:
            self._notify('warning', f"Failed to read latest testcase cache ({path}): {exc}")
        return None

    def _update_latest_testcase_cache(self, new_path: str) -> None:
        self.latest_testcase_path = new_path
        path = getattr(self, 'latest_testcase_cache_path', None)
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_path, encoding='utf-8')
        except OSError as exc:
            self._notify('warning', f"Failed to persist latest testcase cache: {exc}")

    def _render_testcase_document(self, document: TestcaseDocument, mode: str, output_format: str) -> Tuple[str, str]:
        """Render testcase document into the desired format."""

        normalized = (output_format or 'markdown').lower()
        generated_at = datetime.utcnow().isoformat()
        metadata = {
            "generated_at": generated_at,
            "config_hash": self.config_hash,
            "mode": mode,
        }

        if normalized in {'md', 'markdown'}:
            header = (
                f"> generated_at: {generated_at}\n"
                f"> config_hash: {self.config_hash}\n"
            )
            body = document.to_markdown(self.testcase_generator.layouts)
            return header + "\n" + body, f'{mode}.md'
        if normalized == 'json':
            payload = {
                "metadata": metadata,
                "document": document.to_dict(),
            }
            return json.dumps(payload, ensure_ascii=False, indent=2), f'{mode}.json'
        raise ValueError(f"Unsupported testcase output format: {output_format}")

    @staticmethod
    def _calculate_case_health(candidate_text: str) -> float:
        """Lightweight heuristic scoring for test case completeness."""

        blocks = [block.strip() for block in candidate_text.split('##') if block.strip()]
        if not blocks:
            return 0.0

        scores: List[float] = []
        for block in blocks:
            lowered = block.lower()
            features = 0
            if '前置' in block or 'precondition' in lowered:
                features += 1
            if '步骤' in block or 'step' in lowered:
                features += 1
            if '预期' in block or 'expected' in lowered:
                features += 1
            completeness = features / 3
            line_count = len([line for line in block.splitlines() if line.strip()])
            verbosity = min(line_count / 6, 1)
            scores.append(0.6 * completeness + 0.4 * verbosity)

        return round(sum(scores) / len(scores) * 100, 2)

    def _load_input_text(
        self,
        input_path: Optional[str],
        role: str,
        fallback_text: Optional[str] = None,
    ) -> str:
        """Load text from file path; fallback to provided text or placeholder."""

        if input_path:
            path = Path(input_path).expanduser()
            if path.exists():
                try:
                    return path.read_text(encoding='utf-8')
                except OSError as exc:
                    self._notify('warning', f"Failed to read {role} file {input_path}: {exc}")
            else:
                self._notify('warning', f"{role.title()} file {path} not found.")

        if fallback_text:
            return fallback_text

        return f"[{role} placeholder] 未提供 {role} 内容。"

    def _notify(self, level: str, message: str) -> None:
        """Forward status events to the provided callback or logger."""

        if self._status_callback:
            self._status_callback(level, message)
            return

        log_method = getattr(self.logger, level if hasattr(self.logger, level) else 'info')
        log_method(message)
