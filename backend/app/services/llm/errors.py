"""Shared LLM errors raised to the API layer (never 500 with opaque text)."""

from __future__ import annotations


class LLMServiceError(Exception):
    """User-facing failure talking to a hosted LLM (timeout, HTTP, etc.)."""

    def __init__(self, message: str, *, code: str = "llm_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
