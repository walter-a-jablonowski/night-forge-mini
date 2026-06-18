"""Connector interface + the one v1 connector (idea_2 seam: `fetch() -> artifacts`).

`text-folder`: reads .md/.txt snippets from a folder. Dedup watermark is the set of
snippet ids already recorded in past `input` records (passed in by the loop).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol


class Connector(Protocol):
    name: str

    def fetch(self, seen_ids: set[str]) -> list[dict]:
        """Return new artifacts not in seen_ids. Each: {id, text, source}."""
        ...


class TextFolderConnector:
    def __init__(self, name: str, source: Path):
        self.name = name
        self.source = Path(source)

    def fetch(self, seen_ids: set[str]) -> list[dict]:
        if not self.source.exists():
            return []
        out: list[dict] = []
        for p in sorted(self.source.iterdir()):
            if p.suffix.lower() not in {".md", ".txt"} or not p.is_file():
                continue
            text = p.read_text(encoding="utf-8").strip()
            sid = _snippet_id(p.name, text)
            if sid in seen_ids:
                continue
            out.append({"id": sid, "text": text, "source": str(p.name)})
        return out


def _snippet_id(name: str, text: str) -> str:
    h = hashlib.sha1(f"{name}:{text}".encode("utf-8")).hexdigest()[:8]
    return f"snip-{h}"


def build(connector_cfg: dict, inbox_path: Path) -> Connector:
    if connector_cfg["name"] == "text-folder":
        return TextFolderConnector("text-folder", inbox_path)
    raise ValueError(f"unknown connector: {connector_cfg['name']}")
