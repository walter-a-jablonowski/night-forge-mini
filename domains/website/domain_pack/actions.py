"""Action set for the website domain (phase 1). The site under data/site/ is the
materialized artifact the actions write to. Gate metadata is honest:

  create_page   -> create-only (refuses to overwrite) => reversible
  edit_content  -> overwrites a whole file            => NOT reversible
                   (auto-runs ONLY while git makes it recoverable — the pack's
                   git-backed-autonomy default; without healthy git it holds)

`create_page`'s refusal to overwrite is what keeps its `reversible: True` honest —
changing an existing file must go through `edit_content`, which the gate only lets
through when git supplies the undo. Brand/CI constraints are enforced SOFT in phase 1
(rendered into every prompt); hard refusal inside the actions is the phase-2 extension.

Phase 2 adds: change_layout / change_design, remove_page, add_asset.
"""
from __future__ import annotations

from typing import Any

from night_forge_mini.pack import Action

from .site import Site

# name -> gate metadata
ACTIONS: dict[str, dict[str, Any]] = {
    "create_page":  {"risk_level": "low",    "reversible": True},
    "edit_content": {"risk_level": "medium", "reversible": False},
}


def build_actions(site: Site) -> dict[str, Action]:
    """Adapt the Site's write methods to the core's `Action` interface (name -> Action)."""
    impl = {"create_page": site.create_page, "edit_content": site.edit_content}
    return {
        name: Action(name=name, risk_level=meta["risk_level"],
                     reversible=meta["reversible"], run=impl[name])
        for name, meta in ACTIONS.items()
    }
