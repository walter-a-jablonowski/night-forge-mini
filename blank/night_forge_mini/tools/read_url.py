"""Built-in tool `read_url`: web page -> clean, LLM-ready markdown via Jina Reader.

Prepends `https://r.jina.ai/` to the target URL — Jina fetches and converts the page
(including JS-rendered ones) to markdown. The FREE tier needs no key, so this tool is
always available; an optional `JINA_API_KEY` in `.env` unlocks the paid tier's higher
rate limits (sent as a Bearer header when present).

Prefer this over `fetch_url` + `html_to_text` for page CONTENT: those return raw HTML /
a lossy stdlib strip; this returns readable markdown. `fetch_url` stays the right tool
for raw sources (APIs, feeds, files).
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

from .fetch_url import fetch_url as _fetch
from .registry import Tool


def read_url(url: str, *, timeout: float = 30.0) -> str:
    parsed = urlparse(str(url))
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"read_url: refusing non-http(s) URL: {url!r}")
    headers = {}
    key = os.environ.get("JINA_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return _fetch(f"https://r.jina.ai/{url}", timeout=timeout, headers=headers)


TOOL = Tool(name="read_url",
            description="Read a web page as clean markdown (Jina Reader; handles "
                        "JS-rendered pages). Prefer this for page content; use "
                        "fetch_url only for raw sources.",
            run=read_url,
            params={"type": "object",
                    "properties": {"url": {"type": "string",
                                           "description": "http(s) URL of the page to read"}},
                    "required": ["url"]})
