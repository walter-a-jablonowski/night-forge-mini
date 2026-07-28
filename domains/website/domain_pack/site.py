"""The Site — the pack's file API over the materialized website under data/site/
(the KB pack's `KnowledgeBase` analogue). Read side serves analyze (site map,
`read_page` tool) and the metric modules; write side holds the action implementations.

Path safety: every model-supplied target passes `safe_path` — relative only, no `..`,
no drive letters / NTFS streams (`:`), extension whitelisted, and the resolved result
must stay inside the site dir — so a proposed action can never touch anything outside.
The pack treats site files as TEXT and never executes them, which is why `.php` pages
work exactly like `.html` ones (site-shape decision 2026-07-11).

Binary assets are the one exception to "text": they live under `assets/`, are listed
separately from the text files (`assets()` vs `files()`) and are never read into the
model's context — only their paths are.

Content policy (brand/CI invariants, licensing of downloads) is NOT here: the Site owns
paths and bytes, `constraints.HardConstraints` and `assets.AssetPolicy` own what is
acceptable. The write methods consult them; neither needs the filesystem to be tested.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath

from night_forge_mini.tools.fetch_binary import fetch_binary

from .assets import AssetPolicy, sidecar_text
from .constraints import HardConstraints

# what a site TEXT file may be — .php explicitly included (custom PHP sites)
ALLOWED = {".html", ".htm", ".php", ".css", ".js", ".txt", ".xml", ".svg"}
PAGES = {".html", ".htm", ".php"}
STYLES = {".css"}
# downloadable assets; .svg is both text and image, so it appears here and in ALLOWED
ASSETS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".ico", ".svg"}

ASSET_DIR = "assets"
HOME = "index.html"          # removing the site root is never a sane proposal

_TITLE = re.compile(r"<title[^>]*>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)


class Site:
    def __init__(self, site_dir: Path, hard: HardConstraints | None = None,
                 asset_policy: AssetPolicy | None = None):
        self.dir = Path(site_dir).resolve()
        self.dir.mkdir(parents=True, exist_ok=True)
        # permissive defaults keep the Site usable (and testable) without any config
        self.hard = hard or HardConstraints()
        self.asset_policy = asset_policy or AssetPolicy()

    # --- path safety --------------------------------------------------------

    def safe_path(self, target: str, allow: set[str] = ALLOWED) -> Path | None:
        """Resolve a model-supplied relative path to a file inside the site dir;
        None when it is unsafe (absolute/escaping/`:`/disallowed extension). `allow`
        narrows the extension whitelist per action (e.g. STYLES for change_design)."""
        t = str(target).strip().replace("\\", "/").lstrip("/")
        pp = PurePosixPath(t)
        if not t or ":" in t or ".." in pp.parts or pp.suffix.lower() not in allow:
            return None
        f = (self.dir / t).resolve()
        return f if f.is_relative_to(self.dir) else None

    def rel(self, f: Path) -> str:
        return f.relative_to(self.dir).as_posix()

    # --- read side (analyze context, read_page tool, metrics) ----------------

    def _walk(self, suffixes: set[str]) -> list[str]:
        out = []
        for p in self.dir.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in suffixes:
                continue
            r = p.relative_to(self.dir)
            if ".git" in r.parts:
                continue
            out.append(r.as_posix())
        return sorted(out)

    def files(self) -> list[str]:
        """All site TEXT files (relative posix paths), .git and non-site files excluded."""
        return self._walk(ALLOWED)

    def pages(self) -> list[str]:
        return [f for f in self.files() if PurePosixPath(f).suffix.lower() in PAGES]

    def assets(self) -> list[str]:
        """Downloaded assets — listed for the model by PATH only, never read as content."""
        return [f for f in self._walk(ASSETS) if f.startswith(f"{ASSET_DIR}/")]

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
        edit_content / change_design so the stale-edit guard can detect an intervening
        change."""
        f = self.safe_path(target)
        if f is None or not f.is_file():
            return None
        return _hash(f.read_text(encoding="utf-8"))

    # --- write side (the action implementations) -----------------------------

    @staticmethod
    def _content(payload: dict) -> str | None:
        content = str(payload.get("content", ""))
        return content if content.strip() else None

    @staticmethod
    def _stale(f: Path, payload: dict) -> bool:
        """Optimistic concurrency: the proposal stamped the content hash it was written
        against; a mismatch means someone changed the file in between."""
        base = payload.get("base")
        return base is not None and base != _hash(f.read_text(encoding="utf-8"))

    def create_page(self, target: str, payload: dict) -> dict:
        f = self.safe_path(target)
        if f is None:
            return {"status": "error", "detail": f"invalid path {target!r}"}
        if f.exists():
            # create-only: overwriting is irreversible -> must go through edit_content
            # (held unless git makes it recoverable). Never silently overwrite.
            return {"status": "error", "detail": f"{self.rel(f)} exists; use edit_content"}
        content = self._content(payload)
        if content is None:
            return {"status": "error", "detail": "empty content"}
        reason = self.hard.check_page(content)
        if reason:
            return {"status": "error", "detail": f"refused: {reason}"}
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return {"status": "ok", "detail": f"created {self.rel(f)}"}

    def edit_content(self, target: str, payload: dict) -> dict:
        f = self.safe_path(target)
        if f is None:
            return {"status": "error", "detail": f"invalid path {target!r}"}
        if not f.is_file():
            return {"status": "error", "detail": f"no such page {target!r}; use create_page"}
        content = self._content(payload)
        if content is None:
            return {"status": "error", "detail": "empty content"}
        if self._stale(f, payload):
            return {"status": "error",
                    "detail": f"{self.rel(f)} changed since proposed; re-run to re-propose"}
        reason = self.hard.check_page(content, previous=f.read_text(encoding="utf-8"))
        if reason:
            return {"status": "error", "detail": f"refused: {reason}"}
        f.write_text(content, encoding="utf-8")
        return {"status": "ok", "detail": f"edited {self.rel(f)}"}

    def change_design(self, target: str, payload: dict) -> dict:
        """Stylesheets only — the design dimension of the site, separated from content so
        an operator can allow-list the two independently. Create-or-overwrite: a new
        stylesheet is as normal a design change as editing the existing one."""
        f = self.safe_path(target, allow=STYLES)
        if f is None:
            return {"status": "error", "detail": f"invalid stylesheet path {target!r} (.css only)"}
        content = self._content(payload)
        if content is None:
            return {"status": "error", "detail": "empty content"}
        if f.is_file() and self._stale(f, payload):
            return {"status": "error",
                    "detail": f"{self.rel(f)} changed since proposed; re-run to re-propose"}
        reason = self.hard.check_css(content)
        if reason:
            return {"status": "error", "detail": f"refused: {reason}"}
        verb = "restyled" if f.is_file() else "created"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return {"status": "ok", "detail": f"{verb} {self.rel(f)}"}

    def remove_page(self, target: str, payload: dict) -> dict:
        """Delete one page. Pages only (a stylesheet is replaced via change_design, not
        deleted) and never the home page, whose loss would break the whole site — the
        one thing git-revert-ability does not make cheap enough to risk."""
        f = self.safe_path(target, allow=PAGES)
        if f is None:
            return {"status": "error", "detail": f"invalid page path {target!r}"}
        if not f.is_file():
            return {"status": "error", "detail": f"no such page {target!r}"}
        if self.rel(f) == HOME:
            return {"status": "error", "detail": f"refusing to remove the home page {HOME}"}
        f.unlink()
        return {"status": "ok", "detail": f"removed {self.rel(f)}"}

    def add_asset(self, target: str, payload: dict) -> dict:
        """Download one image/file into assets/. Create-only, so it stays honestly
        reversible; the licensing ladder (AssetPolicy) decides whether the source is
        usable at all, and the attribution is written to a sidecar beside the file."""
        f = self.safe_path(target, allow=ASSETS)
        if f is None:
            return {"status": "error", "detail": f"invalid asset path {target!r}"}
        if not self.rel(f).startswith(f"{ASSET_DIR}/"):
            return {"status": "error", "detail": f"assets must live under {ASSET_DIR}/"}
        if f.exists():
            return {"status": "error", "detail": f"{self.rel(f)} exists; assets are create-only"}
        url = str(payload.get("url", "")).strip()
        if not url:
            return {"status": "error", "detail": "no url given"}
        reason = self.asset_policy.check(url, payload)
        if reason:
            return {"status": "error", "detail": f"refused: {reason}"}
        try:
            raw = fetch_binary(url, max_bytes=self.asset_policy.max_bytes)
        except Exception as e:  # noqa: BLE001 - a failed download is a normal outcome
            return {"status": "error", "detail": f"download failed: {type(e).__name__}: {e}"}
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(raw)
        sidecar = f.parent / f"{f.name}.license.txt"
        sidecar.write_text(sidecar_text(url, payload), encoding="utf-8")
        return {"status": "ok", "detail": f"added {self.rel(f)} ({len(raw)} bytes)"}


def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s.strip().lower()).strip("-")
    return s or "page"
