"""Append-only JSONL artifact store = the single source of truth (idea_2).

Nothing is mutated or deleted. State (pending actions, the dedup watermark, the
current KB) is *derived* by querying this log.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .records import Record, PROPOSAL, DECISION, OUTCOME


class Store:
    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, rec: Record) -> Record:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        return rec

    def all(self) -> list[Record]:
        if not self.log_path.exists():
            return []
        out: list[Record] = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(Record.from_dict(json.loads(line)))
        return out

    def by_run(self, run_id: str) -> list[Record]:
        return [r for r in self.all() if r.run_id == run_id]

    def of_type(self, type_: str) -> list[Record]:
        return [r for r in self.all() if r.type == type_]

    # --- derived state -----------------------------------------------------

    def seen_snippet_ids(self, connector: str) -> set[str]:
        """Dedup watermark, derived from past `input` records (no separate state store)."""
        seen: set[str] = set()
        for r in self.all():
            if r.type == "input" and r.payload.get("connector") == connector:
                seen.update(r.payload.get("snippet_ids", []))
        return seen

    def proposed_actions(self) -> dict[str, dict]:
        """All actions ever proposed, by action_id -> {action, run_id}."""
        out: dict[str, dict] = {}
        for r in self.of_type(PROPOSAL):
            for a in r.payload.get("actions", []):
                out[a["action_id"]] = {"action": a, "run_id": r.run_id}
        return out

    def decided_action_ids(self) -> set[str]:
        return {r.parent_id for r in self.of_type(DECISION) if r.parent_id}

    def outcome_action_ids(self) -> set[str]:
        return {r.parent_id for r in self.of_type(OUTCOME) if r.parent_id}

    def pending_actions(self) -> list[dict]:
        """Actions proposed but not yet decided (idea_2: pending = proposal action w/o decision)."""
        decided = self.decided_action_ids()
        return [v for aid, v in self.proposed_actions().items() if aid not in decided]
