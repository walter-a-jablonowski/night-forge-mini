"""Append-only JSONL artifact store = the single source of truth (idea_2).

Nothing is mutated or deleted. State (pending actions, the dedup watermark, the
current KB) is *derived* by querying this log.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterator

from .records import Record, PROPOSAL, DECISION, OUTCOME


class Store:
    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._warned: set[str] = set()  # lines already warned about (dedupe across all() calls)

    def append(self, rec: Record) -> Record:
        # If a previous append was torn (crash mid-write leaves no trailing newline),
        # start on a fresh line so the torn tail can't merge into — and corrupt — this
        # record. The torn tail then stays self-contained and is skipped on read.
        prefix = "\n" if self._missing_trailing_newline() else ""
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(prefix + json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        return rec

    def _missing_trailing_newline(self) -> bool:
        try:
            with self.log_path.open("rb") as f:
                f.seek(-1, 2)            # last byte; raises on empty/missing file
                return f.read(1) != b"\n"
        except (OSError, ValueError):
            return False                 # empty or missing -> nothing to separate from

    def all(self) -> list[Record]:
        if not self.log_path.exists():
            return []
        out: list[Record] = []
        for n, line in enumerate(self.log_path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Record.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError) as e:
                # A torn final line (crash/disk-full mid-append) or a corrupt record must
                # not brick reads of the whole log — skip it so the system stays operable.
                # A partial append was never a committed record; dropping it is correct.
                # Warn (once per line) so it is never silently lost.
                if line not in self._warned:
                    self._warned.add(line)
                    print(f"night_forge_mini: skipping unreadable log line {n}: {e}", file=sys.stderr)
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
