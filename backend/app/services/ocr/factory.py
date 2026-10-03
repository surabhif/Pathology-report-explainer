"""OCR engine factory — configurable via OCR_ENGINE env."""

from __future__ import annotations

import logging

from app.config import get_settings
from app.services.ocr import OcrEngine
from app.services.ocr.mock_engine import MockOcrEngine
from app.services.ocr.tesseract_engine import TesseractOcrEngine
from app.services.ocr.xai_vision import XaiVisionOcrEngine
from app.services.llm.openai_compatible import XAI_DEFAULT_BASE_URL, XAI_DEFAULT_MODEL

logger = logging.getLogger(__name__)


def tesseract_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


def get_ocr_engine(engine_name: str | None = None) -> OcrEngine:
    """Resolve OCR engine. Default: tesseract (falls back to mock if missing)."""
    settings = get_settings()
    name = (engine_name or settings.ocr_engine or "tesseract").strip().lower()

    if name in {"tesseract", "tess"}:
        if tesseract_available():
            return TesseractOcrEngine()
        logger.warning("OCR_ENGINE=tesseract but tesseract binary missing; using mock")
        return MockOcrEngine()

    if name in {"xai_vision", "xai", "grok_vision", "vision"}:
        key = (settings.llm_api_key or settings.xai_api_key or "").strip()
        if not key:
            logger.warning("OCR_ENGINE=xai_vision but no API key; falling back to tesseract/mock")
            return get_ocr_engine("tesseract")
        base = (settings.llm_base_url or "").strip() or XAI_DEFAULT_BASE_URL
        model = (settings.ocr_vision_model or "").strip() or (
            settings.llm_model if settings.llm_provider == "xai" and settings.llm_model else XAI_DEFAULT_MODEL
        )
        if model.startswith("mock"):
            model = XAI_DEFAULT_MODEL
        return XaiVisionOcrEngine(
            api_key=key,
            base_url=base,
            model=model,
            timeout=settings.llm_timeout_seconds,
            detail=settings.ocr_vision_detail,
        )

    if name == "mock":
        return MockOcrEngine()

    raise ValueError(f"Unknown OCR_ENGINE={name!r}; use tesseract, xai_vision, or mock")
