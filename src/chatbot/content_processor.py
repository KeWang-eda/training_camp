"""Content processor module for handling text, documents, and media."""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

StatusCallback = Callable[[str, str], None]


@dataclass
class ContentSegment:
    """A normalized chunk of content ready for downstream ingestion."""

    type: str
    source: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class ContentProcessor:
    """Processes heterogeneous content into ContentSegment objects."""

    SUPPORTED_TEXT_FORMATS = {
        'txt', 'md', 'markdown', 'py', 'js', 'html',
        'css', 'json', 'xml', 'yaml', 'yml'
    }

    SUPPORTED_DOCUMENT_FORMATS = {'pdf', 'docx', 'doc', 'xlsx', 'xls'}
    SUPPORTED_IMAGE_FORMATS = {
        'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp'
    }

    def __init__(
        self,
        image_analyzer=None,
        status_callback: Optional[StatusCallback] = None,
        image_prompt_config: Optional[Dict[str, Any]] = None,
    ):
        self.image_analyzer = image_analyzer
        self._status_callback = status_callback
        self._logger = logging.getLogger(__name__)
        self._image_prompt_config = image_prompt_config or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_files(self, uploaded_files: Iterable[Any]) -> List[ContentSegment]:
        segments: List[ContentSegment] = []

        for file in uploaded_files:
            try:
                segment = self._build_segment(file)
                if segment:
                    segments.append(segment)
            except Exception as exc:
                file_name = getattr(file, 'name', 'unknown')
                self._notify('warning', f"Failed to process {file_name}: {exc}")

        return segments

    def process_local_files(self, file_paths: Iterable[str]) -> List[ContentSegment]:
        buffers = []

        for path in file_paths:
            expanded_path = os.path.abspath(os.path.expanduser(path))
            if not os.path.exists(expanded_path):
                self._notify('warning', f"File not found: {expanded_path}")
                continue

            try:
                with open(expanded_path, 'rb') as file_obj:
                    data = file_obj.read()
                buffer = io.BytesIO(data)
                buffer.name = os.path.basename(expanded_path)
                buffers.append(buffer)
            except OSError as exc:
                self._notify('warning', f"Failed to read {expanded_path}: {exc}")

        return self.process_files(buffers)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_segment(self, file) -> Optional[ContentSegment]:
        file_name = getattr(file, 'name', 'unknown')
        file_extension = file_name.split('.')[-1].lower() if '.' in file_name else ''

        if file_extension in self.SUPPORTED_TEXT_FORMATS:
            content = self._extract_text_content(file)
            return ContentSegment(type='text', source=file_name, content=content)

        if file_extension in self.SUPPORTED_DOCUMENT_FORMATS:
            content = self._extract_document_content(file, file_extension)
            return ContentSegment(
                type='document',
                source=file_name,
                content=content,
                metadata={'format': file_extension},
            )

        if file_extension in self.SUPPORTED_IMAGE_FORMATS:
            content, metadata = self._extract_image_content(file, file_extension)
            return ContentSegment(
                type='image',
                source=file_name,
                content=content,
                metadata=metadata,
            )

        self._notify('warning', f"Unsupported file format: {file_extension}")
        return None

    def _extract_text_content(self, file) -> str:
        data = file.read()
        if isinstance(data, bytes):
            return data.decode('utf-8', errors='ignore')
        return str(data)

    def _extract_document_content(self, file, file_extension: str) -> str:
        if not self.image_analyzer:
            self._notify('warning', f"No document analyzer available for {getattr(file, 'name', 'document')}")
            return ""

        try:
            self._notify('info', f"Analyzing document {getattr(file, 'name', 'document')} with AI...")
            self._reset_file(file)
            analysis_result = self.image_analyzer.analyze_image(file, file_extension)
            content = f"[AI Document Analysis Result] {getattr(file, 'name', 'document')}\n{analysis_result}"
            self._notify('success', f"Document {getattr(file, 'name', 'document')} analysis completed")
            return content
        except Exception as exc:
            file_name = getattr(file, 'name', 'document')
            self._notify('warning', f"AI document analysis failed {file_name}: {exc}")
            return f"[Document File] {file_name} - AI analysis failed"

    def _extract_image_content(self, file, image_type: str) -> (str, Dict[str, Any]):
        if not self.image_analyzer:
            self._notify('warning', f"No image analyzer available for {getattr(file, 'name', 'image')}")
            return "", {}

        prompt_entry = self._prepare_image_prompt(file, image_type)
        label = prompt_entry.get('label', '图片')
        prompt_text = prompt_entry.get('prompt') or self._image_prompt_config.get('default_prompt')
        if not prompt_text:
            prompt_text = "请详细描述这张图片的内容，包括结构、要素和潜在风险。"

        try:
            self._notify('info', f"Analyzing {label} «{getattr(file, 'name', 'image')}» with AI...")
            self._reset_file(file)
            analysis_result = self.image_analyzer.analyze_image(file, image_type, prompt=prompt_text)
            content = f"[{label}解析] {getattr(file, 'name', 'image')}\n{analysis_result}"
            self._notify('success', f"{label} {getattr(file, 'name', 'image')} analysis completed")
            metadata = {
                'format': image_type,
                'image_type': prompt_entry.get('key', 'image'),
                'image_label': label,
            }
            return content, metadata
        except Exception as exc:
            file_name = getattr(file, 'name', 'image')
            self._notify('warning', f"AI image analysis failed {file_name}: {exc}")
            return f"[Image File] {file_name} - AI analysis failed", {'format': image_type}

    def _prepare_image_prompt(self, file, image_type: str) -> Dict[str, Any]:
        config = self._image_prompt_config
        types = config.get('types', [])
        default_entry = config.get('default') or {
            'key': 'image',
            'label': '图片',
            'prompt': config.get('default_prompt') or "请描述这张图片。",
        }

        if not types or not config.get('classifier') or not self.image_analyzer:
            return default_entry

        options_text = ', '.join(
            f"{entry.get('key')}({entry.get('label', '')})" for entry in types
        )
        classifier_prompt = config['classifier'].format(options=options_text)

        self._reset_file(file)
        predicted = self.image_analyzer.classify_image(
            file,
            image_type,
            prompt=classifier_prompt,
            candidate_keys=[entry.get('key') for entry in types],
        )

        for entry in types:
            if entry.get('key') == predicted:
                return entry

        return default_entry

    @staticmethod
    def _reset_file(file) -> None:
        if hasattr(file, 'seek'):
            file.seek(0)

    def _notify(self, level: str, message: str) -> None:
        if self._status_callback:
            self._status_callback(level, message)
            return

        log_method = getattr(self._logger, level if hasattr(self._logger, level) else 'info')
        log_method(message)
