"""Rate-limit client identity helpers.

Behind Render (or any reverse proxy), ``request.client.host`` is the proxy.
Only trust ``X-Forwarded-For`` / ``X-Real-IP`` when ``TRUST_PROXY_HEADERS=true``.
"""

from __future__ import annotations

from fastapi import Request

from app.config import get_settings


def client_ip_key(request: Request) -> str:
    """Return a stable rate-limit key for the apparent client."""
    settings = get_settings()
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # First hop is the original client when proxies append left-to-right.
            return forwarded.split(",")[0].strip() or "unknown"
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
