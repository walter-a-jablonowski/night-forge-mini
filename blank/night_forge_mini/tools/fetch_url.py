"""Built-in tool `fetch_url`: HTTP(S) GET -> decoded text, via stdlib urllib (zero deps).

Refuses non-http(s) schemes (so it can never read local files via `file://`) and caps the
body size, so a pack can fetch configured pages / search results without pulling in a
third-party HTTP client.
"""
from __future__ import annotations

import urllib.request
from urllib.parse import urlparse

from .registry import Tool

_USER_AGENT = "night_forge_mini/1.0 (+tools.fetch_url)"


def fetch_url(url: str, *, timeout: float = 10.0, max_bytes: int = 2_000_000) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"fetch_url: refusing non-http(s) URL: {url!r}")
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - scheme checked above
        raw = resp.read(max_bytes + 1)[:max_bytes]
        charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


TOOL = Tool(name="fetch_url",
            description="HTTP(S) GET a URL and return decoded text (stdlib urllib).",
            run=fetch_url)
