"""Action set for the KB domain. The markdown KB folder is the materialized artifact
the actions write to. Each action's gate metadata (`risk_level` + `reversible`) is honest;
`build_actions(kb)` adapts them to the core's `Action` shape.

Reversibility, honestly declared:
  add_entry / flag_contradiction / mark_stale  -> append-only-ish, reversible
  edit_entry                                    -> overwrites human-curated content => NOT reversible
                                                   (hard-floored by the gate: can never auto-run)
`add_entry` is **create-only**: it refuses to overwrite an existing entry (returns an
error). That refusal is what makes its `reversible: True` honest — overwriting curated
content is irreversible, so it must go through `edit_entry`, which needs approval. Without
this floor, an auto-run `add_entry` on an existing id would silently destroy curated
content, defeating the gate. Re-running add_entry on a *new* id is idempotent.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

from night_forge_mini.pack import Action

# name -> gate metadata
ACTIONS: dict[str, dict[str, Any]] = {
    "add_entry":          {"risk_level": "low",    "reversible": True},
    "flag_contradiction": {"risk_level": "low",    "reversible": True},
    "mark_stale":         {"risk_level": "low",    "reversible": True},
    "edit_entry":         {"risk_level": "medium", "reversible": False},
}


def build_actions(kb: "KnowledgeBase") -> dict[str, Action]:
    """Adapt the KB's actions to the core's `Action` interface (name -> Action)."""
    return {
        name: Action(name=name, risk_level=meta["risk_level"], reversible=meta["reversible"],
                     run=partial(kb.run, name))
        for name, meta in ACTIONS.items()
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

    def fingerprint(self, entry_id: str) -> str | None:
        """Hash of the entry's BODY (the part edit_entry overwrites); None if absent.
        Stamped on a proposed edit so the stale-edit guard can detect an intervening change."""
        f = self._file(entry_id)
        if not f.exists():
            return None
        return _hash(_body(f.read_text(encoding="utf-8")))

    # --- action implementations -------------------------------------------

    def add_entry(self, target: str, payload: dict) -> dict:
        f = self._file(target)
        if f.exists():
            # create-only: overwriting curated content is irreversible -> use edit_entry
            # (reversible=False => held for approval). Never silently overwrite on auto-run.
            return {"status": "error", "detail": f"entry {f.name} exists; use edit_entry"}
        fm = {"title": payload.get("title", target), "id": slug(target),
              "source": payload.get("source", ""), "updated": _now()}
        f.write_text(_render(fm, payload.get("body", "")), encoding="utf-8")
        return {"status": "ok", "detail": f"created {f.name}"}

    def edit_entry(self, target: str, payload: dict) -> dict:
        f = self._file(target)
        if not f.exists():
            return {"status": "error", "detail": f"no such entry {target}"}
        old = f.read_text(encoding="utf-8")
        # stale-edit guard (optimistic concurrency): if the body changed since this edit was
        # proposed, refuse instead of silently overwriting the intervening change (lost update).
        base = payload.get("base")
        if base is not None and base != _hash(_body(old)):
            return {"status": "error", "detail": f"{f.name} changed since proposed; re-run to re-propose"}
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


def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


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
