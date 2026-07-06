"""The core toolbox. Importing this package wires the built-in tools into `registry`.

Packs add their own tools in `build_pack(cfg)` via `registry.register(...)`.
See tasks/backlog/tool-registry.md for the design.
"""
from __future__ import annotations

from .registry import Registry, Tool, registry
from . import fetch_url as _fetch_url
from . import html_to_text as _html_to_text
from . import read_url as _read_url
from . import web_search as _web_search

# explicit wiring (no import-time magic inside the tool modules) — the whole built-in set
# is visible here in one place
registry.register(_fetch_url.TOOL)
registry.register(_html_to_text.TOOL)
registry.register(_read_url.TOOL)
registry.register(_web_search.TOOL)

__all__ = ["Tool", "Registry", "registry"]
