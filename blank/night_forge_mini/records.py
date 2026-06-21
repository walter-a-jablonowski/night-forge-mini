"""The single typed artifact record + the closed `type` enum (idea_2 "Artifact record").

One shape for every record; the hierarchy is a query (group by run_id), not nesting.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

from . import SCHEMA_V

# Closed enum for v1 — extend the enum, never the shape.
INPUT = "input"          # Capture:  fetched snippets + source cursor (dedup watermark)
ANALYSIS = "analysis"    # Analyze:  finding vs goal + the run's measured metric value
PROPOSAL = "proposal"    # Propose:  actions[] with risk_level + reversible
DECISION = "decision"    # Gate:     auto-run (allow-list + reversible) or human verdict
OUTCOME = "outcome"      # after an action runs: result / status ok|error
TYPES = {INPUT, ANALYSIS, PROPOSAL, DECISION, OUTCOME}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@dataclass
class Record:
    run_id: str
    domain: str
    type: str
    payload: dict[str, Any]
    parent_id: Optional[str] = None          # links a record to the action_id it concerns
    source: Optional[str] = None
    start_ts: Optional[str] = None           # span timing (e.g. the model call)
    end_ts: Optional[str] = None
    id: str = field(default_factory=lambda: new_id("rec"))
    ts: str = field(default_factory=now_iso)
    schema_v: int = SCHEMA_V

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Record":
        return Record(**d)
