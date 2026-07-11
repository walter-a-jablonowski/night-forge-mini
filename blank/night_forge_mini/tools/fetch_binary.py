"""Built-in tool `fetch_binary`: HTTP(S) GET -> raw bytes, via stdlib urllib (zero deps).

The binary-safe sibling of `fetch_url` (which decodes text): same non-http(s) scheme refusal
and body size cap, but the body is returned unmodified — for downloading images/assets a
pack writes to disk (e.g. the website pack's `add_asset`). Two deliberate differences:
- oversize bodies RAISE instead of truncating (a truncated image is silent corruption),
- no `params` schema — bytes are not model-consumable, so this tool is never exposed to
  the model via `run_tools`; it is called by pack code only.
"""
from __future__ import annotations

import urllib.request
from urllib.parse import urlparse

from .registry import Tool

_USER_AGENT = "night_forge_mini/1.0 (+tools.fetch_binary)"


def fetch_binary(url: str, *, timeout: float = 10.0, max_bytes: int = 10_000_000) -> bytes:
    # default cap is larger than fetch_url's: assets (images) run bigger than text pages
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"fetch_binary: refusing non-http(s) URL: {url!r}")
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - scheme checked above
        raw = resp.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError(f"fetch_binary: body exceeds max_bytes={max_bytes}: {url!r}")
    return raw


TOOL = Tool(name="fetch_binary",
            description="HTTP(S) GET a URL and return raw bytes (assets; not model-exposed).",
            run=fetch_binary)
