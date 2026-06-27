"""Built-in tool `html_to_text`: strip HTML to readable plain text via stdlib html.parser.

Drops script / style / head content, inserts line breaks at block boundaries, and collapses
blank lines. Good enough to feed page content to the model; a pack needing higher fidelity
can register a richer tool of its own.
"""
from __future__ import annotations

from html.parser import HTMLParser

from .registry import Tool

# tags whose text content we drop entirely
_SKIP = {"script", "style", "head", "noscript", "template"}

# tags that imply a line break around their content
_BLOCK = {"p", "div", "br", "li", "tr", "section", "article", "header", "footer",
          "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "blockquote", "pre"}


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # &amp; etc. arrive as text in handle_data
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCK:
            self._parts.append("\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag in _BLOCK:  # self-closing block, e.g. <br/>
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._skip:
            self._skip -= 1
        elif tag in _BLOCK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            self._parts.append(data)


def html_to_text(html: str) -> str:
    p = _Extractor()
    p.feed(html)
    p.close()
    lines = (ln.strip() for ln in "".join(p._parts).splitlines())
    return "\n".join(ln for ln in lines if ln)


TOOL = Tool(name="html_to_text",
            description="Strip HTML to readable plain text (stdlib html.parser).",
            run=html_to_text)
