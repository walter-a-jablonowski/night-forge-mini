# Core as Package — pip-installable night_forge_mini

**From the 2026-07-05 core review. Trigger-based: do this when the SECOND real
installation exists — with one deploy, copy-the-folder is fine.**

**What:** Make the blank core a proper installable package (`pyproject.toml`), so a
deployment is `domain_pack/ + config.json + data/` with `night-forge-mini` as a pinned
dependency instead of a copied folder.

**Why (and why not yet):**
- With copy-deploy, every core bugfix must be hand-copied into every installation —
  N deployments = N manual 3-way merges. As a dependency, an upgrade is
  `pip install -U` + reading the changelog.
- The `Pack` seam already supports this with zero code change — packs import
  `night_forge_mini.*`, never the other way around.
- Not yet: one moving deployment; packaging now is pure overhead.

**First step worth doing NOW (cheap):** give the core a `__version__` next to `SCHEMA_V`
and bump it on every core change, so a copied deployment can at least tell which core it
runs and whether a re-copy is due.

**Design sketch:**
- `pyproject.toml` in blank/, `pip install -e .` for dev; publish to a private index or
  install via git URL + tag (no PyPI needed).
- Deploy layout becomes: `my-system/{domain_pack/, config.json, data/, .env,
  requirements.txt(-> night-forge-mini==x.y)}`.
- Keep `python -m night_forge_mini` as the entry point; add a console script alias.

**Effort:** S (packaging + versioning + README deploy-flow update).
