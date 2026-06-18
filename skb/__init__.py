"""skb — Self-improving Knowledge Base (v1).

A faithful, minimal implementation of idea_2.md: one hardcoded domain (curating a
knowledge base from incoming text), the full closed loop, an append-only JSONL
artifact store, and a per-action approval gate with a reversible hard floor.
"""

SCHEMA_V = 1
