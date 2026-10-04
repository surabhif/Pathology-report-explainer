"""Deterministic mock OCR for tests / environments without Tesseract."""

from __future__ import annotations

import time

from app.services.ocr import OcrPageResult


class MockOcrEngine:
    """Returns a canned transcription; useful in CI without system packages."""

    name = "mock"

    def __init__(self, *, canned_text: str | None = None) -> None:
        self._canned = canned_text

    def engine_id(self) -> str:
        return self.name

    def engine_version(self) -> str:
        return "mock-ocr-v1"

    async def ocr_image_bytes(
        self,
        image_bytes: bytes,
        *,
        mime: str = "image/jpeg",
        page: int = 1,
    ) -> OcrPageResult:
        t0 = time.perf_counter()
        if self._canned is not None:
            text = self._canned
        else:
            # Tiny fingerprint so empty images still produce something measurable.
            text = f"[mock-ocr page={page} bytes={len(image_bytes)}]"
        ms = (time.perf_counter() - t0) * 1000
        return OcrPageResult(page=page, text=text, duration_ms=ms)
