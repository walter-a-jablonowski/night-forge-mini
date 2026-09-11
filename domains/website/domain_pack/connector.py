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
import re

from night_forge_mini.tools.read_url import read_url as _read_url

# Jina puts its own header before the page; the page itself follows this marker.
_BODY_MARKER = "Markdown Content:"
# a line that is only a markdown link (optionally as a bullet) — menu, not content
_LINK_LINE = re.compile(r'^[\s*\-]*(?:\[[^\]]*\]\([^)]*\)[\s,.*\-]*)+$')
_MIN_PROSE = 60          # chars of non-link text before a line counts as the article


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
            text = _strip_nav(text)
            sid = f"{url}#{_hash(text)}"
            if sid in seen_ids:
                continue
            out.append({"id": sid, "text": text[: self.snippet_max], "source": url})
        return out


def _strip_nav(md: str) -> str:
    """Drop the site furniture in front of the article.

    Capture is bounded, and the bound is spent from the START of what the reader returns.
    Measured live: Wikipedia's article text began at char 6,140 while `snippet_max` was
    4,000, so three captured pages handed the model nothing but menus — and because the
    watermark then marked those urls seen, their content could never be ingested at all.
    A bounded snippet is only useful if the bound is spent on content.

    Deliberately conservative: when nothing in the page looks like prose, the text is
    returned unchanged. An empty snippet would be worse than a menu."""
    head, _, body = md.partition(_BODY_MARKER)
    if not body:
        head, body = "", md

    lines = body.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or _LINK_LINE.match(stripped):
            continue
        # a line is the article once enough of it survives having its links removed
        if len(re.sub(r'\[[^\]]*\]\([^)]*\)', '', stripped)) >= _MIN_PROSE:
            return "\n".join(lines[i:]).strip()
    return md.strip()


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
