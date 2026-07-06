"""Built-in tool `web_search`: one search tool, two providers (Tavily / Exa) behind it.

Keyed-but-core: search is domain-agnostic and both providers are a single stdlib REST
call, so it ships as a built-in; the `.env` key gates it (`available()` is False without
one) and the capability disables gracefully — the registry's design for keyed tools.

Provider selection (no config access at import time, so env-driven):
  - `WEB_SEARCH_PROVIDER=tavily|exa` forces one (its key must be set),
  - otherwise Tavily when `TAVILY_API_KEY` is set (its RAG-style results ship content
    snippets — the best default for "find content to work with"), else Exa
    (`EXA_API_KEY`, neural/semantic search).
Exactly ONE tool is exposed to the model — it should spend its steps searching, not
choosing between two near-identical search tools.
"""
from __future__ import annotations

import json
import os
import urllib.request

from .registry import Tool

_SNIPPET_MAX = 500  # chars per result fed back to the model


def _post_json(url: str, headers: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - fixed https URLs
        return json.loads(resp.read().decode("utf-8"))


def _tavily(query: str, n: int, timeout: float) -> list[dict]:
    data = _post_json("https://api.tavily.com/search",
                      {"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"},
                      {"query": query, "max_results": n}, timeout)
    return [{"title": r.get("title", ""), "url": r.get("url", ""),
             "snippet": r.get("content", "")} for r in data.get("results", [])]


def _exa(query: str, n: int, timeout: float) -> list[dict]:
    data = _post_json("https://api.exa.ai/search",
                      {"x-api-key": os.environ["EXA_API_KEY"]},
                      {"query": query, "numResults": n, "contents": {"text": True}}, timeout)
    return [{"title": r.get("title", ""), "url": r.get("url", ""),
             "snippet": r.get("text", "")} for r in data.get("results", [])]


_PROVIDERS = {"tavily": ("TAVILY_API_KEY", _tavily), "exa": ("EXA_API_KEY", _exa)}


def _pick_provider() -> str | None:
    forced = os.environ.get("WEB_SEARCH_PROVIDER", "").lower()
    if forced in _PROVIDERS and os.environ.get(_PROVIDERS[forced][0]):
        return forced
    for name, (key_env, _) in _PROVIDERS.items():  # dict order = preference: tavily first
        if os.environ.get(key_env):
            return name
    return None


def web_search(query: str, max_results: int = 5, *, timeout: float = 15.0) -> str:
    provider = _pick_provider()
    if provider is None:
        raise ValueError("web_search: no provider key set (TAVILY_API_KEY or EXA_API_KEY in .env)")
    n = max(1, min(int(max_results), 10))
    results = _PROVIDERS[provider][1](str(query), n, timeout)
    if not results:
        return f"no results for: {query}"
    return "\n\n".join(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet'][:_SNIPPET_MAX]}"
                       for i, r in enumerate(results, 1))


TOOL = Tool(name="web_search",
            description="Search the web; returns titles, URLs and content snippets. "
                        "Use fetch_url to read a promising result in full.",
            run=web_search,
            available_check=lambda: _pick_provider() is not None,
            params={"type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "web search query"},
                        "max_results": {"type": "integer",
                                        "description": "number of results (1-10, default 5)"},
                    },
                    "required": ["query"]})
