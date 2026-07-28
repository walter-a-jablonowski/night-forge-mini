"""Website domain pack — a self-improving website developed toward a config-defined goal.

The single entry point the blank core looks for: `build_pack(cfg) -> Pack`. Unlike the
KB pack (whose goal is a constant), the goal, the brand/CI constraints and the active
metrics all come from the deploy's config.json — this pack is the mechanism, the
operator supplies the objective. The site under data/site/ is the materialized
artifact; git (per_action) is what lets the honestly-irreversible edit_content
auto-run (git-backed autonomy — see tasks/backlog/website-domain-pack.md).
"""
from __future__ import annotations

from night_forge_mini.config import Config
from night_forge_mini.pack import Pack

from . import analyze as analyze_mod
from . import metrics as metrics_mod
from .actions import build_actions
from .assets import AssetPolicy
from .connector import WebSourceConnector
from .constraints import HardConstraints
from .site import Site

DOMAIN = "website"
DEFAULT_METRICS = ["pages", "broken_links", "seo_basics", "goal_coverage"]


def build_pack(cfg: Config) -> Pack:
    goal = str(cfg.get("site_goal") or "").strip()
    if not goal:
        raise ValueError("config: site_goal is required — the website pack's goal is "
                         "operator data, not pack code")
    constraints = _text(cfg.get("constraints", ""))

    # constraints are enforced twice: `constraints` (free text) goes into every prompt,
    # `hard_constraints` (structured) is refused inside the write actions
    site = Site(cfg.path("site"),
                hard=HardConstraints.from_config(cfg.get("hard_constraints")),
                asset_policy=AssetPolicy.from_config(cfg.get("assets")))

    conn = cfg.connector
    mode = conn.get("mode", "pages")
    if mode != "pages":
        raise ValueError(f"config: connector mode {mode!r} not supported yet (phase 1: pages)")
    connector = WebSourceConnector(list(conn.get("pages", [])),
                                   snippet_max=int(conn.get("snippet_max", 4000)))

    metric_mods = metrics_mod.load(list(cfg.get("metrics", DEFAULT_METRICS)))
    map_max = int(cfg.get("site_map_max", 50))    # bound the site map fed to the model
    tool_steps = int(cfg.get("analyze_tool_steps", 8))  # agentic read budget; 0 = one-shot

    def analyze(model, *, goal, snippets, history):
        return analyze_mod.analyze(model, site=site, goal=goal, constraints=constraints,
                                   snippets=snippets, history=history,
                                   metric_mods=metric_mods, map_max=map_max,
                                   tool_steps=tool_steps)

    return Pack(domain=DOMAIN, goal=goal, connector=connector,
                actions=build_actions(site), analyze=analyze)


def _text(v) -> str:
    """Config convenience: constraints may be a string or a list of lines."""
    if isinstance(v, (list, tuple)):
        return "\n".join(f"- {x}" for x in v)
    return str(v or "")
