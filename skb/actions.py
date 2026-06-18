"""Action set for the KB domain. Each action is an object with `risk_level` +
`reversible` (idea_2 seam) and a `run`. The gate reads risk_level/reversible; the
markdown KB folder is the materialized artifact the actions write to.

Reversibility, honestly declared:
  add_entry / flag_contradiction / mark_stale  -> append-only-ish, reversible
  edit_entry                                    -> overwrites human-curated content => NOT reversible
                                                   (hard-floored: can never auto-run)
Actions are keyed by `target` (entry id) so re-running one is idempotent.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# name -> gate metadata
ACTIONS: dict[str, dict[str, Any]] = {
    "add_entry":          {"risk_level": "low",    "reversible": True},
    "flag_contradiction": {"risk_level": "low",    "reversible": True},
    "mark_stale":         {"risk_level": "low",    "reversible": True},
    "edit_entry":         {"risk_level": "medium", "reversible": False},
}


class KnowledgeBase:
    def __init__(self, kb_dir: Path):
        self.dir = Path(kb_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _file(self, entry_id: str) -> Path:
        return self.dir / f"{slug(entry_id)}.md"

    def exists(self, entry_id: str) -> bool:
        return self._file(entry_id).exists()

    def index(self) -> list[dict]:
        """Lightweight KB index for context: id + title + first line."""
        out = []
        for p in sorted(self.dir.glob("*.md")):
            text = p.read_text(encoding="utf-8")
            title = _frontmatter(text).get("title", p.stem)
            body = _body(text).strip().splitlines()
            out.append({"id": p.stem, "title": title, "preview": (body[0] if body else "")[:120]})
        return out

    def count(self) -> int:
        return len(list(self.dir.glob("*.md")))

    def stale_count(self) -> int:
        return sum(1 for p in self.dir.glob("*.md") if _frontmatter(p.read_text(encoding="utf-8")).get("stale") == "true")

    # --- action implementations -------------------------------------------

    def add_entry(self, target: str, payload: dict) -> dict:
        f = self._file(target)
        created = not f.exists()
        fm = {"title": payload.get("title", target), "id": slug(target),
              "source": payload.get("source", ""), "updated": _now()}
        f.write_text(_render(fm, payload.get("body", "")), encoding="utf-8")
        return {"status": "ok", "detail": ("created" if created else "overwrote") + f" {f.name}"}

    def edit_entry(self, target: str, payload: dict) -> dict:
        f = self._file(target)
        if not f.exists():
            return {"status": "error", "detail": f"no such entry {target}"}
        old = f.read_text(encoding="utf-8")
        fm = _frontmatter(old)
        fm["updated"] = _now()
        f.write_text(_render(fm, payload.get("body", _body(old))), encoding="utf-8")
        return {"status": "ok", "detail": f"edited {f.name}"}

    def flag_contradiction(self, target: str, payload: dict) -> dict:
        return self._annotate(target, f"> ⚠️ contradiction: {payload.get('note', '')}")

    def mark_stale(self, target: str, payload: dict) -> dict:
        f = self._file(target)
        if not f.exists():
            return {"status": "error", "detail": f"no such entry {target}"}
        old = f.read_text(encoding="utf-8")
        fm = _frontmatter(old)
        fm["stale"] = "true"
        fm["updated"] = _now()
        f.write_text(_render(fm, _body(old)), encoding="utf-8")
        return {"status": "ok", "detail": f"marked stale {f.name}"}

    def _annotate(self, target: str, note: str) -> dict:
        f = self._file(target)
        if not f.exists():
            return {"status": "error", "detail": f"no such entry {target}"}
        old = f.read_text(encoding="utf-8")
        f.write_text(old.rstrip() + "\n\n" + note + "\n", encoding="utf-8")
        return {"status": "ok", "detail": f"annotated {f.name}"}

    def run(self, name: str, target: str, payload: dict) -> dict:
        fn = getattr(self, name, None)
        if fn is None or name not in ACTIONS:
            return {"status": "error", "detail": f"unknown action {name}"}
        return fn(target, payload)


# --- tiny markdown frontmatter helpers (no external dep) -------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s.strip().lower()).strip("-")
    return s or "entry"


def _render(fm: dict, body: str) -> str:
    lines = ["---"] + [f"{k}: {v}" for k, v in fm.items()] + ["---", "", body.strip(), ""]
    return "\n".join(lines)


def _frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _body(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].strip()
    return text.strip()
