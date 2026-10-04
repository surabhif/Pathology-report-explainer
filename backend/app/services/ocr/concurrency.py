"""Limit concurrent Tesseract OCR jobs for small-RAM hosts (Render free ≈512 MB).

Tesseract + Pillow on our ~1400px page images typically peaks around 150–250 MB RSS
per job. Running several at once OOMs a 512 MB instance, so the default is one
in-flight job with a tiny wait queue; additional callers get HTTP 429.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class OcrBusyError(RuntimeError):
    """Raised when the OCR concurrency queue is full."""

    def __init__(self, message: str = "OCR engine is busy; try again shortly.") -> None:
        super().__init__(message)
        self.code = "ocr_busy"


_sem: asyncio.Semaphore | None = None
_sem_limit: int | None = None
_inflight = 0
_state_lock = asyncio.Lock()


def _semaphore() -> asyncio.Semaphore:
    """Lazy semaphore sized from settings (rebuilt if the limit changes in tests)."""
    global _sem, _sem_limit
    limit = max(1, int(get_settings().ocr_max_concurrent))
    if _sem is None or _sem_limit != limit:
        _sem = asyncio.Semaphore(limit)
        _sem_limit = limit
    return _sem


def reset_ocr_concurrency_for_tests() -> None:
    """Reset module state between tests."""
    global _sem, _sem_limit, _inflight
    _sem = None
    _sem_limit = None
    _inflight = 0


async def run_with_ocr_slot(factory: Callable[[], Awaitable[T]]) -> T:
    """Run ``factory()`` under the OCR concurrency gate.

    ``factory`` is a zero-arg async callable so work only starts after a slot is
    acquired (avoids starting Tesseract before we know we can run).
    """
    global _inflight
    settings = get_settings()
    max_running = max(1, int(settings.ocr_max_concurrent))
    max_queue = max(0, int(settings.ocr_max_queue))
    capacity = max_running + max_queue

    async with _state_lock:
        if _inflight >= capacity:
            logger.warning(
                "ocr.busy inflight=%s capacity=%s (max_concurrent=%s max_queue=%s)",
                _inflight,
                capacity,
                max_running,
                max_queue,
            )
            raise OcrBusyError(
                f"OCR engine is busy ({_inflight} in flight; "
                f"limit {max_running} concurrent + {max_queue} queued). Retry shortly."
            )
        _inflight += 1

    try:
        async with _semaphore():
            logger.debug("ocr.slot.acquired inflight=%s", _inflight)
            return await factory()
    finally:
        async with _state_lock:
            _inflight = max(0, _inflight - 1)
