"""xAI Grok vision OCR via OpenAI-compatible chat completions image input.

Uses chat/completions with content parts:
  {type: image_url, image_url: {url: data:image/jpeg;base64,..., detail: low|high}}
Docs: https://docs.x.ai/developers/model-capabilities/images/understanding
       https://docs.x.ai/developers/model-capabilities/legacy/chat-completions

Cost/latency: vision tokens are billed as image tokens. We default to detail=low
and max 2 pages, and cache results so demos do not re-spend.
"""

from __future__ import annotations

import base64
import logging
import time

import httpx

from app.services.llm.errors import LLMServiceError
from app.services.ocr import OcrPageResult

logger = logging.getLogger(__name__)

OCR_SYSTEM = (
    "You are an OCR transcription engine for pathology report page images. "
    "Transcribe ALL visible text verbatim. Preserve line breaks when helpful. "
    "Do not summarize, translate, or invent text. Output only the transcribed text."
)

# Rough cost estimate for documentation / dashboard (USD per page, detail=low).
# Image tokens dominate; grok-4.20-0309-non-reasoning is ~$1.25 / 1M input tokens.
# Low-detail tiles ≈ 85–300 image tokens → ~$0.0001–$0.0004 + completion.
# We report a conservative estimate used for budgeting demos.
DEFAULT_EST_USD_PER_PAGE_LOW = 0.002
DEFAULT_EST_USD_PER_PAGE_HIGH = 0.01


class XaiVisionOcrEngine:
    """OCR via a vision-capable Grok model."""

    name = "xai_vision"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.x.ai/v1",
        model: str = "grok-4.20-0309-non-reasoning",
        timeout: float = 120.0,
        detail: str = "low",
    ) -> None:
        if not api_key:
            raise ValueError("API key required for xai_vision OCR")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._detail = detail if detail in {"low", "high", "auto"} else "low"

    def engine_id(self) -> str:
        return self.name

    def engine_version(self) -> str:
        return f"xai_vision:{self._model}:detail={self._detail}"

    async def ocr_image_bytes(
        self,
        image_bytes: bytes,
        *,
        mime: str = "image/jpeg",
        page: int = 1,
    ) -> OcrPageResult:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        payload = {
            "model": self._model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": OCR_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": self._detail},
                        },
                        {
                            "type": "text",
                            "text": (
                                f"Transcribe page {page} of this pathology report scan "
                                "verbatim. Output only the text."
                            ),
                        },
                    ],
                },
            ],
        }
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            raise LLMServiceError(
                f"Vision OCR timed out after {int(self._timeout)}s.",
                code="ocr_timeout",
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise LLMServiceError(
                f"Vision OCR returned HTTP {status}.",
                code="ocr_http_error",
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMServiceError(
                "Could not reach vision OCR service.",
                code="ocr_network_error",
            ) from exc

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMServiceError(
                "Vision OCR returned unexpected response shape.",
                code="ocr_bad_response",
            ) from exc

        ms = (time.perf_counter() - t0) * 1000
        usage = data.get("usage") or {}
        logger.info(
            "ocr.xai_vision page=%s chars=%d ms=%.0f model=%s usage=%s",
            page,
            len(text),
            ms,
            self._model,
            {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens") if k in usage},
        )
        return OcrPageResult(page=page, text=text.strip(), duration_ms=ms)
