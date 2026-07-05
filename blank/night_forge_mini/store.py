"""Append-only JSONL artifact store = the single source of truth (idea_2).

Nothing is mutated or deleted. State (pending actions, the dedup watermark, the
current KB) is *derived* by querying this log.

Reads are cached per process: the file is parsed once, appends write through to the
cache, and a file-size check reloads when another process appended in the meantime —
so derived-state queries stay cheap while the log grows forever by design.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .records import Record, INPUT, ANALYSIS, PROPOSAL, DECISION, OUTCOME


class Store:
    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[Record] | None = None  # parsed cache; None = not loaded yet
        self._size = -1                            # file size the cache corresponds to
        self._warned: set[str] = set()             # lines already warned about (dedupe across reloads)

    def append(self, rec: Record) -> Record:
        # If a previous append was torn (crash mid-write leaves no trailing newline),
        # start on a fresh line so the torn tail can't merge into — and corrupt — this
        # record. The torn tail then stays self-contained and is skipped on read.
        prefix = "\n" if self._missing_trailing_newline() else ""
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(prefix + json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        self._size = self._file_size()
        if self._records is not None:
            self._records.append(rec)
        return rec

    def _missing_trailing_newline(self) -> bool:
        try:
            with self.log_path.open("rb") as f:
                f.seek(-1, 2)            # last byte; raises on empty/missing file
                return f.read(1) != b"\n"
        except (OSError, ValueError):
            return False                 # empty or missing -> nothing to separate from

    def _file_size(self) -> int:
        try:
            return self.log_path.stat().st_size
        except OSError:
            return 0

    def all(self) -> list[Record]:
        size = self._file_size()
        if self._records is None or size != self._size:  # first read, or external append
            self._records = self._load()
            self._size = size
        return list(self._records)

    def _load(self) -> list[Record]:
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
        """Dedup watermark, derived from past `input` records (no separate state store).
        Only runs that reached `analysis` count: an input captured by a run that then
        crashed (LLM down, bad JSON) was never processed, so its snippets must be
        re-fetched on the next run instead of being lost forever."""
        recs = self.all()
        completed = {r.run_id for r in recs if r.type == ANALYSIS}
        seen: set[str] = set()
        for r in recs:
            if (r.type == INPUT and r.run_id in completed
                    and r.payload.get("connector") == connector):
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

    # --- history for the next run (closing the loop) ------------------------

    def recent_findings(self, n: int) -> list[str]:
        return [r.payload.get("finding", "") for r in self.of_type(ANALYSIS)][-n:]

    def recent_metrics(self, n: int) -> list[dict]:
        """The last n measured metric values, oldest first — lets analyze see the trend."""
        vals = [r.payload.get("metric") for r in self.of_type(ANALYSIS)]
        return [m for m in vals if isinstance(m, dict) and m][-n:]

    def recent_rejections(self, n: int) -> list[dict]:
        """The last n human-rejected actions — the strongest teaching signal there is."""
        proposed = self.proposed_actions()
        out = []
        for r in self.of_type(DECISION):
            if r.payload.get("verdict") == "reject":
                a = proposed.get(r.parent_id, {}).get("action", {})
                out.append({"name": r.payload.get("name", ""),
                            "target": a.get("target", ""),
                            "rationale": a.get("rationale", "")})
        return out[-n:]

    def recent_failures(self, n: int) -> list[dict]:
        """The last n error outcomes, so the model stops repeating actions that fail."""
        proposed = self.proposed_actions()
        out = []
        for r in self.of_type(OUTCOME):
            if r.payload.get("status") == "error":
                a = proposed.get(r.parent_id, {}).get("action", {})
                out.append({"name": r.payload.get("name", ""),
                            "target": a.get("target", ""),
                            "detail": r.payload.get("detail", "")})
        return out[-n:]
