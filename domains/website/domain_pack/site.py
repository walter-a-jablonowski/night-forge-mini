"""The Site — the pack's file API over the materialized website under data/site/
(the KB pack's `KnowledgeBase` analogue). Read side serves analyze (site map,
`read_page` tool) and the metric modules; write side holds the action implementations.

Path safety: every model-supplied target passes `safe_path` — relative only, no `..`,
no drive letters / NTFS streams (`:`), extension whitelisted, and the resolved result
must stay inside the site dir — so a proposed action can never touch anything outside.
The pack treats site files as TEXT and never executes them, which is why `.php` pages
work exactly like `.html` ones (site-shape decision 2026-07-11).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath

# what a site file may be — .php explicitly included (custom PHP sites)
ALLOWED = {".html", ".htm", ".php", ".css", ".js", ".txt", ".xml", ".svg"}
PAGES = {".html", ".htm", ".php"}

_TITLE = re.compile(r"<title[^>]*>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)


class Site:
    def __init__(self, site_dir: Path):
        self.dir = Path(site_dir).resolve()
        self.dir.mkdir(parents=True, exist_ok=True)

    # --- path safety --------------------------------------------------------

    def safe_path(self, target: str) -> Path | None:
        """Resolve a model-supplied relative path to a file inside the site dir;
        None when it is unsafe (absolute/escaping/`:`/disallowed extension)."""
        t = str(target).strip().replace("\\", "/").lstrip("/")
        pp = PurePosixPath(t)
        if not t or ":" in t or ".." in pp.parts or pp.suffix.lower() not in ALLOWED:
            return None
        f = (self.dir / t).resolve()
        return f if f.is_relative_to(self.dir) else None

    def rel(self, f: Path) -> str:
        return f.relative_to(self.dir).as_posix()

    # --- read side (analyze context, read_page tool, metrics) ----------------

    def files(self) -> list[str]:
        """All site files (relative posix paths), .git and non-site files excluded."""
        out = []
        for p in self.dir.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in ALLOWED:
                continue
            r = p.relative_to(self.dir)
            if ".git" in r.parts:
                continue
            out.append(r.as_posix())
        return sorted(out)

    def pages(self) -> list[str]:
        return [f for f in self.files() if PurePosixPath(f).suffix.lower() in PAGES]

    def has_file(self, relpath: str) -> bool:
        """Existence check for link targets (ANY extension — images too); read-only,
        so it deliberately skips `safe_path`'s extension policy."""
        t = str(relpath).replace("\\", "/").lstrip("/")
        if not t or ":" in t or ".." in PurePosixPath(t).parts:
            return False
        return (self.dir / t).is_file()

    def exists(self, target: str) -> bool:
        f = self.safe_path(target)
        return bool(f and f.is_file())

    def read(self, target: str) -> str:
        """Full source of one site file — the read_page tool for the agentic analyze."""
        f = self.safe_path(target)
        if f is None:
            return f"error: invalid path {target!r}"
        if not f.is_file():
            return f"error: no such page {target!r}"
        return f.read_text(encoding="utf-8")

    def site_map(self) -> list[dict]:
        """Lightweight map for context: path + <title> + size (chars)."""
        out = []
        for rel in self.files():
            text = (self.dir / rel).read_text(encoding="utf-8")
            m = _TITLE.search(text) if PurePosixPath(rel).suffix.lower() in PAGES else None
            out.append({"path": rel, "title": (m.group(1)[:80] if m else ""),
                        "size": len(text)})
        return out

    def fingerprint(self, target: str) -> str | None:
        """Hash of a file's current content; None if absent. Stamped on a proposed
        edit_content so the stale-edit guard can detect an intervening change."""
        f = self.safe_path(target)
        if f is None or not f.is_file():
            return None
        return _hash(f.read_text(encoding="utf-8"))

    # --- write side (the action implementations) -----------------------------

    def create_page(self, target: str, payload: dict) -> dict:
        f = self.safe_path(target)
        if f is None:
            return {"status": "error", "detail": f"invalid path {target!r}"}
        if f.exists():
            # create-only: overwriting is irreversible -> must go through edit_content
            # (held unless git makes it recoverable). Never silently overwrite.
            return {"status": "error", "detail": f"{self.rel(f)} exists; use edit_content"}
        content = str(payload.get("content", ""))
        if not content.strip():
            return {"status": "error", "detail": "empty content"}
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return {"status": "ok", "detail": f"created {self.rel(f)}"}

    def edit_content(self, target: str, payload: dict) -> dict:
        f = self.safe_path(target)
        if f is None:
            return {"status": "error", "detail": f"invalid path {target!r}"}
        if not f.is_file():
            return {"status": "error", "detail": f"no such page {target!r}; use create_page"}
        content = str(payload.get("content", ""))
        if not content.strip():
            return {"status": "error", "detail": "empty content"}
        # stale-edit guard (optimistic concurrency): if the file changed since this edit
        # was proposed, refuse instead of silently overwriting the intervening change.
        base = payload.get("base")
        if base is not None and base != _hash(f.read_text(encoding="utf-8")):
            return {"status": "error",
                    "detail": f"{self.rel(f)} changed since proposed; re-run to re-propose"}
        f.write_text(content, encoding="utf-8")
        return {"status": "ok", "detail": f"edited {self.rel(f)}"}


def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s.strip().lower()).strip("-")
    return s or "page"
