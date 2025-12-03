"""Image analyzer using multimodal AI models."""

import base64
import logging
from typing import List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


class ImageAnalyzer:
    """Analyzes images using multimodal AI models."""

    def __init__(self, api_key: str, base_url: str, model_name: str):
        """Initialize image analyzer.

        Args:
            api_key: API key for the multimodal model.
            base_url: Base URL for the API.
            model_name: Name of the multimodal model.
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def encode_image(self, image_file) -> Optional[str]:
        """Encode image file to base64 string.

        Args:
            image_file: Image file object.

        Returns:
            Base64 encoded image string or None if encoding fails.
        """
        try:
            # Reset file pointer to beginning
            image_file.seek(0)
            # Read image content
            image_bytes = image_file.read()
            # Encode to base64
            encoded_string = base64.b64encode(image_bytes).decode('utf-8')
            return encoded_string
        except Exception as e:
            logger.error(f"Image encoding failed: {str(e)}")
            return None

    def analyze_image(self, image_file, image_type: str, prompt: Optional[str] = None) -> str:
        """Analyze image using multimodal AI model.

        Args:
            image_file: Image file object.
            image_type: Image file extension (e.g., 'jpg', 'png').

        Returns:
            AI analysis result as string.
        """
        try:
            # Encode image
            base64_image = self.encode_image(image_file)
            if not base64_image:
                return "Image encoding failed, unable to analyze"

            image_url = f"data:image/{image_type};base64,{base64_image}"

            completion = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "你是 Kimi，多模态分析助手。",
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url},
                            },
                            {
                                "type": "text",
                                "text": prompt or "请详细描述这张图片的内容。如果是图表，请提取数据和结论；如果包含文字，请完整转写；最后给出简短的美学评价。",
                            },
                        ],
                    },
                ],
            )

            choice = completion.choices[0]
            return choice.message.content if choice.message else ""

        except Exception as e:
            logger.error(f"Image analysis failed: {str(e)}")
            return f"Image analysis failed: {str(e)}"


    def classify_image(
        self,
        image_file,
        image_type: str,
        prompt: str,
        candidate_keys: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Classify the image into predefined categories."""

        candidate_keys = candidate_keys or []
        try:
            base64_image = self.encode_image(image_file)
            if not base64_image:
                return candidate_keys[0] if candidate_keys else None

            image_url = f"data:image/{image_type};base64,{base64_image}"
            completion = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一名图像分类助手，只能回答候选类别中的一个 key。",
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_url}},
                            {"type": "text", "text": prompt},
                        ],
                    },
                ],
            )

            text = (completion.choices[0].message.content or "").lower()
            for key in candidate_keys:
                if key and key.lower() in text:
                    return key

            return candidate_keys[0] if candidate_keys else None
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Image classification failed: {exc}")
            return candidate_keys[0] if candidate_keys else None
