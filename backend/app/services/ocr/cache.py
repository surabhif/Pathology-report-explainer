"""Disk + DB OCR cache so demos do not re-run expensive vision calls."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def ocr_cache_root() -> Path:
    from app.config import get_settings

    return Path(get_settings().data_dir) / "ocr_cache"


def _key(barcode: str, engine: str, engine_version: str, page_fingerprints: list[str]) -> str:
    raw = "|".join([barcode, engine, engine_version, *page_fingerprints])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def page_fingerprint(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()[:16]


def cache_path(barcode: str, engine: str, key: str) -> Path:
    safe_engine = "".join(c if c.isalnum() or c in "-_" else "_" for c in engine)
    return ocr_cache_root() / barcode / safe_engine / f"{key}.json"


def load_disk_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_disk_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Do not store full page image bytes — text only.
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("ocr.cache.write path=%s chars=%d", path, len(payload.get("text") or ""))


def cache_key_for_pages(
    barcode: str,
    engine: str,
    engine_version: str,
    image_bytes_list: list[bytes],
) -> tuple[str, Path]:
    fps = [page_fingerprint(b) for b in image_bytes_list]
    key = _key(barcode, engine, engine_version, fps)
    return key, cache_path(barcode, engine, key)
