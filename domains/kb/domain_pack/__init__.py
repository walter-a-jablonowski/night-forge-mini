"""KB domain pack — curating a knowledge base from incoming text snippets.

The single entry point the blank core looks for: `build_pack(cfg) -> Pack`. Everything
domain-specific (goal, the connector, the analysis strategy + its metric, the actions)
is wired here; the core stays domain-agnostic.
"""
from __future__ import annotations

from night_forge_mini.config import Config
from night_forge_mini.pack import Pack

from . import analyze as analyze_mod
from .actions import KnowledgeBase, build_actions
from .connector import TextFolderConnector

DOMAIN = "knowledge-base"
GOAL = "Maintain a complete, non-redundant, current knowledge base from incoming text snippets."


def build_pack(cfg: Config) -> Pack:
    kb = KnowledgeBase(cfg.path("kb"))
    source = cfg.resolve(cfg.connector.get("source", "data/inbox"))
    connector = TextFolderConnector("text-folder", source)
    actions = build_actions(kb)

    def analyze(model, *, goal, snippets, recent_findings):
        return analyze_mod.analyze(model, kb=kb, goal=goal,
                                   snippets=snippets, recent_findings=recent_findings)

    return Pack(domain=DOMAIN, goal=GOAL, connector=connector, actions=actions, analyze=analyze)
