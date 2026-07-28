"""Built-in tool `image_search`: find openly-licensed images via the Openverse API.

Keyless-and-core, the `read_url` case rather than the `web_search` one: Openverse's
search endpoint needs no credentials, so the tool is ALWAYS available (anonymous calls
are rate-limited, which is fine for a handful of lookups per run).

Why a tool and not "let the model name any image URL": a generic web image is not safe
to copy. The request is filtered to `license_type=commercial,modification` — only
licenses that permit commercial use AND modification come back — and every result
carries its license plus the attribution string the reuser must reproduce. A pack that
downloads one (e.g. the website pack's `add_asset`) can therefore record provenance
instead of guessing it.

Returns the image's DIRECT url (what you download) and its `source` landing page (what
you link in an attribution/credits line) — they are different URLs and both matter.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .registry import Tool

_ENDPOINT = "https://api.openverse.org/v1/images/"
_USER_AGENT = "night_forge_mini/1.0 (+tools.image_search)"

# only licenses permitting commercial use AND modification — mirrors the API filter, and
# is the set a pack may accept as proof of "safe to copy" (see `add_asset`)
OPEN_LICENSES = {"by", "by-sa", "cc0", "pdm"}


def _get_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - fixed https endpoint
        return json.loads(resp.read().decode("utf-8"))


def _license_label(r: dict) -> str:
    lic = str(r.get("license", "")).lower()
    version = str(r.get("license_version", "")).strip()
    return f"{lic} {version}".strip() if lic else "unknown"


def _attribution(r: dict) -> str:
    """Openverse ships a ready-made attribution sentence; fall back to building one."""
    text = str(r.get("attribution", "")).strip()
    if text:
        return " ".join(text.split())          # it arrives with newlines in it
    title = r.get("title") or "Untitled"
    creator = r.get("creator") or "unknown creator"
    return f'"{title}" by {creator} is licensed under {_license_label(r).upper()}.'


def image_search(query: str, max_results: int = 5, *, timeout: float = 15.0) -> str:
    n = max(1, min(int(max_results), 10))
    params = urllib.parse.urlencode({"q": str(query), "page_size": n,
                                     "license_type": "commercial,modification"})
    data = _get_json(f"{_ENDPOINT}?{params}", timeout)
    results = data.get("results", [])
    if not results:
        return f"no openly-licensed images for: {query}"

    blocks = []
    for i, r in enumerate(results, 1):
        blocks.append(
            f"{i}. {r.get('title') or '(untitled)'}\n"
            f"   url:         {r.get('url', '')}\n"
            f"   license:     {_license_label(r)}\n"
            f"   creator:     {r.get('creator') or 'unknown'}\n"
            f"   source:      {r.get('foreign_landing_url', '')}\n"
            f"   attribution: {_attribution(r)}")
    return "\n\n".join(blocks)


TOOL = Tool(name="image_search",
            description="Search for openly-licensed images (Openverse; commercial use + "
                        "modification allowed). Returns each image's direct url, license, "
                        "creator, source page and the attribution line to reproduce. Use "
                        "these fields verbatim when proposing an image download.",
            run=image_search,
            params={"type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "what the image should show"},
                        "max_results": {"type": "integer",
                                        "description": "number of results (1-10, default 5)"},
                    },
                    "required": ["query"]})
