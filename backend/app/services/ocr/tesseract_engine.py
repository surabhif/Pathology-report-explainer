"""Tesseract OCR engine (default — free, local, Render-friendly)."""

from __future__ import annotations

import io
import logging
import time

from app.services.ocr import OcrPageResult

logger = logging.getLogger(__name__)


class TesseractOcrEngine:
    """Wraps pytesseract + system tesseract-ocr package."""

    name = "tesseract"

    def __init__(self, *, lang: str = "eng", psm: int = 6) -> None:
        self._lang = lang
        self._psm = psm

    def engine_id(self) -> str:
        return self.name

    def engine_version(self) -> str:
        try:
            import pytesseract

            return f"tesseract-{pytesseract.get_tesseract_version()}"
        except Exception:  # noqa: BLE001
            return "tesseract-unknown"

    async def ocr_image_bytes(
        self,
        image_bytes: bytes,
        *,
        mime: str = "image/jpeg",
        page: int = 1,
    ) -> OcrPageResult:
        import asyncio

        return await asyncio.to_thread(self._ocr_sync, image_bytes, page)

    def _ocr_sync(self, image_bytes: bytes, page: int) -> OcrPageResult:
        import pytesseract
        from PIL import Image

        t0 = time.perf_counter()
        img = Image.open(io.BytesIO(image_bytes))
        # Convert to RGB for consistent OCR
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        config = f"--psm {self._psm}"
        text = pytesseract.image_to_string(img, lang=self._lang, config=config) or ""
        ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "ocr.tesseract page=%s chars=%d ms=%.0f",
            page,
            len(text),
            ms,
        )
        return OcrPageResult(
            page=page,
            text=text.strip(),
            duration_ms=ms,
            width=img.width,
            height=img.height,
        )
