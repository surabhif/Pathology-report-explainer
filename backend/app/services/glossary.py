"""Glossary helpers for plain-language pathology terms."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings


@lru_cache
def load_glossary() -> dict[str, Any]:
    path: Path = get_settings().config_dir / "glossary.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def define(term: str) -> str | None:
    glossary = load_glossary()
    key = term.strip().lower()
    for entry in glossary.get("terms", []):
        if entry.get("term", "").lower() == key or key in [a.lower() for a in entry.get("aliases", [])]:
            return entry.get("definition")
    return None


def simplify_phrase(text: str) -> str:
    """Replace known glossary terms with short plain-language hints in parentheses."""
    glossary = load_glossary()
    out = text
    for entry in glossary.get("terms", []):
        term = entry.get("term", "")
        short = entry.get("short", entry.get("definition", ""))
        if term and term in out and short:
            out = out.replace(term, f"{term} ({short})", 1)
    return out
