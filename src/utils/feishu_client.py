"""Feishu (Lark) document client for fetching raw wiki/docx content."""

from __future__ import annotations

import contextlib
import io
import json
import logging
import re
import warnings
from typing import Optional

warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=UserWarning,
)

import lark_oapi as lark
from lark_oapi.api.docx.v1 import RawContentDocumentRequest

logger = logging.getLogger(__name__)


class FeishuDocClient:
    """Small wrapper around the Feishu RawContent API."""

    _DOC_ID_PATTERN = re.compile(r"([A-Za-z0-9]+)$")

    def __init__(self, app_id: str, app_secret: str, base_url: str = "https://open.feishu.cn"):
        builder = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .log_level(lark.LogLevel.INFO)
        )

        if base_url != "https://open.feishu.cn":
            logger.warning(
                "Custom Feishu base_url %s is not directly supported by the SDK; default endpoint will be used.",
                base_url,
            )

        self.client = builder.build()

    @staticmethod
    def extract_document_id(link_or_id: str) -> Optional[str]:
        """Extract document token from a wiki/docx URL or raw id."""

        if not link_or_id:
            return None

        if "http" not in link_or_id:
            return link_or_id

        match = FeishuDocClient._DOC_ID_PATTERN.search(link_or_id.rstrip("/"))
        return match.group(1) if match else None

    def fetch_raw_content(self, document_id: str) -> str:
        """Fetch raw document JSON and return as a string."""

        request = (
            RawContentDocumentRequest.builder()
            .document_id(document_id)
            .lang(0)
            .build()
        )

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            response = self.client.docx.v1.document.raw_content(request)
        if not response.success():
            detail = {
                "code": response.code,
                "msg": response.msg,
                "log_id": response.get_log_id(),
            }
            raise RuntimeError(f"Feishu API failed: {detail}")

        # The SDK wraps response data in an object; dump to JSON text so it can be indexed.
        return json.dumps(json.loads(response.raw.content), ensure_ascii=False, indent=2)
