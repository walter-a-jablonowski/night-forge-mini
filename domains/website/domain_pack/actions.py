"""Action set for the website domain. The site under data/site/ is the materialized
artifact the actions write to. Gate metadata is honest — `reversible` says what the
action does to the filesystem, not how recoverable the operator's setup makes it:

  create_page   -> create-only (refuses to overwrite)      => reversible
  add_asset     -> create-only download into assets/       => reversible
  edit_content  -> overwrites a page file                  => NOT reversible
  change_design -> writes a stylesheet                     => NOT reversible
  remove_page   -> deletes a page file                     => NOT reversible

The three irreversible ones auto-run ONLY while git makes them recoverable (the pack's
git-backed-autonomy default: enabled + per_action + clean repo); without healthy git the
gate holds them for approval. `create_page`/`add_asset` refusing to overwrite is what
keeps their `reversible: True` honest — changing an existing file must go through the
action git is watching.

`change_design` is a separate action from `edit_content` rather than "an edit that
happens to target .css": it gives design changes their own identity in the log and their
own line in the allow_list, so an operator can let the site rewrite its content while
holding restyles for review (or the reverse). The write policies genuinely differ too —
create-or-overwrite vs. must-exist, CSS constraints vs. page constraints.

Brand/CI constraints are enforced in BOTH layers: soft (rendered into every prompt) and
hard (refused inside the write, see constraints.py).
"""
from __future__ import annotations

from typing import Any

from night_forge_mini.pack import Action

from .site import Site

# name -> gate metadata
ACTIONS: dict[str, dict[str, Any]] = {
    "create_page":   {"risk_level": "low",    "reversible": True},
    "add_asset":     {"risk_level": "low",    "reversible": True},
    "edit_content":  {"risk_level": "medium", "reversible": False},
    "change_design": {"risk_level": "medium", "reversible": False},
    "remove_page":   {"risk_level": "high",   "reversible": False},
}


def build_actions(site: Site) -> dict[str, Action]:
    """Adapt the Site's write methods to the core's `Action` interface (name -> Action)."""
    impl = {"create_page": site.create_page, "add_asset": site.add_asset,
            "edit_content": site.edit_content, "change_design": site.change_design,
            "remove_page": site.remove_page}
    return {
        name: Action(name=name, risk_level=meta["risk_level"],
                     reversible=meta["reversible"], run=impl[name])
        for name, meta in ACTIONS.items()
    }
