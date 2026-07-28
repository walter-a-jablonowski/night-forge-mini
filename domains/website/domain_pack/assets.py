"""Asset provenance policy — the licensing ladder for `add_asset` (phase 2).

A generic web image is NOT safe to copy, so a download has to justify its source. Two
rungs are accepted, in the spec's preference order:

  1. operator-provided — the URL's host is in the deploy config's `assets.allowed_hosts`
     (the operator's own CDN, their logo host, ...). Always safe: the operator vouches.
  2. openly-licensed — the payload carries a license from `OPEN_LICENSES` (commercial use
     AND modification permitted), i.e. what the core `image_search` tool returns. The
     attribution the license demands is written next to the file as a sidecar.

Anything else is refused. Rung 3 of the spec's ladder (hotlinking an external image
instead of downloading it) is not a download at all — it is enforced on the page source
by `HardConstraints.check_page`, default off.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from night_forge_mini.tools.image_search import OPEN_LICENSES


class AssetPolicy:
    """Decides whether a proposed download may happen, and records why it was allowed."""

    def __init__(self, allowed_hosts: list[str] | None = None, max_bytes: int = 5_000_000):
        self.allowed_hosts = [str(h).strip().lower() for h in (allowed_hosts or [])
                              if str(h).strip()]
        self.max_bytes = int(max_bytes)

    @classmethod
    def from_config(cls, raw: Any) -> AssetPolicy:
        cfg = raw if isinstance(raw, dict) else {}
        return cls(allowed_hosts=cfg.get("allowed_hosts"),
                   max_bytes=int(cfg.get("max_bytes", 5_000_000)))

    def host_allowed(self, url: str) -> bool:
        host = (urlparse(str(url)).hostname or "").lower()
        # a listed host also covers its subdomains (cdn.example.org matches example.org)
        return any(host == h or host.endswith(f".{h}") for h in self.allowed_hosts)

    def check(self, url: str, payload: dict) -> str | None:
        """None when the download is permitted, else the reason to refuse it."""
        if urlparse(str(url)).scheme not in ("http", "https"):
            return f"url must be http(s): {url!r}"
        if self.host_allowed(url):
            return None
        license_id = str(payload.get("license", "")).strip().lower()
        if not license_id:
            return ("no license given and the host is not operator-approved - use "
                    "image_search and pass its license/creator/source fields, or add the "
                    "host to assets.allowed_hosts")
        # image_search labels look like "by-sa 4.0"; the license id is the first word
        if license_id.split()[0] not in OPEN_LICENSES:
            return (f"license {license_id!r} does not permit commercial use and "
                    f"modification (accepted: {', '.join(sorted(OPEN_LICENSES))})")
        return None


def sidecar_text(url: str, payload: dict) -> str:
    """Attribution record stored next to a downloaded asset (`<name>.license.txt`), so
    provenance lives with the file and is versioned by git along with it."""
    lines = [f"source_url:  {url}"]
    for key in ("license", "creator", "source", "attribution"):
        value = str(payload.get(key, "")).strip()
        if value:
            lines.append(f"{key + ':':12} {value}")
    return "\n".join(lines) + "\n"
