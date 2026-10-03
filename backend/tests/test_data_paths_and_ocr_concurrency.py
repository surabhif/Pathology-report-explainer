"""Data path resolution + OCR concurrency gate."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.config import get_settings
from app.services.ocr.concurrency import (
    OcrBusyError,
    reset_ocr_concurrency_for_tests,
    run_with_ocr_slot,
)
from app.services.ocr.cache import ocr_cache_root
from app.services.scan_assets import scan_cache_root


@pytest.fixture(autouse=True)
def _reset_ocr_gate(monkeypatch):
    reset_ocr_concurrency_for_tests()
    get_settings.cache_clear()
    yield
    reset_ocr_concurrency_for_tests()
    get_settings.cache_clear()


def test_data_dir_defaults_to_repo_data():
    settings = get_settings()
    assert settings.data_dir.name == "data"
    assert (settings.data_dir / "sample_reports.json").exists()
    assert scan_cache_root() == settings.data_dir / "scan_cache"
    assert ocr_cache_root() == settings.data_dir / "ocr_cache"
    assert (scan_cache_root() / "TCGA-B6-A401" / "manifest.json").exists()


def test_data_dir_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.data_dir == tmp_path
    assert scan_cache_root() == tmp_path / "scan_cache"
    assert ocr_cache_root() == tmp_path / "ocr_cache"


@pytest.mark.asyncio
async def test_ocr_slot_serializes_and_rejects_overflow(monkeypatch):
    monkeypatch.setenv("OCR_MAX_CONCURRENT", "1")
    monkeypatch.setenv("OCR_MAX_QUEUE", "1")
    get_settings.cache_clear()
    reset_ocr_concurrency_for_tests()

    started = asyncio.Event()
    release = asyncio.Event()
    order: list[str] = []

    async def holder() -> str:
        order.append("hold-start")
        started.set()
        await release.wait()
        order.append("hold-end")
        return "held"

    async def waiter() -> str:
        order.append("wait-start")
        return "waited"

    t_hold = asyncio.create_task(run_with_ocr_slot(holder))
    await started.wait()

    t_wait = asyncio.create_task(run_with_ocr_slot(waiter))
    # Give the waiter a moment to enter the queue (inflight=2 = 1 run + 1 queue).
    await asyncio.sleep(0.05)

    with pytest.raises(OcrBusyError):
        await run_with_ocr_slot(lambda: asyncio.sleep(0))

    release.set()
    assert await t_hold == "held"
    assert await t_wait == "waited"
    # Waiter factory only starts after the holder releases the semaphore.
    assert order == ["hold-start", "hold-end", "wait-start"]


def test_sample_reports_has_thirty_stratified():
    import json

    path = get_settings().data_dir / "sample_reports.json"
    reports = json.loads(path.read_text(encoding="utf-8"))
    assert len(reports) >= 30
    from collections import Counter

    counts = Counter(r["cancer_type"] for r in reports)
    assert counts["BRCA"] >= 10
    assert counts["COAD"] >= 10
    assert counts["LUAD"] >= 10
