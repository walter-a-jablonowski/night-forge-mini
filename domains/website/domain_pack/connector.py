"""The website connector `web-source` — scheduled *capture* of external content.

`pages` mode: a fixed URL list from config; each URL is read via the core `read_url`
tool (Jina Reader -> clean markdown). Snippet id = `url#<hash of the markdown>`, so a
changed page gets a new id and re-ingests through the normal seen_ids watermark, and
an unchanged page is skipped — no special re-fetch mechanism.

Capture is bounded (`snippet_max`): the model can read any page IN FULL on demand via
the `read_url` tool during analyze — capture only has to say "something is here".
Failures are non-fatal: an unreachable URL is skipped this run and retried next run.

`search` mode is deferred (phase 3): model-driven `web_search` during analyze covers
discovery for now.
"""
from __future__ import annotations

import hashlib

from night_forge_mini.tools.read_url import read_url as _read_url


class WebSourceConnector:
    name = "web-source"

    def __init__(self, pages: list[str], snippet_max: int = 4000):
        self.pages = [str(u) for u in pages]
        self.snippet_max = int(snippet_max)

    def fetch(self, seen_ids: set[str]) -> list[dict]:
        out: list[dict] = []
        for url in self.pages:
            try:
                text = _read_url(url).strip()
            except Exception:  # noqa: BLE001 - skip this run, retry next run
                continue
            sid = f"{url}#{_hash(text)}"
            if sid in seen_ids:
                continue
            out.append({"id": sid, "text": text[: self.snippet_max], "source": url})
        return out


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
