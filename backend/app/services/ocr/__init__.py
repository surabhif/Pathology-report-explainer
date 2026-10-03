"""OCR engines for PathExplain: scan pages → machine-readable text.

Default engine: Tesseract (free, runs on Render free tier via Dockerfile).
Optional: xAI Grok vision via OpenAI-compatible chat completions image input.
Every result is tagged with engine id + version for research honesty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class OcrPageResult:
    page: int
    text: str
    duration_ms: float = 0.0
    width: int | None = None
    height: int | None = None
    filename: str | None = None


@dataclass
class OcrResult:
    """Full OCR output for a report, tagged for evaluation."""

    engine: str
    engine_version: str
    text: str
    pages: list[OcrPageResult] = field(default_factory=list)
    duration_ms: float = 0.0
    estimated_cost_usd: float | None = None
    model: str | None = None  # for vision engines
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "engine_version": self.engine_version,
            "text": self.text,
            "pages": [
                {
                    "page": p.page,
                    "text": p.text,
                    "duration_ms": p.duration_ms,
                    "width": p.width,
                    "height": p.height,
                    "filename": p.filename,
                }
                for p in self.pages
            ],
            "duration_ms": self.duration_ms,
            "estimated_cost_usd": self.estimated_cost_usd,
            "model": self.model,
            "meta": self.meta,
        }


class OcrEngine(Protocol):
    def engine_id(self) -> str: ...

    def engine_version(self) -> str: ...

    async def ocr_image_bytes(
        self,
        image_bytes: bytes,
        *,
        mime: str = "image/jpeg",
        page: int = 1,
    ) -> OcrPageResult: ...
