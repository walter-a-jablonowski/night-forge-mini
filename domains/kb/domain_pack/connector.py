"""The KB connector (idea_2 seam: `fetch() -> artifacts`).

`text-folder`: reads .md/.txt snippets from a folder. The dedup watermark is the set of
snippet ids already recorded in past `input` records (passed in by the loop).
"""
from __future__ import annotations

import hashlib
from pathlib import Path


class TextFolderConnector:
    name = "text-folder"

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
