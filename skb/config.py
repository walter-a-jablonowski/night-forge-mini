"""Config loading. The hardcoded domain (goal, metric, connector, allow-list, provider)
lives here as data — the core code stays domain-agnostic (idea_2 "goal+metric as data")."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Config:
    raw: dict[str, Any]
    root: Path

    @property
    def domain(self) -> str:
        return self.raw["domain"]

    @property
    def goal(self) -> str:
        return self.raw["goal"]

    @property
    def metric(self) -> str:
        return self.raw["metric"]

    @property
    def allow_list(self) -> list[str]:
        return list(self.raw.get("allow_list", []))

    @property
    def recent_runs(self) -> int:
        return int(self.raw.get("recent_runs", 5))

    def path(self, key: str) -> Path:
        return (self.root / self.raw["paths"][key]).resolve()

    @property
    def connector(self) -> dict[str, Any]:
        return self.raw["connector"]

    def provider(self) -> dict[str, Any]:
        name = self.raw["provider"]
        p = dict(self.raw["providers"][name])
        p["name"] = name
        return p


def load(config_path: str | Path = "config.json") -> Config:
    cp = Path(config_path).resolve()
    raw = json.loads(cp.read_text(encoding="utf-8"))
    return Config(raw=raw, root=cp.parent)
