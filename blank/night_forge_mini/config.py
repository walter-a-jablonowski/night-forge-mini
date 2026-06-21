"""Config loading — infra only. The blank core is domain-agnostic, so this holds the
operator's per-deployment settings: provider/model, paths, the auto-run `allow_list`,
`recent_runs`, and connector params/creds. The domain *definition* (goal, metric,
connector impl, actions) lives in the pack, not here."""
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
    def allow_list(self) -> list[str]:
        """Operator policy: which actions may auto-run (gate also requires reversible)."""
        return list(self.raw.get("allow_list", []))

    @property
    def recent_runs(self) -> int:
        return int(self.raw.get("recent_runs", 5))

    @property
    def connector(self) -> dict[str, Any]:
        """Connector params/creds for the pack to wire its connector (e.g. source path)."""
        return self.raw.get("connector", {})

    def path(self, key: str) -> Path:
        return self.resolve(self.raw["paths"][key])

    def resolve(self, relpath: str | Path) -> Path:
        """Resolve a path relative to the config file's directory (the deploy root)."""
        return (self.root / relpath).resolve()

    def provider(self) -> dict[str, Any]:
        name = self.raw["provider"]
        p = dict(self.raw["providers"][name])
        p["name"] = name
        return p


def load(config_path: str | Path = "config.json") -> Config:
    cp = Path(config_path).resolve()
    raw = json.loads(cp.read_text(encoding="utf-8"))
    return Config(raw=raw, root=cp.parent)
